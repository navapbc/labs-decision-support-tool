import logging
import textwrap
from copy import copy
from dataclasses import dataclass
from functools import cached_property
from typing import Callable, NamedTuple, Optional, Sequence

from langchain_text_splitters import RecursiveCharacterTextSplitter
from mistletoe import block_token
from nutree import Node, Tree

from src.ingestion.markdown_tree import (
    TokenNodeData,
    get_parent_headings_raw,
    remove_child,
    render_nodes_as_md,
    HeadingSectionNodeData,
    _get_node_data_id,
    copy_tree,
)
from src.util.string_utils import remove_links

logger = logging.getLogger(__name__)


def shorten(body: str, char_limit: int, placeholder: str = "...", max_lines: int = 2) -> str:
    "Shorten text while retaining line breaks. textwrap.shorten() removes line breaks"
    new_body = []
    char_remaining = char_limit
    for line in body.splitlines()[:max_lines]:
        line = textwrap.shorten(
            line, char_remaining, placeholder=placeholder, break_long_words=False
        )
        new_body.append(line)
        char_remaining -= len(line)
        if char_remaining < len(placeholder):
            break
    return "\n".join(new_body)


def copy_ancestors(node: Node, target_tree: Tree) -> Node:
    "Copy the ancestors of node to target_tree, returning the deepest ancestor in the target tree"
    ancestor_nodes = node.get_parent_list()
    p_node = target_tree
    for parent in ancestor_nodes:
        existing_p_node = next((c for c in p_node.children if c.data_id == parent.data_id), None)
        if existing_p_node:
            p_node = existing_p_node
        else:
            logger.info("Copying %s to parent %s", parent.data_id, p_node.data_id)
            p_node = parent.copy_to(p_node, deep=False)
            # Remember to call update_copied_tree() since we skip: p_node.set_data(copy(parent.data), data_id=parent.data_id)

    return p_node


def copy_subtree(
    node: Node, include_descendants: bool = True, include_ancestors: bool = True
) -> Tree:
    """
    Returns a new tree for the node, its descendants, and optionally its ancestors (to capture headings).
    Each node's contents is deep-copied, including node.data and node.data.token.
    """
    subtree = Tree(f"{node.data_id} subtree", shadow_attrs=True, calc_data_id=_get_node_data_id)
    # Copy the meta attributes from the original tree so that get_parent_headings() works
    for k, v in node.tree.system_root.meta.items():
        subtree.system_root.set_meta(k, v.copy())

    # Copy the nodes and descendants; this does not deep-copy node.data objects
    # For some reason, copy_to() assigns a random data_id to the new node in subtree
    new_node = node.copy_to(subtree, deep=include_descendants)

    if include_ancestors:
        new_parent_node = copy_ancestors(node, new_node.tree)
        new_node.move_to(new_parent_node)

    assert new_node.data_id == node.data_id, f"Expected data_id {node.data_id!r} for {new_node}"

    update_copied_tree(subtree)

    # At this point, no object in the subtree should be pointing to objects in the original tree,
    # except for tokens associated with "freeze_token_children". We are free to modify the subtree.
    return new_node


def update_copied_tree(tree: Tree) -> None:
    # Set the data_id back to the original, along with creating copies of objects
    for n in tree:
        n.set_data(copy(n.data), data_id=n.data.data_id)
        n.data.tree = tree
        if isinstance(n.data, TokenNodeData):
            are_tokens_frozen = find_closest_ancestor(
                n,
                lambda p: isinstance(p.data, TokenNodeData) and p.data["freeze_token_children"],
                include_self=True,
            )
            # Why check for are_tokens_frozen? Because calling copy() on Paragraph tokens doesn't work.
            # Fortunately if we use "freeze_token_children", then we don't need to copy Paragraph tokens
            if not are_tokens_frozen:
                assert (
                    n.data_type != "Paragraph"
                ), f"Unexpected Paragraph node {n.id_string}; should be frozen"
                n.data.token = copy(n.data.token)

    # Now that copies of node.data and node.data.token are created, update references to the tokens
    # Update all node.data.token.children to point to the new token objects in the subtree
    for n in tree:
        if isinstance(n.data, TokenNodeData) and not n.data["freeze_token_children"]:
            n.data.token.children = [
                c.token for c in n.children if isinstance(c.data, TokenNodeData)
            ]
            for c in n.data.token.children:
                # token.parent was indirectly updated when token.children was set
                assert c.parent == n.data.token


def remove_children_from(node: Node, child_data_ids: set[str]) -> None:
    "Remove children nodes with data_id in child_data_ids from node"
    # Do not remove children while iterating through them
    # Create a list of child nodes to remove, then remove them
    nodes_to_remove = [c for c in node.children if c.data_id in child_data_ids]
    if len(nodes_to_remove) != len(child_data_ids):
        logger.warning(
            "Expected to remove %s, but found only %s",
            child_data_ids,
            set(n.data_id for n in nodes_to_remove),
        )
    for child_node in nodes_to_remove:
        remove_child(child_node)


