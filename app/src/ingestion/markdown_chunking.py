import itertools
import logging
import textwrap
from copy import copy
from dataclasses import dataclass
from typing import Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter
from mistletoe import block_token
from nutree import Node, Tree

from src.ingestion.markdown_tree import (
    HeadingSectionNodeData,
    TokenNodeData,
    assert_no_mismatches,
    copy_subtree,
    copy_with_ancestors,
    data_ids_for,
    find_data_type_nodes,
    find_node,
    get_parent_headings_raw,
    next_renderable_node,
    remove_children_from,
    render_nodes_as_md,
    tokens_vs_tree_mismatches,
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


# endregion
# region ###### Classes


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


class ChunkingConfig:

    def __init__(self, max_length: int) -> None:
        self.max_length = max_length

        self.full_enough_threshold = 0.65
        self.text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            model_name="gpt-4",
            # Offer some buffer to ensure we stay below the max_length
            chunk_size=self.max_length - 30,
            chunk_overlap=15,
        )
        self.reset()

    def reset(self) -> None:
        self.chunks: dict[str, ProtoChunk] = {}

    def text_length(self, markdown: str) -> int:
        return self.text_splitter._length_function(markdown)

    def nodes_fit_in_chunk(self, nodes: list[Node], breadcrumb_node) -> bool:
        chunk = self.create_protochunk(nodes, breadcrumb_node=breadcrumb_node)
        logger.info("Checking fit %s: %s", chunk.length, data_ids_for(nodes))
        return chunk.length < self.max_length

    def add_chunk(self, chunk: ProtoChunk) -> None:
        # Don't add Heading nodes by themselves
        if len(chunk.nodes) == 1 and chunk.nodes[0].data_type in ["Heading"]:
            raise AssertionError(f"Unexpected single Heading node: {chunk.nodes[0].id_string}")

        if chunk.length > self.max_length:
            raise AssertionError(f"{chunk.id} is too large! {chunk.length} > {self.max_length}")
        chunk.id = f"{len(self.chunks)}:{chunk.id}"
        logger.info("Adding chunk %s created from: %s", chunk.id, data_ids_for(chunk.nodes))
        self.chunks[chunk.id] = chunk

    def create_protochunk(
        self,
        nodes: list[Node],
        *,
        chunk_id_suffix: Optional[str] = None,
        breadcrumb_node: Optional[Node] = None,
        markdown: Optional[str] = None,
    ) -> ProtoChunk:
        # logger.info("Creating protochunk %s using %s", chunk_id, data_ids_for(nodes))
        assert all(n for n in nodes), f"Unexpected None in {nodes}"
        markdown = markdown or render_nodes_as_md(nodes)
        markdown = self._replace_table_separators(markdown).strip()

        chunk = ProtoChunk(
            chunk_id_suffix or nodes[0].data_id,
            nodes,
            [n.data_id for n in nodes],
            headings := self._headings_with_doc_name(breadcrumb_node or nodes[0]),
            context_str := "\n".join(headings),
            markdown,
            embedding_str := f"{context_str.strip()}\n\n{remove_links(markdown)}",
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
                col_count = line.count(" |")
                lines[i] = "| " + ("--- | " * col_count)
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
            # TODO only call add_chunk() in _gradually... for comprehension
            self.add_chunk(
                self.create_protochunk(
                    node_with_intro.as_list,
                    chunk_id_suffix=f"{node.data_id}[{i}]",
                    markdown=split,
                    breadcrumb_node=node,
                )
            )

    def compose_summary_text(self, node: Node) -> str:
        if node.data_type == "Paragraph":
            return "(...)\n\n"

        if isinstance(node.data, HeadingSectionNodeData):
            return f"(SUMMARIZED {node.data.rendered_text})\n\n"
        
        if node.data_type == "Heading":
            raise AssertionError(f"Unexpected Heading node {node.data_id}")

        if node.data_type not in ["List", "Table", "ListItem"]:
            return "(SUMMARY)\n\n"

        if not node.has_token() or not (md := node.render()):
            raise AssertionError(f"No summary for {node.data_id}")

        if node.data_type == "List":
            # return f"* (SUMMARIZED LIST {node.data_id})\n\n"
            summary = shorten(remove_links(md.splitlines()[0]), 120, placeholder="...")
            assert summary, f"Unexpected empty summary for {node.data_id}"
            return f"{summary}\n\n"

        if node.data_type == "Table":
            return f"(SUMMARIZED TABLE {node.data_id})\n\n"

        summary = shorten(remove_links(md.splitlines()[0]), 200, placeholder="...")
        assert summary, f"Unexpected empty summary for {node.data_id}"
        return f"({summary})\n\n"

    # TODO: distinguish against full_enough_to_flush()
    def should_summarize(self, node_with_intro: NodeWithIntro) -> bool:
        chunk = self.create_protochunk(node_with_intro.as_list)
        next_nodes_portion = chunk.length / self.max_length
        # Example on https://edd.ca.gov/en/jobs_and_training/FAQs_WARN/
        # Only the 1 larger accordion is chunked by itself and summarized.
        # The smaller accordions are included alongside other accordions.
        # logger.debug("should_summarize: %f %s", next_nodes_portion, [n.data_id for n in node_with_intro])
        return next_nodes_portion > 0.75

    def full_enough_to_flush(self, chunk_buffer: list[Node], breadcrumb_node):
        chunk = self.create_protochunk(chunk_buffer, breadcrumb_node=breadcrumb_node)
        next_nodes_portion = chunk.length / self.max_length
        logger.info("next_nodes_portion = %s", next_nodes_portion)
        # Example on https://edd.ca.gov/en/jobs_and_training/FAQs_WARN/
        # Only the 1 larger accordion is chunked by itself and summarized.
        # The smaller accordions are included alongside other accordions.
        return next_nodes_portion > self.full_enough_threshold

    def should_examine_children(self, next: NodeWithIntro, working_tree: Tree) -> bool:
        "Returns true if next node's children should be examined for chunking"
        if next.node.data_type in "HeadingSection":
            return True
        if next.node.data_type == "List":
            sublists = find_data_type_nodes(next.node, "List")
            if sublists:
                return True
        if next.node.has_children():
            next_nodes_portion = (
                self.text_length(render_nodes_as_md(next.as_list)) / self.max_length
            )
            return next_nodes_portion > 0.75
        return False


# endregion
# region ###### Chunking functions

# block_types = container_types + list_types
# container_types = "Document", "HeadingSection", "ListItem", and probably "TableCell"
#     - we have to update token.children (to render partials) based on tree structure;
# list_types = "List", "Table"
#     - List has "ListItem"s
#     - Table has "TableRow"s (which has "TableCell"s)
#     - we have to update token.children (to render partials) based on tree structure

# leaf_types = non-block_types = no children = "Paragraph", "Heading"
#     - we don't modify token.children; these tokens are frozen as indicated by node.data["freeze_token_children"]


def chunk_tree(input_tree: Tree, config: ChunkingConfig) -> dict[str, ProtoChunk]:
    config.reset()

    # 3 main trees besides the original input tree
    # 1. COMMITTED tree reflects chunked text; summaries replace chunked text; only updated when config.add_chunk() is called
    # 2. (transactional) BUFFER tree contains (uncommitted) possible content for the next chunk
    # 3. (transactional) Transaction (TXN) tree: copy of COMMITTED tree; summaries replace (uncommitted) content in the BUFFER tree

    # Initialize the COMMITTED tree as a full copy of input_tree
    doc_node = copy_subtree("COMMITTED", input_tree.first_child())
    try:
        # Try to chunk as much content as possible, so see if the node's contents fit, including descendants
        while not config.nodes_fit_in_chunk([doc_node], doc_node):
            with assert_no_mismatches(doc_node.tree):
                logger.info("======= Document node %s is too large for one chunk", doc_node.data_id)
                # Start with the first child of the Document node
                n = doc_node.first_child()
                _gradually_chunk_tree_nodes(n, config)
    except EOFError:
        logger.info("No more nodes to chunk")

    next_node = NodeWithIntro(doc_node)
    _chunk_and_summarize_next_nodes(config, next_node)
    return config.chunks


def _gradually_chunk_tree_nodes(orig_node: Node, config: ChunkingConfig):
    committed_tree = orig_node.tree
    # logger.info("CommittedTree: %s", committed_tree.format())
    # logger.info(
    #     "Committed MD: %s", config.create_protochunk([committed_tree.first_child()]).markdown
    # )

    # Transaction tree
    txn_tree = copy_subtree("TXN", committed_tree.first_child()).tree
    node = txn_tree[orig_node.data_id]

    # Empty chunking data structures
    assert node.parent.data_type == "Document"
    buffer_tree = copy_subtree("BUFFER", node.parent, include_descendants=False).tree
    assert buffer_tree.count == 1
    buffer: list[NodeWithIntro] = []  # in chunking_tree
    intro_node: Node | None = None
    while node:
        if node.data["chunked"]:
            logger.info("Skipping chunked node %s", node.data_id)
            p_node = node
            node = next_renderable_node(node)
            if p_node.data_type == "Paragraph":
                committed_tree[p_node.data_id].remove()
                p_node.remove()
                logger.info("nodes %i", txn_tree.count)
            if not node:
                raise EOFError("No more nodes")
            continue

        # keep-with-next for intro nodes
        if node.data["is_intro"]:
            intro_node = node
            node = node.next_sibling()
            assert node, f"Expected next node after intro node {intro_node.data_id}"
            continue

        next_node = NodeWithIntro(node, intro_node)
        logger.info("Next: %s", next_node)
        # logger.info("ChunkingTree: %s", chunking_tree.format())
        # logger.info(
        #     "Chunking MD: %s", config.create_protochunk([chunking_tree.first_child()]).markdown
        # )
        # logger.info("WorkingTree: %s", working_tree.format())
        # logger.info(
        #     "Working MD: %s", config.create_protochunk([working_tree.first_child()]).markdown
        # )
        breadcrumb_node = buffer[0].node if buffer else None
        if config.nodes_fit_in_chunk([buffer_tree.first_child()] + next_node.as_list, breadcrumb_node):
            logger.info("Fits! Adding %s", next_node)
            # Update WORKING tree
            # DON'T update COMMITTED tree

            # Copy data AND sync_tokens
            with assert_no_mismatches(buffer_tree):  # Create new context to copy tokens

                # Copy next_node.intro_node branch to chunking_tree BEFORE copying next_node.node branch
                # intro_node may be a parent (e.g., ListItem) of node (e.g., List)
                new_intro_node = None
                if next_node.intro_node:
                    # There is no one structural relationship: assert next_node.intro_node.parent == next_node.node.parent
                    if not (
                        new_intro_node := find_node(buffer_tree, next_node.intro_node.data_id)
                    ):
                        # Copy next_node.intro_node branch to chunking_tree
                        logger.info(
                            "Copying next_node.intro_node %s to chunking_tree",
                            next_node.intro_node.data_id,
                        )
                        new_intro_node = copy_with_ancestors(
                            next_node.intro_node, buffer_tree, include_descendants=True
                        )

                # Copy next_node.node branch to chunking_tree
                if not (new_node := find_node(buffer_tree, next_node.node.data_id)):
                    logger.info(
                        "Copying next_node.node %s to chunking_tree", next_node.node.data_id
                    )
                    # copy then remove in _summarize_nodes() => move
                    new_node = copy_with_ancestors(
                        next_node.node, buffer_tree, include_descendants=True
                    )

            copied_next_node = NodeWithIntro(new_node, new_intro_node)
            buffer.append(copied_next_node)

            # Since intro_node is included in chunk_buffer, reset it
            intro_node = None
            node = next_renderable_node(node)
            # logger.info("Next node: %s", node)
            if not node:
                raise EOFError("No more nodes")

            pc = config.create_protochunk([buffer_tree.first_child()], breadcrumb_node=breadcrumb_node)
            logger.info("Added to chunking tree %s: %i\n%s", pc.id, pc.length, pc.markdown)

            # logger.info("Updated ChunkingTree: %s", chunking_tree.format())
            # This will remove node in TXN tree
            _summarize_nodes(next_node.as_list, config)
            continue

        # does not fit
        # Following does not modify the working tree or chunk_buffer
        # It may modify the COMMITTED tree and RETURN
        # chunking_tree is used to flush the chunk_buffer to create a chunk
        logger.info("Does not fit: %s + %s", buffer_tree.first_child().data_id, next_node)
        if node.data_type == "Table":
            # Summarize the next node
            # update COMMITTED tree
            orig_next_node = NodeWithIntro(
                committed_tree[next_node.node.data_id],
                committed_tree[next_node.intro_node.data_id] if next_node.intro_node else None,
            )
            _chunk_and_summarize_next_nodes(config, orig_next_node)
        elif node.data_type == "HeadingSection" and config.full_enough_to_flush(next_node.as_list, breadcrumb_node) and config.nodes_fit_in_chunk(next_node.as_list, breadcrumb_node):
            # update COMMITTED tree
            orig_next_node = NodeWithIntro(
                committed_tree[next_node.node.data_id],
                committed_tree[next_node.intro_node.data_id] if next_node.intro_node else None,
            )
            logger.info("Putting HeadingSection %s into separate chunk", next_node)
            config.add_chunk(pc := config.create_protochunk(next_node.as_list, breadcrumb_node=breadcrumb_node))
            logger.debug("Added chunk %s:\n%s", pc.id, pc.markdown)
            _summarize_nodes(orig_next_node.as_list, config)
        elif not node.has_children() and config.full_enough_to_flush(next_node.as_list, breadcrumb_node):
            assert node.data_type in [
                "Paragraph",
                "BlockCode",
            ], f"Unexpected data_type {node.data_type} for leaf node"

            # must split Paragraph n into multiple chunks; doesn't make sense to mix parts of it with other chunks

            # update COMMITTED tree
            orig_next_node = NodeWithIntro(
                committed_tree[next_node.node.data_id],
                committed_tree[next_node.intro_node.data_id] if next_node.intro_node else None,
            )
            # _chunk_and_summarize_next_nodes(config, node_with_intro)
            if config.nodes_fit_in_chunk(next_node.as_list, breadcrumb_node):
                logger.info("Putting Paragraph %s into separate chunk", next_node)
                config.add_chunk(pc := config.create_protochunk(next_node.as_list, breadcrumb_node=breadcrumb_node))
                logger.debug("Added chunk %s:\n%s", pc.id, pc.markdown)
            else:
                # split_paragraph_into_chunks
                logger.info("Splitting Paragraph %s into multiple chunks", next_node)
                config.create_chunks_for_next_nodes(orig_next_node)
            _summarize_nodes(orig_next_node.as_list, config)
        elif config.full_enough_to_flush([buffer_tree.first_child()], breadcrumb_node):
            logger.info("Full enough! %s", [n.data_id for n in buffer_tree])
            # Flush the chunk_buffer to a chunk
            config.add_chunk(pc := config.create_protochunk([buffer_tree.first_child()], breadcrumb_node=breadcrumb_node))
            logger.info("Added chunk %s:\n%s", pc.id, pc.markdown)
            # TODO: del chunk_tree

            # update COMMITTED tree
            for nwi in buffer:
                orig_nodes = NodeWithIntro(
                    committed_tree[nwi.node.data_id],
                    committed_tree[nwi.intro_node.data_id] if nwi.intro_node else None,
                )
                _summarize_nodes(orig_nodes.as_list, config)
        elif next_node.node.has_children() and config.should_examine_children(
            next_node, txn_tree
        ):
            node = node.first_child()
            logger.info("Go to child to %s", node.data_id)
            continue
        else:
            assert node.data_type in [
                "ListItem",
                "List",
                "Table",
                "Paragraph",
                "BlockCode",
            ], f"Unexpected data_type {node.data_type}"
            # Summarize the next node
            # update COMMITTED tree
            orig_next_node = NodeWithIntro(
                committed_tree[next_node.node.data_id],
                committed_tree[next_node.intro_node.data_id] if next_node.intro_node else None,
            )
            _chunk_and_summarize_next_nodes(config, orig_next_node)
        return


def _new_tree_for_partials(
    name: str, orig_node: Node, children_ids: dict[str, Node], intro_node: Optional[Node] = None
) -> NodeWithIntro:
    "Create a new tree keeping only the children in children_ids. Used for creating a chunk for partial lists/tables."
    logger.debug("Creating new tree with children: %s", children_ids.keys())
    block_node = copy_subtree(name, orig_node)  # the List or Table node
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
    candidate_node = _new_tree_for_partials("PARTIAL", node, children_ids, intro_node)
    while children_ids:  # Repeat until all the children are in some chunk
        block_node = candidate_node.node
        logger.info(
            "Trying to fit %s into a chunk by gradually removing children: %s",
            block_node.data_id,
            data_ids_for(block_node.children),
        )
        while not config.nodes_fit_in_chunk(candidate_node.as_list, block_node) and block_node.has_children():
            block_node.last_child().remove()

        if block_node.has_children():
            logger.info("Fits into a chunk: %s", data_ids_for(block_node.children))
            chunks_to_create.append(candidate_node.as_list)
            # Don't need intro_node for subsequent subtrees
            intro_node = None
            for child_node in block_node.children:
                del children_ids[child_node.data_id]
        else:  # List doesn't fit with any children
            # Reset the tree (restore children) and try to summarize the sublists
            candidate_node = _new_tree_for_partials("PARTIAL", node, children_ids, intro_node)
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
                # TODO: Fall back to use RecursiveCharacterTextSplitter
                raise AssertionError(f"{block_node.data_id} should have at least one child")

        if children_ids:  # Prep for the next loop iteration
            # Subsequent subtrees don't need an intro_node
            candidate_node = _new_tree_for_partials("PARTIAL", node, children_ids)

    _create_chunks(config, node, chunks_to_create)


def _summarize_big_listitems(
    candidate_node: NodeWithIntro, config: ChunkingConfig
) -> NodeWithIntro | None:
    assert candidate_node.node.data_type in [
        "List",
        "Table",
    ], f"Unexpected data_type {candidate_node.node.data_type}"
    # TODO: This summarizes ALL list items, not just the big ones. Make this smarter.
    for li in list(candidate_node.node.children):
        assert li.data_type in ["ListItem", "TableRow"], f"Unexpected child {li.id_string}"
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
        ", ".join(data_ids_for(node.children)),
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
        if config.nodes_fit_in_chunk(candidate_node_buffer, candidate_node_buffer[0]):
            node_buffer = candidate_node_buffer
        else:  # candidate_node_buffer doesn't fit
            # Determine whether to summarize node_with_intro or add it to the next chunk

            # For these data_types, node_with_intro (and its descendants) can be chunked and summarized
            can_summarize = node_with_intro.node.data_type in ["HeadingSection", "List", "Table"]
            if can_summarize and config.should_summarize(node_with_intro):
                # logger.warning(
                #     "This logic should be handled in _add_to_buffer_or_summarize() %s",
                #     node_with_intro,
                # )
                # assert (
                #     False
                # ), f"This logic should be handled in _add_to_buffer_or_summarize() {node_with_intro}"
                node_with_intro = _chunk_and_summarize_next_nodes(config, node_with_intro)
                # logger.info("RETURNING from _chunk_and_summarize_next_nodes %s", node_with_intro)
                # return
                # Try again now that node_with_intro has been chunked and summarized.
                # nodes_fit_in_chunk() calls render_nodes_as_md(), which will use the shorter
                # summary text instead of the full text
                candidate_node_buffer = node_buffer + node_with_intro.as_list
                if config.nodes_fit_in_chunk(candidate_node_buffer, candidate_node_buffer[0]):
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
            if config.nodes_fit_in_chunk(node_with_intro.as_list, node_with_intro.node):
                # Reset node_buffer to be node_with_intro
                node_buffer = node_with_intro.as_list.copy()
            else:  # node_with_intro needs to be split into multiple chunks
                config.create_chunks_for_next_nodes(node_with_intro)

    assert not intro_node, f"Was intro_node {intro_node.data_id} added to a node_buffer?"
    if node_buffer:  # Create a chunk with the remaining nodes
        if config.nodes_fit_in_chunk(node_buffer, node_buffer[0]):
            chunks_to_create.append(node_buffer)
        else:
            raise AssertionError(f"node_buffer should always fit: {node_buffer}")

    _create_chunks(config, node, chunks_to_create)


def _chunk_and_summarize_next_nodes(config, node_with_intro: NodeWithIntro) -> NodeWithIntro:
    node = node_with_intro.node
    # See if the node's contents fit, including descendants
    if config.nodes_fit_in_chunk(node_with_intro.as_list, node_with_intro.node):
        config.add_chunk(config.create_protochunk(node_with_intro.as_list))
    elif node.data_type in ["Document", "HeadingSection", "ListItem"]:
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
    elif node.data_type in ["TableRow"]:
        # TODO: split TableRow into multiple chunks
        raise NotImplementedError(f"TableRow node {node.data_id} should be handled")
    else:
        raise AssertionError(f"Unexpected data_type: {node.id_string}")

    # Then set a shorter summary text in a custom attribute
    # assert node.data["summary"] is None, "Summary should not be set yet"
    # node.data["summary"]
    return _summarize_node(NodeWithIntro(node), config)


def _summarize_node(node_with_intro: NodeWithIntro, config: ChunkingConfig) -> NodeWithIntro:
    node = node_with_intro.node
    summary = config.compose_summary_text(node)
    logger.info("Added SUMMARY to %s: %r", node.data_id, summary)

    if node.has_token():
        line_number = node.token.line_number
    elif isinstance(node.data, HeadingSectionNodeData):
        line_number = node.data.line_number
    else:
        raise AssertionError(f"Unexpected node.data type: {node.data_type}")
    p_nodedata = _create_summary_paragraph_node_data(line_number, summary)

    # TODO: remove the intro_node? First, check if it's been included in a chunk; Actually,
    # FIXME: we should mark nodes as they are added into a chunk, then check that before they are removed and at the end.
    # ListItem's should already have an "intro" attribute set.
    # if node_with_intro.intro_node:
    #     node_with_intro.intro_node.remove()

    if node.data_type in ["Document", "List", "HeadingSection", "ListItem"]:
        # Replace all children and add Paragraph summary as the only child
        # for c in list(node_with_intro.node.children):
        # c.remove()
        node_with_intro.node.remove_children()

        # add summary Paragraph
        node.add_child(p_nodedata)
        logger.info("%s children %s", node.data_id, data_ids_for(node.children))

        # Mark the node as chunked so it can be skipped in future chunking
        node.data["chunked"] = True
        return node_with_intro
    elif node.data_type in [
        "Table",
        "Paragraph",
        "BlockCode",
    ]:  # Replace Table with Paragraph summary
        parent = node.parent
        p_node = parent.add_child(p_nodedata, before=node)
        node.remove()
        if parent.has_token():
            pass
        elif isinstance(parent.data, HeadingSectionNodeData):
            pass
        else:
            raise AssertionError(f"Unexpected parent.data type: {parent.data_type}")
        return NodeWithIntro(p_node, node_with_intro.intro_node)
    else:
        raise AssertionError(f"Unexpected data type: {node.data_type}")


def _summarize_nodes(nodes: list[Node], config: ChunkingConfig) -> Node:
    "Assumes nodes are at the same level in the tree, ie have the same parent"
    # TODO: how should we summarize if nodes have different parents? i.e, where should the summary be placed?
    # assert all(n.parent == nodes[0].parent for n in nodes), f"Nodes should have the same parent {[n.parent.data_id for n in nodes]}"
    node = nodes[-1]
    if node.data_type == "Heading":
        logger.info("Skipping summarization of lone Heading node %s", node.data_id)
        assert [
            n.data_id for n in nodes if n != node
        ] == [], f"Unexpected nodes: {[n.data_id for n in nodes if n != node]}"
        return node
    if node.data_type == "List":
        logger.info("Skipping summarization of List node %s", node.data_id)
        parent = node.parent
        for c in nodes:
            c.remove()
        if parent.has_token():
            assert parent.data_type in ["Document", "ListItem", "List", "Table"]
        return node

    logger.debug("Summarizing %s with %s", node.data_id, [n.data_id for n in nodes if n != node])
    # summary = f"(CHUNKED: {node.data_id} with {[n.data_id for n in nodes if n != node]})"
    summary = config.compose_summary_text(node)
    logger.debug("Added SUMMARY to %s: %r", node.data_id, summary)

    # Replace all nodes with Paragraph summary

    p_nodedata = _create_summary_paragraph_node_data(node.data.line_number, summary)

    parent = node.parent
    p_node = parent.add_child(p_nodedata, before=node)
    for c in nodes:
        c.remove()
    if parent.has_token():
        assert parent.data_type in ["Document", "ListItem", "List", "Table"]
    elif isinstance(parent.data, HeadingSectionNodeData):
        pass
    else:
        raise AssertionError(f"Unexpected parent.data type: {parent.data_type}")
    # return NodeWithIntro(p_node, node_with_intro.intro_node)
    return p_node


summary_counter = itertools.count()


def _create_summary_paragraph_node_data(line_number, summary):
    p = block_token.Paragraph(lines=[f"{summary}\n"])
    p.line_number = line_number
    p_nodedata = TokenNodeData(p, id_suffix=f"_summ{next(summary_counter)}")
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


# endregion
