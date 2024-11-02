import logging
import textwrap
from functools import cached_property
from copy import copy
from dataclasses import dataclass
from typing import Callable, NamedTuple, Optional, Sequence

from langchain_text_splitters import RecursiveCharacterTextSplitter
from nutree import Node, Tree

from src.ingestion.markdown_tree import (
    TokenNodeData,
    get_parent_headings_raw,
    remove_child,
    render_nodes_as_md,
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


def copy_ancestors(node: Node, target_node: Node) -> int:
    "Copy the ancestors of node to target_tree, returning the number of ancestors copied"
    count = 0
    ancestor_nodes = node.get_parent_list()
    p_node = target_node.tree
    for parent in ancestor_nodes:
        p_node = parent.copy_to(p_node, deep=False)
        count += 1
    target_node.move_to(p_node)
    return count


def copy_subtree(node: Node, include_ancestors: bool = True) -> Tree:
    """
    Returns a new tree for the node, its descendants, and optionally its ancestors (to capture headings).
    Each node's contents is deep-copied, including node.data and node.data.token.
    """
    logger.info("Creating new tree from subtree %s", node.data_id)
    subtree = Tree(f"{node.data_id} subtree", shadow_attrs=True)
    # Copy the nodes and descendants; this does not deep-copy node.data objects
    # For some reason, copy_to() assigns a random data_id to the new node in subtree
    new_node = node.copy_to(subtree, deep=True)

    # Copy the meta attributes from the original tree so that get_parent_headings() works
    for k, v in node.tree.system_root.meta.items():
        subtree.system_root.set_meta(k, v.copy())

    if include_ancestors:
        copy_ancestors(node, new_node)

    # Set the data_id back to the original, along with creating copies of objects
    for n in subtree:
        n.set_data(copy(n.data), data_id=n.data.data_id)
        n.data.tree = subtree
        if isinstance(n.data, TokenNodeData):
            are_tokens_frozen = find_closest_ancestor(
                n,
                lambda p: isinstance(p.data, TokenNodeData) and p.data["freeze_token_children"],
                include_self=True,
            )
            # Why check for are_tokens_frozen? Because calling copy() on Paragraph tokens doesn't work.
            # Fortunately if we use "freeze_token_children", then we don't need to copy Paragraph tokens
            if not are_tokens_frozen:
                n.data.token = copy(n.data.token)

    assert new_node.data_id == node.data_id, f"Expected data_id {node.data_id!r} for {new_node}"

    # Now that copies of node.data and node.data.token are created, update references to the tokens
    # Update all node.data.token.children to point to the new token objects in the subtree
    for n in subtree:
        if isinstance(n.data, TokenNodeData) and not n.data["freeze_token_children"]:
            n.data.token.children = [
                c.token for c in n.children if isinstance(c.data, TokenNodeData)
            ]
            for c in n.data.token.children:
                # token.parent was indirectly updated when token.children was set
                assert c.parent == n.data.token

    # At this point, no object in the subtree should be pointing to objects in the original tree,
    # except for tokens associated with "freeze_token_children". We are free to modify the subtree.
    return new_node


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
        remove_child(node, child_node)


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
        self.as_list = [intro_node, node] if intro_node else [node]


@dataclass
class ProtoChunk:
    "Temporary data structure for storing chunk data before creating a Chunk object"
    id: str
    nodes: list[Node]
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
        return RecursiveCharacterTextSplitter(
            chunk_size=5 * self.max_length,  # Assume a low 5 characters per word
            chunk_overlap=7 * 20,  # 20 words (average sentence) overlap between chunks
        )

    def reset(self) -> None:
        self.chunks = {}

    def text_length(self, markdown: str) -> int:
        return len(markdown.split())

    def nodes_fit_in_chunk(self, nodes: list[Node]) -> bool:
        chunk = self.create_protochunk(nodes)
        return chunk.length < self.max_length

    def add_chunk(self, chunk: ProtoChunk) -> None:
        # Don't add Heading nodes by themselves
        if len(chunk.nodes) == 1 and chunk.nodes[0].data_type in ["Heading"]:
            raise AssertionError(f"Unexpected single Heading node: {chunk.nodes[0].id_string}")

        if not chunk.length < self.max_length:
            raise AssertionError(f"{chunk.id} is too large! {chunk.length} > {self.max_length}")
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

        if not markdown:
            markdown = render_nodes_as_md(nodes)
        markdown = markdown.strip()

        headings = self._headings_with_doc_name(breadcrumb_node or nodes[0])
        context_str = "\n".join(headings)
        embedding_str = f"{context_str.strip()}\n\n{remove_links(markdown)}"

        chunk = ProtoChunk(
            chunk_id,
            nodes,
            headings,
            context_str,
            markdown,
            embedding_str,
            self.text_length(embedding_str),
        )
        return chunk

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
        ], f"This should have been handled by split_heading_section_into_chunks(): {node.id_string} {node.data['summary']!r}"
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

    def should_summarize(self, node_with_intro: NodeWithIntro, node_buffer: Sequence[Node]) -> bool:
        next_nodes_portion = (
            self.text_length(render_nodes_as_md(node_with_intro.as_list)) / self.max_length
        )
        # Example on https://edd.ca.gov/en/jobs_and_training/FAQs_WARN/
        # Only the 1 larger accordion is chunked by itself and summarized.
        # The smaller accordions are included alongside other accordions.
        # logger.debug("should_summarize: %f %s", next_nodes_portion, [n.data_id for n in node_with_intro])
        return next_nodes_portion > 0.75

    def compose_summary_text(self, node: Node) -> str:
        return (
            shorten(remove_links(node.render()).splitlines()[0], 100, placeholder="...")
            + f" (SUMMARY of {node.data_id})\n\n"
        )