def find_closest_ancestor(
    node: Node, does_match: Callable[[Node], bool], include_self: bool = False
) -> Node:
    "Return the first parent/ancestor node that matches the does_match function"
    if include_self and does_match(node):
        return node

    while node := node.parent:
        if does_match(node):
            return node

    return None


class NodeWithIntro:

    def __init__(self, node: Node, intro_node: Optional[Node] = None) -> None:
        self.node = node
        self.intro_node = intro_node
        assert isinstance(node, Node), f"Unexpected type {type(node)} for node"
        assert not intro_node or isinstance(
            intro_node, Node
        ), f"Unexpected type {type(intro_node)} for intro_node"
        self.as_list = [intro_node, node] if intro_node else [node]

    def __str__(self) -> str:
        return f"{self.node.data_id}{f' with intro {self.intro_node.data_id}' if self.intro_node else ''}"


@dataclass
class ProtoChunk:
    "Temporary data structure for storing chunk data before creating a Chunk object"
    id: str
    nodes: list[Node]
    data_ids: list[str]
    headings: list[str]
    context_str: str  # Headings breadcrumb
    markdown: str  # Markdown content of the chunk
    embedding_str: str  # String used to create embedding
    length: int  # Length of embedding_str


class ChunkingConfig:

    def __init__(self, max_length: int) -> None:
        self.max_length = max_length
        self.chunks: dict[str, ProtoChunk] = {}

    @cached_property
    def text_splitter(self) -> RecursiveCharacterTextSplitter:
        chars_per_word = 6  # Assume a low 4 characters per word
        overlapping_words = 15  # 15 words overlap between chunks
        return RecursiveCharacterTextSplitter(
            chunk_size=chars_per_word * self.max_length,
            chunk_overlap=chars_per_word * overlapping_words,
        )

    def reset(self) -> None:
        self.chunks = {}

    def text_length(self, markdown: str) -> int:
        return len(markdown.split())

    def nodes_fit_in_chunk(self, nodes: list[Node]) -> bool:
        logger.debug("Checking fit: %s", [n.data_id for n in nodes])
        chunk = self.create_protochunk(nodes)
        return chunk.length < self.max_length

    def add_chunk(self, chunk: ProtoChunk) -> None:
        # Don't add Heading nodes by themselves
        if len(chunk.nodes) == 1 and chunk.nodes[0].data_type in ["Heading"]:
            raise AssertionError(f"Unexpected single Heading node: {chunk.nodes[0].id_string}")

        if not chunk.length < self.max_length:
            logger.error("Chunk %s is too large! %s > %s", chunk.id, chunk.length, self.max_length)
            # FIXME: raise AssertionError(f"{chunk.id} is too large! {chunk.length} > {self.max_length}")
        logger.info("Adding chunk %s created from: %s", chunk.id, [c.data_id for c in chunk.nodes])
        self.chunks[chunk.id] = chunk

    def create_protochunk(
        self,
        nodes: list[Node],
        chunk_id_suffix: Optional[str] = None,
        breadcrumb_node: Optional[Node] = None,
        markdown: Optional[str] = None,
    ) -> ProtoChunk:
        if not chunk_id_suffix:
            chunk_id_suffix = nodes[0].data_id
        chunk_id = f"{len(self.chunks)}:{chunk_id_suffix}"
        # logger.info("Creating protochunk %s using %s", chunk_id, [c.data_id for c in nodes])

        if not markdown:
            markdown = render_nodes_as_md(nodes)
            markdown = self._replace_table_separators(markdown)
        markdown = markdown.strip()

        headings = self._headings_with_doc_name(breadcrumb_node or nodes[0])
        context_str = "\n".join(headings)
        embedding_str = f"{context_str.strip()}\n\n{remove_links(markdown)}"

        chunk = ProtoChunk(
            chunk_id,
            nodes,
            [n.data_id for n in nodes],
            headings,
            context_str,
            markdown,
            embedding_str,
            self.text_length(embedding_str),
        )
        return chunk

    def _replace_table_separators(self, markdown: str) -> str:
        "Workaround for tokenizers that count each dash in a table separator as a token"
        if "| ---" not in markdown:
            return markdown

        lines = markdown.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("| ---"):
                cols = line.count(" |") - 1
                lines[i] = "| " + "--- | " * cols
        return "\n".join(lines)

    def _headings_with_doc_name(self, node: Node) -> list[str]:
        headings = get_parent_headings_raw(node)
        document_node = node.tree.first_child()
        assert document_node.data_type == "Document"
        if doc_name := document_node.data["name"]:
            headings.insert(0, doc_name)
        return headings

    def create_chunks_for_next_nodes(self, node_with_intro: NodeWithIntro) -> None:
        node = node_with_intro.node
        assert node.data_type not in [
            "HeadingSection",
            "List",
            "Table",
        ], f"This should have been handled by split_heading_section_into_chunks(): {node.id_string}"
        logger.warning("If this is called often, use a better text splitter for %s", node.id_string)

        temp_chunk = self.create_protochunk(node_with_intro.as_list, breadcrumb_node=node)
        splits = self.text_splitter.split_text(temp_chunk.embedding_str)
        for i, split in enumerate(splits):
            self.add_chunk(
                self.create_protochunk(
                    node_with_intro.as_list,
                    chunk_id_suffix=f"{node.data_id}[{i}]",
                    markdown=split,
                    breadcrumb_node=node,
                )
            )

    def should_summarize(self, node_with_intro: NodeWithIntro) -> bool:
        next_nodes_portion = (
            self.text_length(render_nodes_as_md(node_with_intro.as_list)) / self.max_length
        )
        # Example on https://edd.ca.gov/en/jobs_and_training/FAQs_WARN/
        # Only the 1 larger accordion is chunked by itself and summarized.
        # The smaller accordions are included alongside other accordions.
        # logger.debug("should_summarize: %f %s", next_nodes_portion, [n.data_id for n in node_with_intro])
        return next_nodes_portion > 0.75

    # def compose_summary_text(self, node: Node) -> str:
    #     return (
    #         shorten(remove_links(node.render()).splitlines()[0], 100, placeholder="...")
    #         + f" (SUMMARY of {node.data_id})\n\n"
    #     )
    def compose_summary_text(self, node: Node) -> str:
        if node.data_type not in ["Heading", "HeadingSection", "List", "ListItem"]:
            return f"(SUMMARIZED {node.data_id})\n\n"
        if not (md := node.render()):
            logger.warning(
                "No markdown for %s: children=%s", node, [c.data_id for c in node.children]
            )

        if node.data_type == "List":
            items = [line for line in md.splitlines() if line.startswith("* ")]
            items = [
                shorten(remove_links(line), int(200 / len(items)), placeholder="...")
                for line in items
            ]
            summary = "\n".join(items)
            return f"(\n{summary}\n)\n\n"
        else:
            summary = shorten(remove_links(md.splitlines()[0]), 140, placeholder="...")
            return f"({summary})\n\n"


def chunk_tree(in_tree: Tree, config: ChunkingConfig) -> dict[str, ProtoChunk]:
    # Reset the tree for chunking
    config.reset()

    # 2 trees:
    # 1. The original tree is used to create the chunks from chunk_buffer
    # 2. The copied tree where nodes can be removed to reflect chunking
    # node.data points to the same object in both trees. Nope! token.children must be modified for rendering
    # New plan: use copy_subtree() to create a new tree for each chunk
    # 3 trees:
    # 1. COMMITTED: original tree: only updated when add_chunk() is called
    # 2. (transactional) BUFFER: chunking_tree: reflect (uncommitted) chunk_buffer
    # 3. (transactional) WORKING: copied original working tree: copy of the original tree, but nodes can be removed to reflect (uncommitted) chunk_buffer
    #    used to assess tree wrt BUFFER

    doc_node = copy_tree(in_tree).first_child()  # COMMITTED tree

    # Try to chunk as much content as possible, so see if the node's contents fit, including descendants
    while not config.nodes_fit_in_chunk([doc_node]):
        logger.info("======= Document node %s is too large for one chunk", doc_node.data_id)
        # a Document node is structurally similar to a HeadingSection node
        # split_heading_section_into_chunks(doc_node, config)
        n = doc_node.first_child()
        _gradually_chunk_tree_nodes(n, config)

    config.add_chunk(config.create_protochunk([doc_node]))
    return config.chunks


RELEVANT_TYPES = ["HeadingSection", "Heading", "List", "Table", "ListItem", "Paragraph"]


def _update_tokens(chunking_tree):
    "Do this after copying a node to chunking_tree"
    for n in chunking_tree:
        if isinstance(n.data, TokenNodeData):
            child_tokens = [c.token for c in n.children if isinstance(c.data, TokenNodeData)]
            # Ensure ordering is retained
            n.data.token.children = [
                c for c in n.data.token.children if not hasattr(c, "type") or c in child_tokens
            ]
            n.data.token.children += [c for c in child_tokens if c not in n.data.token.children]

            logger.info("Updated tokens for %s: %s", n.data_id, [c for c in n.data.token.children])