def chunk_tree(tree: Tree, config: ChunkingConfig) -> dict[str, ProtoChunk]:
    config.reset()
    # Reset the tree for chunking
    for n in tree:
        for attr in ["summary"]:
            n.data[attr] = None

    node = tree.first_child()
    # Try to chunk as much content as possible, so see if the node's contents fit, including descendants
    if config.nodes_fit_in_chunk([node]):
        config.add_chunk(config.create_protochunk([node]))
        # Don't need to recurse through child nodes
    else:
        # node is a Document node and structurally similar to a HeadingSection node
        split_heading_section_into_chunks(node, config)
    return config.chunks


def split_list_or_table_node_into_chunks(
    node: Node, config: ChunkingConfig, intro_node: Optional[Node] = None
) -> None:
    assert node.data_type in ["List", "Table"]
    logger.info("Splitting large %s into multiple chunks", node.id_string)

    def create_new_tree_with(
        children_ids: set[str], intro_node: Optional[Node] = None
    ) -> tuple[Node, Optional[Node]]:
        "Create a new tree keeping only the children in children_ids"
        block_node = copy_subtree(node)  # the List or Table node
        if intro_node:
            assert intro_node.data[
                "freeze_token_children"
            ], f"Non-frozen intro_node {intro_node.id_string} will need its data and token copied to avoid modifying the original tree"
            intro_node_copy = intro_node.copy_to(block_node.parent, before=block_node, deep=True)
            assert not block_node.data["show_intro"]
        else:
            intro_node_copy = None
            # Since intro_node is not provided, set show_intro=True so that
            # the block_node.data["intro"] is rendered in place of intro_node
            block_node.data["show_intro"] = True
        to_remove = {c.data_id for c in block_node.children} - children_ids
        remove_children_from(block_node, to_remove)
        assert {c.data_id for c in block_node.children} == children_ids
        return (block_node, intro_node_copy)

    chunks_to_create: list[list[Node]] = []
    children_ids = {c.data_id for c in node.children}
    # Copy the node's subtree, then gradually remove the last child until the content fits
    # The first subtree will have the intro_node, if it exists
    block_node, intro_node_copy = create_new_tree_with(children_ids, intro_node)
    # Put the intro node before block_node
    candidate_node_list = [intro_node_copy, block_node]
    while children_ids:  # Repeat until all the children are in some chunk
        while not config.nodes_fit_in_chunk(candidate_node_list) and block_node.has_children():
            remove_child(block_node, block_node.last_child())

        if block_node.has_children():
            chunks_to_create.append(candidate_node_list)
            for child_node in block_node.children:
                children_ids.remove(child_node.data_id)
        else:
            raise AssertionError(f"{block_node.data_id} should have at least one child")

        if not children_ids:
            break

        block_node, _no_intro_node = create_new_tree_with(children_ids)
        # Subsequent subtrees will not have an intro_node
        candidate_node_list = [block_node]

    _create_chunks(config, node, chunks_to_create)


def split_heading_section_into_chunks(node: Node, config: ChunkingConfig) -> None:
    assert node.data_type in ["Document", "HeadingSection"]

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
        logger.debug("%s: Adding child node %s", node.data_id, child.data_id)

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
            if can_summarize and config.should_summarize(node_with_intro, node_buffer):
                _chunk_and_summarize_next_nodes(config, node_with_intro)
                # Try again now that node_with_intro has been chunked and summarized.
                # nodes_fit_in_chunk() calls render_nodes_as_md(), which will use the shorter
                # summary text instead of the full text
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

    assert not intro_node, f"intro_node {intro_node.data_id} should have been added to node_with_intro"
    if node_buffer:  # Create a chunk with the remaining nodes
        if config.nodes_fit_in_chunk(node_buffer):
            chunks_to_create.append(node_buffer)
        else:
            raise AssertionError(f"node_buffer should always fit: {node_buffer}")

    _create_chunks(config, node, chunks_to_create)


def _chunk_and_summarize_next_nodes(config, node_with_intro: NodeWithIntro):
    node = node_with_intro.node
    # See if the node's contents fit, including descendants
    if config.nodes_fit_in_chunk(node_with_intro.as_list):
        config.add_chunk(config.create_protochunk(node_with_intro.as_list))
    elif node.data_type in ["HeadingSection"]:
        logger.info("%s is too large for one chunk", node.data_id)
        split_heading_section_into_chunks(node, config)
    elif node.data_type in ["List", "Table"]:
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
    assert node.data["summary"] is None, "Summary should not be set yet"
    node.data["summary"] = config.compose_summary_text(node)
    logger.info("Added summary to %s: %r", node.data_id, node.data["summary"])


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
        logger.info("Creating %s chunk for %s: %s", len(chunks_to_create), node.data_id, [c.data_id for c in chunk_nodes])
        chunk = config.create_protochunk(chunk_nodes, chunk_id_suffix=f"{node.data_id}")
        config.add_chunk(chunk)
    else:
        for i, chunk_nodes in enumerate(chunks_to_create):
            logger.info("Creating %s chunks for %s: %s", len(chunk_nodes), node.data_id, [c.data_id for c in chunk_nodes])
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