def _gradually_chunk_tree_nodes(orig_node: Node, config: ChunkingConfig):
    committed_tree = orig_node.tree
    logger.info("CommittedTree: %s", committed_tree.format())
    logger.info(
        "Committed MD: %s", config.create_protochunk([committed_tree.first_child()]).markdown
    )

    # Transaction trees
    working_tree = copy_tree(committed_tree, copy_data_attribs=True)
    node = working_tree[orig_node.data_id]

    # Empty chunking data structures
    assert node.parent.data_type == "Document"
    chunking_tree = copy_subtree(
        node.parent, include_descendants=False, include_ancestors=True
    ).tree
    chunk_buffer: list[NodeWithIntro] = []  # in chunking_tree
    intro_node: Node | None = None
    while node:
        if node.data["chunked"]:
            # and node.data_type == "Paragraph":
            logger.info("Skipping chunked Paragraph node %s", node.data_id)
            node = node.next_sibling()
            continue

        # keep-with-next for intro nodes
        if node.data["is_intro"]:
            intro_node = node
            node = node.next_sibling()
            continue

        next_node = NodeWithIntro(node, intro_node)
        logger.info("Next: %s", next_node)
        logger.info("ChunkingTree: %s", chunking_tree.format())
        logger.info(
            "Chunking MD: %s", config.create_protochunk([chunking_tree.first_child()]).markdown
        )
        logger.info("WorkingTree: %s", working_tree.format())
        logger.info(
            "Working MD: %s", config.create_protochunk([working_tree.first_child()]).markdown
        )
        if config.nodes_fit_in_chunk([chunking_tree.first_child()] + next_node.as_list):
            logger.info("Fits! Adding %s", next_node)
            # Update WORKING tree
            # DON'T update COMMITTED tree

            # Copy next_node.intro_node branch to chunking_tree BEFORE copying next_node.node branch
            # intro_node may be a parent (e.g., ListItem) of node (e.g., List)
            new_intro_node = None
            if next_node.intro_node:
                # There is no one structural relationship: assert next_node.intro_node.parent == next_node.node.parent
                if not (
                    new_intro_node := chunking_tree.find(
                        match=lambda n: n.data_id == next_node.intro_node.data_id
                    )
                ):
                    # Copy next_node.intro_node branch to chunking_tree
                    logger.info(
                        "Copying next_node.intro_node %s to chunking_tree",
                        next_node.intro_node.data_id,
                    )
                    new_intro_parent_node = copy_ancestors(next_node.intro_node, chunking_tree)
                    # copy then remove in _summarize_nodes() => move
                    new_intro_node = next_node.intro_node.copy_to(new_intro_parent_node, deep=True)
                    # new_intro_node.set_data(
                    #     copy(new_intro_node.data), data_id=next_node.intro_node.data_id
                    # )

            # Copy next_node.node branch to chunking_tree
            if not (
                new_node := chunking_tree.find(match=lambda n: n.data_id == next_node.node.data_id)
            ):
                logger.info("Copying next_node.node %s to chunking_tree", next_node.node.data_id)
                new_parent_node = copy_ancestors(next_node.node, chunking_tree)
                # For some reason, copy_to() assigns a random data_id to the new node in subtree
                # copy then remove in _summarize_nodes() => move
                new_node = next_node.node.copy_to(new_parent_node, deep=True)
                # new_node.set_data(copy(new_node.data), data_id=next_node.node.data_id)

            update_copied_tree(chunking_tree)

            copied_next_node = NodeWithIntro(new_node, new_intro_node)
            chunk_buffer.append(copied_next_node)

            # Since intro_node is included in chunk_buffer, reset it
            intro_node = None
            # _update_tokens(chunking_tree)
            node = node.next_sibling()

            # This will remove node
            _summarize_nodes(next_node.as_list, config)
            continue

        # does not fit
        # Following does not modify the working tree or chunk_buffer
        # It may modify the COMMITTED tree and RETURN
        # chunking_tree is used to flush the chunk_buffer to create a chunk
        logger.info("Does not fit: %s + %s", chunking_tree.first_child().data_id, next_node)
        if not node.has_children() and not config.nodes_fit_in_chunk(next_node.as_list):
            assert node.data_type in [
                "Paragraph"
            ], f"Unexpected data_type {node.data_type} for leaf node"
            logger.info("Splitting Paragraph %s into multiple chunks", next_node)
            # must split Paragraph n into multiple chunks; doesn't make sense to mix parts of it with other chunks

            # update COMMITTED tree
            orig_next_node = NodeWithIntro(
                committed_tree[next_node.node.data_id],
                committed_tree[next_node.intro_node.data_id] if next_node.intro_node else None,
            )
            # _chunk_and_summarize_next_nodes(config, node_with_intro)
            # split_paragraph_into_chunks
            config.create_chunks_for_next_nodes(orig_next_node)
            _summarize_nodes(orig_next_node.as_list, config)
        elif full_enough_to_flush([chunking_tree.first_child()], config):
            logger.info("Full enough! %s", [n.data_id for n in chunking_tree])
            # Flush the chunk_buffer to a chunk
            config.add_chunk(pc := config.create_protochunk([chunking_tree.first_child()]))
            logger.debug("Added chunk %s:\n%s", pc.id, pc.markdown)
            # TODO: del chunk_tree

            # update COMMITTED tree
            for nwi in chunk_buffer:
                orig_nodes = NodeWithIntro(
                    committed_tree[nwi.node.data_id],
                    committed_tree[nwi.intro_node.data_id] if nwi.intro_node else None,
                )
                _summarize_nodes(orig_nodes.as_list, config)
        elif want_to_go_deeper(working_tree, next_node, config):
            node = node.first_child()
            logger.info("Go deeper to %s", node.data_id)
            continue
        else:
            assert node.data_type in [
                "ListItem",
                "List",
                "Table",
            ], f"Unexpected data_type {node.data_type}"
            # Summarize the next node
            # update COMMITTED tree
            orig_next_node = NodeWithIntro(
                committed_tree[next_node.node.data_id],
                committed_tree[next_node.intro_node.data_id] if next_node.intro_node else None,
            )
            _chunk_and_summarize_next_nodes(config, orig_next_node)
        return


def full_enough_to_flush(chunk_buffer: list[Node], config: ChunkingConfig):
    chunk = config.create_protochunk(chunk_buffer)
    next_nodes_portion = chunk.length / config.max_length
    logger.info("next_nodes_portion = %s", next_nodes_portion)
    # Example on https://edd.ca.gov/en/jobs_and_training/FAQs_WARN/
    # Only the 1 larger accordion is chunked by itself and summarized.
    # The smaller accordions are included alongside other accordions.
    # logger.debug("should_summarize: %f %s", next_nodes_portion, [n.data_id for n in node_with_intro])
    return next_nodes_portion > 0.75


def want_to_go_deeper(working_tree: Tree, next: NodeWithIntro, config: ChunkingConfig):
    if next.node.data_type in "HeadingSection":
        return True
    if next.node.data_type == "List":
        sublists = next.node.find_all(match=lambda n: n.data_type == "List")
        if sublists:
            return True
    if next.node.has_children():
        next_nodes_portion = (
            config.text_length(render_nodes_as_md(next.as_list)) / config.max_length
        )
        return next_nodes_portion > 0.75
    return False


def _create_new_tree_with(
    orig_node: Node, children_ids: dict[str, Node], intro_node: Optional[Node] = None
) -> NodeWithIntro:
    "Create a new tree keeping only the children in children_ids"
    logger.debug("Creating new tree with children: %s", children_ids.keys())
    block_node = copy_subtree(orig_node)  # the List or Table node
    if intro_node:
        logger.debug("Inserting intro_node %s", intro_node.data_id)
        assert intro_node.data[
            "freeze_token_children"
        ], f"Non-frozen intro_node {intro_node.id_string} will need its data and token copied to avoid modifying the original tree"
        intro_node_copy = intro_node.copy_to(block_node.parent, before=block_node, deep=True)

        intro_node_copy.set_data(copy(intro_node_copy.data), data_id=intro_node_copy.data.data_id)
        intro_node_copy.data.tree = block_node.tree

        assert not block_node.data["show_intro"]
    else:
        intro_node_copy = None
        # Since intro_node is not provided, set show_intro=True so that
        # the block_node.data["intro"] is rendered in place of intro_node
        block_node.data["show_intro"] = True
    to_remove = {c.data_id for c in block_node.children} - children_ids.keys()
    remove_children_from(block_node, to_remove)

    assert {c.data_id for c in block_node.children} == children_ids.keys()
    return NodeWithIntro(block_node, intro_node_copy)


def split_list_or_table_node_into_chunks(
    node: Node, config: ChunkingConfig, intro_node: Optional[Node] = None
) -> None:
    assert node.data_type in ["List", "Table"]
    assert node.children, f"{node.id_string} should have children to split"
    logger.info("Splitting large %s into multiple chunks", node.id_string)

    chunks_to_create: list[list[Node]] = []
    children_ids = {c.data_id: c for c in node.children}
    # Copy the node's subtree, then gradually remove the last child until the content fits
    # If that doesn't work, start summarize the each sublist

    # Only the first subtree will have the intro_node, if it exists
    candidate_node = _create_new_tree_with(node, children_ids, intro_node)
    while children_ids:  # Repeat until all the children are in some chunk
        block_node = candidate_node.node
        logger.info(
            "Trying to fit %s into a chunk by gradually removing children: %s",
            block_node.data_id,
            [c.data_id for c in block_node.children],
        )
        while not config.nodes_fit_in_chunk(candidate_node.as_list) and block_node.has_children():
            remove_child(block_node.last_child())

        if block_node.has_children():
            logger.info("Fits into a chunk: %s", [c.data_id for c in block_node.children])
            chunks_to_create.append(candidate_node.as_list)
            # Don't need intro_node for subsequent subtrees
            intro_node = None
            for child_node in block_node.children:
                del children_ids[child_node.data_id]
        else:  # List doesn't fit with any children
            # Reset the tree (restore children) and try to summarize the sublists
            candidate_node = _create_new_tree_with(node, children_ids, intro_node)
            summarized_node = _summarize_big_listitems(candidate_node, config)
            if summarized_node:
                logger.info("Summarized big list items into %s", summarized_node)
                logger.debug("children_ids: %s", children_ids.keys())
                candidate_node.node.tree.print()
                # logger.info("RETURNING from split_list_or_table_node_into_chunks %s", candidate_node)
                # return
                # summarized_items = list(candidate_node.node.children)
                # for n in summarized_items:
                #     del children_ids[n.data_id]
                # logger.debug("New children_ids: %s", children_ids.keys())
                continue  # Try again with the reset tree and candidate_node
            else:
                # FIXME: Fall back to use RecursiveCharacterTextSplitter
                raise AssertionError(f"{block_node.data_id} should have at least one child")

        if children_ids:  # Prep for the next loop iteration
            # Subsequent subtrees don't need an intro_node
            candidate_node = _create_new_tree_with(node, children_ids)

    _create_chunks(config, node, chunks_to_create)


def _summarize_big_listitems(
    candidate_node: NodeWithIntro, config: ChunkingConfig
) -> NodeWithIntro | None:
    assert (
        candidate_node.node.data_type == "List"
    ), f"Unexpected data_type {candidate_node.node.data_type}"
    # TODO: This summarizes ALL list items, not just the big ones. Make this smarter.
    for li in list(candidate_node.node.children):
        assert li.data_type == "ListItem", f"Unexpected child {li.id_string}"
        li_candidate = NodeWithIntro(li)
        if config.should_summarize(li_candidate):
            logger.info("Summarizing big list item %s", li.data_id)
            li_candidate = _chunk_and_summarize_next_nodes(config, li_candidate)
            return li_candidate
    return None


def split_heading_section_into_chunks(node: Node, config: ChunkingConfig) -> None:
    assert node.data_type in ["Document", "HeadingSection", "ListItem"]

    logger.info(
        "Splitting large %s into chunks given children: %s",
        node.id_string,
        # Reduce verbosity by excluding BlankLine nodes
        ", ".join([c.data_id for c in node.children if c.data_type != "BlankLine"]),
    )
    # Iterate through each child node, adding them to node_buffer
    # Before chunk capacity is exceeded, designate node_buffer to be used as a chunk
    # and assign node_buffer to a new list.
    # At any time, the contents of node_buffer should fit into a chunk,
    # so check if nodes_fit_in_chunk(node_buffer + [nodes]) before adding to node_buffer.
    node_buffer: list[Node] = []
    intro_node = None
    chunks_to_create: list[list[Node]] = []
    for child in node.children:
        logger.debug("%s: Assessing child node %s", node.data_id, child.data_id)

        # These intro_nodes should be kept with the next child node.
        # When child.data["is_intro"]==True, there is always a next child,
        # so child will be included in node_with_intro on the next loop.
        if child.data["is_intro"]:
            intro_node = child
            continue

        node_with_intro = NodeWithIntro(node=child, intro_node=intro_node)
        # Since intro_node has been included in node_with_intro, reset it
        intro_node = None

        candidate_node_buffer = node_buffer + node_with_intro.as_list
        if config.nodes_fit_in_chunk(candidate_node_buffer):
            node_buffer = candidate_node_buffer
        else:  # candidate_node_buffer doesn't fit
            # Determine whether to summarize node_with_intro or add it to the next chunk

            # For these data_types, node_with_intro (and its descendants) can be chunked and summarized
            can_summarize = node_with_intro.node.data_type in ["HeadingSection", "List", "Table"]
            if can_summarize and config.should_summarize(node_with_intro):
                logger.warning(
                    "This logic should be handled in _add_to_buffer_or_summarize() %s",
                    node_with_intro,
                )
                assert (
                    False
                ), f"This logic should be handled in _add_to_buffer_or_summarize() {node_with_intro}"
                node_with_intro = _chunk_and_summarize_next_nodes(config, node_with_intro)
                # logger.info("RETURNING from _chunk_and_summarize_next_nodes %s", node_with_intro)
                # return
                # Try again now that node_with_intro has been chunked and summarized.
                # nodes_fit_in_chunk() calls render_nodes_as_md(), which will use the shorter
                # summary text instead of the full text
                candidate_node_buffer = node_buffer + node_with_intro.as_list
                if config.nodes_fit_in_chunk(candidate_node_buffer):
                    node_buffer = candidate_node_buffer
                    continue

            # Either no summary was created or candidate_node_buffer still doesn't fit using the summarized node_with_intro

            # Split candidate_node_buffer (node_buffer + node_with_intro) across multiple chunks
            # 1. Flush node_buffer to its own chunk
            if node_buffer:
                # Create a chunk with the current node_buffer
                chunks_to_create.append(node_buffer)
                # and reset node_buffer to a new list
                node_buffer = []
            assert not node_buffer, f"node_buffer should be empty: {node_buffer}"

            # 2. Handle node_with_intro
            # Check if node_with_intro can be the new node_buffer
            if config.nodes_fit_in_chunk(node_with_intro.as_list):
                # Reset node_buffer to be node_with_intro
                node_buffer = node_with_intro.as_list.copy()
            else:  # node_with_intro needs to be split into multiple chunks
                config.create_chunks_for_next_nodes(node_with_intro)

    assert not intro_node, f"Was intro_node {intro_node.data_id} added to a node_buffer?"
    if node_buffer:  # Create a chunk with the remaining nodes
        if config.nodes_fit_in_chunk(node_buffer):
            chunks_to_create.append(node_buffer)
        else:
            raise AssertionError(f"node_buffer should always fit: {node_buffer}")

    _create_chunks(config, node, chunks_to_create)


def _chunk_and_summarize_next_nodes(config, node_with_intro: NodeWithIntro) -> NodeWithIntro:
    node = node_with_intro.node
    # See if the node's contents fit, including descendants
    if config.nodes_fit_in_chunk(node_with_intro.as_list):
        config.add_chunk(config.create_protochunk(node_with_intro.as_list))
    elif node.data_type in ["HeadingSection", "ListItem"]:
        # ListItem can have similar children as HeadingSection
        logger.info("%s is too large for one chunk", node.data_id)
        split_heading_section_into_chunks(node, config)
    elif node.data_type in ["List", "Table"]:
        # List and Table nodes are container nodes and never have their own content.
        # Renderable content are in their children, which are either ListItem or TableRow nodes.
        # Split these specially since they can have an intro sentence (and table header)
        # to include for each chunk
        if node_with_intro.intro_node:
            # The intro_node, next_nodes[0], will be rendered fully in the first of the split chunks
            # Remaining chunks will use the short node.data["intro"] text instead
            split_list_or_table_node_into_chunks(node, config, node_with_intro.intro_node)
        else:
            # All split chunks will use the short node.data["intro"] text
            split_list_or_table_node_into_chunks(node, config)
    else:
        raise AssertionError(f"Unexpected data_type: {node.id_string}")

    # Then set a shorter summary text in a custom attribute
    # assert node.data["summary"] is None, "Summary should not be set yet"
    # node.data["summary"]
    return _summarize_node(node, config)


def _summarize_node(node_with_intro: NodeWithIntro, config: ChunkingConfig) -> NodeWithIntro:
    node = node_with_intro.node
    summary = config.compose_summary_text(node)
    logger.info("Added SUMMARY to %s: %r", node.data_id, summary)

    if isinstance(node.data, TokenNodeData):
        line_number = node.token.line_number
    elif isinstance(node.data, HeadingSectionNodeData):
        line_number = node.data.line_number
    else:
        raise AssertionError(f"Unexpected node.data type: {node.data_type}")
    p_nodedata = _create_paragraph_node_data(line_number, summary, node.tree)

    if node.data_type in ["List", "HeadingSection", "ListItem"]:
        # Replace all children and add Paragraph summary as the only child
        for c in list(node_with_intro.node.children):
            remove_child(c)

        # add summary Paragraph
        node.add_child(p_nodedata)
        if isinstance(node.data, TokenNodeData):
            node.token.children = [
                c.token for c in node.children if isinstance(c.data, TokenNodeData)
            ]
        logger.debug("%s children %s", node.data_id, [c.data_id for c in node.children])

        # FIXME: do something with the intro_node
        # if node_with_intro.intro_node:
        #     remove_child(node_with_intro.intro_node)
        return node_with_intro
    elif node.data_type == "Table":  # Replace Table with Paragraph summary
        parent = node.parent
        p_node = parent.add_child(p_nodedata, before=node)
        node.remove()
        if isinstance(parent.data, TokenNodeData):
            parent.token.children = [
                c.token for c in parent.children if isinstance(c.data, TokenNodeData)
            ]
        elif isinstance(parent.data, HeadingSectionNodeData):
            pass
        else:
            raise AssertionError(f"Unexpected parent.data type: {parent.data_type}")
        return NodeWithIntro(p_node, node_with_intro.intro_node)
    else:
        raise AssertionError(f"Unexpected data type: {node.data_type}")


def _insert_summary_node(node: Node, config: ChunkingConfig) -> Node:
    logger.info("_insert_summary_node for %s", node.data_id)
    summary = f"(CHUNKED: {node.data_id})"  # config.compose_summary_text(node)
    logger.info("Added SUMMARY to %s: %r", node.data_id, summary)

    p_nodedata = _create_paragraph_node_data(node.token.line_number, summary, node.tree)

    # Insert nodes with Paragraph summary
    parent = node.parent
    p_node = parent.add_child(p_nodedata, before=node)
    if isinstance(parent.data, TokenNodeData):
        assert parent.data_type in ["Document", "ListItem", "List", "Table"]
        parent.token.children = [
            c.token for c in parent.children if isinstance(c.data, TokenNodeData)
        ]
    elif isinstance(parent.data, HeadingSectionNodeData):
        pass
    else:
        raise AssertionError(f"Unexpected parent.data type: {parent.data_type}")
    # return NodeWithIntro(p_node, node_with_intro.intro_node)
    return p_node


def _summarize_nodes(nodes: list[Node], config: ChunkingConfig) -> Node:
    "Assumes nodes are at the same level in the tree, ie have the same parent"
    node = nodes[-1]
    if node.data_type == "Heading":
        logger.info("Skipping summarization of lone Heading node %s", node.data_id)
        assert [
            n.data_id for n in nodes if n != node
        ] == [], f"Unexpected nodes: {[n.data_id for n in nodes if n != node]}"
        return node

    logger.info("Summarizing %s with %s", node.data_id, [n.data_id for n in nodes if n != node])
    # assert all(n.parent == nodes[0].parent for n in nodes), f"Nodes should have the same parent {[n.parent.data_id for n in nodes]}"
    summary = f"(CHUNKED: {node.data_id} with {[n.data_id for n in nodes if n != node]})"  # config.compose_summary_text(node)
    if node.data_type == "ListItem":
        summary = "* " + summary  # FIXME: generalize this
    logger.info("Added SUMMARY to %s: %r", node.data_id, summary)

    # Replace all nodes with Paragraph summary

    p_nodedata = _create_paragraph_node_data(node.token.line_number, summary, node.tree)

    parent = node.parent
    p_node = parent.add_child(p_nodedata, before=node)
    for c in nodes:
        c.remove()
    if isinstance(parent.data, TokenNodeData):
        assert parent.data_type in ["Document", "ListItem", "List", "Table"]
        parent.token.children = [
            c.token for c in parent.children if isinstance(c.data, TokenNodeData)
        ]
    elif isinstance(parent.data, HeadingSectionNodeData):
        pass
    else:
        raise AssertionError(f"Unexpected parent.data type: {parent.data_type}")
    # return NodeWithIntro(p_node, node_with_intro.intro_node)
    return p_node


def _create_paragraph_node_data(line_number, summary, tree):
    p = block_token.Paragraph(lines=[f"{summary}\n"])
    p.line_number = line_number
    p_nodedata = TokenNodeData(p, tree)
    p_nodedata["freeze_token_children"] = True
    p_nodedata["oneliner_of_hidden_nodes"] = textwrap.shorten(
        remove_links(summary), 50, placeholder="...(hidden)", drop_whitespace=False
    )
    p_nodedata["chunked"] = True
    p_nodedata["is_summary"] = 1
    return p_nodedata


def _create_chunks(config: ChunkingConfig, node: Node, chunks_to_create: list[list[Node]]) -> None:
    """
    Create chunks based on chunks_to_create, which are some partitioning of node's children.
    If there are multiple chunks for the node, use a different chunk_id_suffix to make it obvious.
    """
    if len(chunks_to_create) == 1:
        chunk_nodes = chunks_to_create[0]
        if len(chunk_nodes) == 1 and chunk_nodes[0].data_type in ["Heading"]:
            # Don't chunk lone heading nodes
            return
        chunk = config.create_protochunk(chunk_nodes, chunk_id_suffix=f"{node.data_id}")
        config.add_chunk(chunk)
    else:
        for i, chunk_nodes in enumerate(chunks_to_create):
            # Make sure first_node is different from node. They can be the same when splitting Lists and Tables.
            first_node_id = (
                chunk_nodes[0].first_child().data_id
                if chunk_nodes[0].data_id == node.data_id
                else chunk_nodes[0].data_id
            )
            # The chunk id identifies the node being split, the split number, and the first node in the chunk
            chunk = config.create_protochunk(
                chunk_nodes,
                chunk_id_suffix=f"{node.data_id}[{i}]:{first_node_id}",
                # The headings breadcrumb should reflect the first item in chunk_nodes
                breadcrumb_node=chunk_nodes[0],
            )
            config.add_chunk(chunk)
