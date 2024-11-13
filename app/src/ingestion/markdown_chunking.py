import itertools
import logging
import textwrap
from copy import copy
from dataclasses import dataclass
from functools import cached_property
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

    def remove(self) -> None:
        for node in self.as_list:
            node.remove()

    def __str__(self) -> str:
        return f"{self.node.data_id}{f' with intro {self.intro_node.data_id}' if self.intro_node else ''}"


@dataclass
class TreeTransaction:
    """
    This represents the state of the trees during chunking.
    There are 3 trees created during chunking:
    1. COMMITTED tree reflects chunked text; summaries replace chunked text; only updated when config.add_chunk() is called
    2. Transaction "TXN" tree: initially a copy of COMMITTED tree; summaries replace (uncommitted) content in the BUFFER tree
    3. BUFFER tree contains (uncommitted) possible content for the next chunk

    The TXN and BUFFER tree act as a scratchpad for creating chunks -- similar to a DB transaction.
    When the scratchpad/transaction is committed (or flushed), the BUFFER tree is used to create a chunk.
    Only when config.add_chunk() is called does the COMMITTED tree get updated.
    """

    committed_tree: Tree
    txn_tree: Tree
    buffer_tree: Tree
    buffer: list[NodeWithIntro]
    breadcrumb_node: Node


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

    def nodes_fit_in_chunk(self, nodes: list[Node], breadcrumb_node: Node) -> bool:
        chunk = self.create_protochunk(nodes, breadcrumb_node=breadcrumb_node)
        logger.debug("Checking fit %s: %s", chunk.length, data_ids_for(nodes))
        return chunk.length < self.max_length

    def add_chunk(self, chunk: ProtoChunk) -> None:
        # Don't add Heading nodes by themselves
        if len(chunk.nodes) == 1 and chunk.nodes[0].data_type in ["Heading"]:
            raise AssertionError(f"Unexpected single Heading node: {chunk.nodes[0].id_string}")

        if chunk.length > self.max_length:
            raise AssertionError(f"{chunk.id} is too large! {chunk.length} > {self.max_length}")
        chunk.id = f"{len(self.chunks)}:{chunk.id}"
        logger.debug("Adding chunk %s created from: %s", chunk.id, data_ids_for(chunk.nodes))
        self.chunks[chunk.id] = chunk

    def create_protochunk(
        self,
        nodes: list[Node],
        *,
        chunk_id_suffix: Optional[str] = None,
        breadcrumb_node: Optional[Node] = None,
        markdown: Optional[str] = None,
    ) -> ProtoChunk:
        assert all(n for n in nodes), f"Unexpected None in {nodes}"
        chunk_id = chunk_id_suffix or nodes[0].data_id
        logger.debug("Creating protochunk %s using %s", chunk_id, data_ids_for(nodes))

        markdown = markdown or render_nodes_as_md(nodes)
        markdown = self._replace_table_separators(markdown).strip()

        chunk = ProtoChunk(
            chunk_id,
            nodes,
            [n.data_id for node in nodes for n in node.iterator(add_self=True)],
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

    def add_chunks_for_node(self, node_with_intro: NodeWithIntro) -> None:
        node = node_with_intro.node
        assert node.data_type not in [
            "HeadingSection",
            "ListItem",
            "List",
            "Table",
        ], f"{node.data_type} should be handled outside this method: {node.id_string}"

        temp_chunk = self.create_protochunk(node_with_intro.as_list, breadcrumb_node=node)
        logger.warning("If this is called often, use a better text splitter for %s", node.id_string)
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

    def compose_summary_text(self, node: Node) -> str:
        if node.data_type == "Paragraph":
            return "(...)\n\n"

        if isinstance(node.data, HeadingSectionNodeData):
            return f"(CHUNKED {node.data.rendered_text.strip()})\n\n"

        if node.data_type == "Heading":
            return f"(HEADING {node.data['raw_text']})\n\n"
            # raise AssertionError(f"Unexpected Heading node {node.data_id}")

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

    def full_enough_to_commit(self, chunk_buffer: list[Node], breadcrumb_node: Node) -> bool:
        chunk = self.create_protochunk(chunk_buffer, breadcrumb_node=breadcrumb_node)
        next_nodes_portion = chunk.length / self.max_length
        # Example on https://edd.ca.gov/en/jobs_and_training/FAQs_WARN/
        # Only the 1 larger accordion is chunked by itself and summarized.
        # The smaller accordions are included alongside other accordions.
        return next_nodes_portion > self.full_enough_threshold

    def should_examine_children(self, next: NodeWithIntro, txn: TreeTransaction) -> bool:
        """
        Returns True if next node's (shorter-length) children should be examined for adding to a chunk.
        Called when next node (and all its children) is too large to fit into an existing chunk.
        """
        # The following heuristics tries to maximize the length of chunks
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


def chunk_tree(input_tree: Tree, config: ChunkingConfig) -> dict[str, ProtoChunk]:
    config.reset()

    # Initialize the COMMITTED tree as a full copy of input_tree
    doc_node = copy_subtree("COMMITTED", input_tree.first_child())
    try:
        # Try to chunk as much content as possible, so see if the node's contents fit, including descendants
        tree = doc_node.tree
        while not config.nodes_fit_in_chunk([doc_node], doc_node):
            with assert_no_mismatches(tree):
                logger.debug("=== Document node %s is too large for one chunk", doc_node.data_id)
                logger.debug(
                    "COMMITTED tree:\n%s\n%r (length %i)\n%s",
                    *_format_tree_and_markdown(tree, config),
                )
                _gradually_chunk_tree_nodes(tree, config)

                # Remove the summary paragraph from the tree as it provides no value at this time
                chunked = tree.find_all(
                    match=lambda n: n.data["chunked"] and n.data_type == "Paragraph"
                )
                for chunked_node in chunked:
                    # It's possible a parent node already removed the chunked_node, so check if it's still in the tree
                    if chunked_node.tree:
                        chunked_node.remove()

    except EOFError:
        logger.debug("No more nodes to chunk")

    next_node = NodeWithIntro(doc_node)
    _add_chunks_and_summarize_node(config, next_node)

    # Ensure all nodes are in some chunk
    input_nodes = {n.data_id for n in input_tree.iterator()} - {doc_node.data_id}
    chunked_nodes = {id for pc in config.chunks.values() for id in pc.data_ids} - {doc_node.data_id}
    unchunked_nodes = input_nodes - chunked_nodes
    assert not unchunked_nodes, f"Expected {unchunked_nodes} to be chunked"
    return config.chunks


def _format_tree_and_markdown(tree: Tree, config: ChunkingConfig) -> tuple[str, str, int, str]:
    pc = config.create_protochunk([tree.first_child()])
    return (tree.format(), pc.id, pc.length, pc.markdown)


def _gradually_chunk_tree_nodes(committed_tree: Tree, config: ChunkingConfig):
    """
    The _general_ algorithm is:
    - Consider the next node in the TXN tree
    - If it fits in the BUFFER, add it to the BUFFER
    - If it doesn't fit, summarize the node in a new chunk and replace the original node content with a summary
    - Repeat with the next node and once the BUFFER is full enough,
      create a chunk from the BUFFER and replace the original node content with a summary
    - Whenever a chunk is created (for any reason), reset and restart the process from the root
      because creating a chunk reduces the content and may allow more summary nodes to fit where it didn't before
      - The new chunk is reflected in the COMMITTED tree, which is copied to the TXN tree

    Notes:
      - Content in the BUFFER as a whole _always_ fits in a chunk
      - Content in the BUFFER may not necessarily become a chunk if a chunk is created for another reason.
    """

    # Create Transaction tree from COMMITTED tree
    txn_tree = copy_subtree("TXN", committed_tree.first_child()).tree
    assert committed_tree.count == txn_tree.count
    doc_node = txn_tree.first_child()
    assert doc_node.data_type == "Document"

    # Initialize empty BUFFER data structures
    buffer_tree = copy_subtree("BUFFER", txn_tree.first_child(), include_descendants=False).tree
    assert buffer_tree.count == 1
    # This buffer will be used to update the COMMITTED tree once the buffer is committed to a chunk
    buffer: list[NodeWithIntro] = []

    # Start with the first child of the Document node
    node = doc_node.first_child()
    intro_node: Node | None = None
    while node:
        if node.data["chunked"]:
            logger.debug("Skipping chunked node %s", node.data_id)
            chunked_node = node
            # Determine the next node BEFORE removing chunked_node
            node = next_renderable_node(node)
            if chunked_node.data_type == "Paragraph":
                # Remove the summary paragraph from the tree as it provides no value at this time
                #     committed_tree[chunked_node.data_id].remove()
                chunked_node.remove()
            continue

        # keep-with-next for intro nodes
        if node.data["is_intro"]:
            intro_node = node
            node = node.next_sibling()
            assert node, f"Expected next_sibling after intro node {intro_node.data_id}"
            assert (
                node.data["intro_data_id"] == intro_node.data_id
            ), f"{node.data_id}: Unexpected intro doesn't match: {node.data["intro_data_id"]} != {intro_node.data_id}"
            continue

        next_node = NodeWithIntro(node, intro_node)
        logger.debug("Next: %s", next_node)
        logger.debug(
            "BUFFER tree:\n%s\n%r (length %i)\n%s",
            *_format_tree_and_markdown(buffer_tree, config),
        )
        logger.debug(
            "TXN tree:\n%s\n%r (length %i)\n%s",
            *_format_tree_and_markdown(txn_tree, config),
        )

        if node.data_id == "T_25":
            pass

        # Set the breadcrumb node from which the headings for the chunk will be extracted
        breadcrumb_node = buffer[0].node if buffer else node

        # Check if candidate_buffer (BUFFER + next_node) fits in a chunk
        candidate_buffer = [buffer_tree.first_child()] + next_node.as_list
        if config.nodes_fit_in_chunk(candidate_buffer, breadcrumb_node):
            logger.debug("Fits! Adding %s", next_node)
            # Update TXN tree but not the COMMITTED tree since the buffer is not yet ready to be chunked.
            # Move next_node to the BUFFER tree by copying it to the buffer_tree,
            # then in the TXN tree, replacing the original node with a summary.
            copied_next_node = _copy_next_node_to(buffer_tree, next_node)
            # Add copied_next_node in the buffer_tree to the buffer
            buffer.append(copied_next_node)
            # Since intro_node is included in chunk_buffer, reset intro_node
            # so that it's not included in the subsequent next_node
            intro_node = None

            # Determine the next node BEFORE modifying/summarizing next_node.node
            node = next_renderable_node(node)
            # Replace next_node in TXN tree with a summary
            _summarize_node(next_node, config)
            continue

        # candidate_buffer does not fit so determine an action.
        logger.debug("Does not fit: %s + %s", data_ids_for(buffer_tree.iterator()), next_node)
        # If the action results in a new chunk, then the COMMITTED tree is modified, so restart. This is usually the case.
        txn = TreeTransaction(committed_tree, txn_tree, buffer_tree, buffer, breadcrumb_node)
        chunk_created = _handle_does_not_fit(config, txn, next_node)
        if chunk_created:
            # Reset and restart from the root, since creating a chunk reduces the content,
            # which may allow higher-level nodes (with some summarized child nodes) to fit where they didn't before
            return

        # Go deeper into the tree to find smaller content to include in the buffer
        node = node.first_child()
    raise EOFError("No more nodes")


class NextNodeCache:
    def __init__(
        self,
        config: ChunkingConfig,
        committed_tree: Tree,
        next_node: NodeWithIntro,
        breadcrumb_node: Node,
    ) -> None:
        self.config = config
        self.committed_tree = committed_tree
        self.next_node = next_node
        self.breadcrumb_node = breadcrumb_node

        self.committed_nodes = _nodes_in_committed_tree(self.next_node, self.committed_tree)
        self._committed_breadcrumb_node = self.committed_tree[self.breadcrumb_node.data_id]

    @cached_property
    def next_node_alone_protochunk(self) -> ProtoChunk:
        "Returns a ProtoChunk for the next_node by itself"
        return self.config.create_protochunk(
            self.committed_nodes.as_list, breadcrumb_node=self._committed_breadcrumb_node
        )

    @cached_property
    def next_node_alone_fits(self) -> bool:
        "Returns True if next_node fits in a chunk by itself, i.e., ignoring what's in the buffer?"
        return self.config.nodes_fit_in_chunk(
            self.committed_nodes.as_list, breadcrumb_node=self._committed_breadcrumb_node
        )

    @cached_property
    def next_node_alone_large_enough_to_commit(self) -> bool:
        "Returns True if next_node is large enough to commit by itself, i.e., ignoring what's in the buffer?"
        return self.config.full_enough_to_commit(
            self.committed_nodes.as_list, breadcrumb_node=self._committed_breadcrumb_node
        )


def _nodes_in_committed_tree(next_node: NodeWithIntro, committed_tree: Tree) -> NodeWithIntro:
    return NodeWithIntro(
        committed_tree[next_node.node.data_id],
        committed_tree[next_node.intro_node.data_id] if next_node.intro_node else None,
    )


def _handle_does_not_fit(
    config: ChunkingConfig, txn: TreeTransaction, next_node: NodeWithIntro
) -> bool:
    "Returns True if a chunk was created"
    cache = NextNodeCache(config, txn.committed_tree, next_node, txn.breadcrumb_node)
    data_type = next_node.node.data_type

    if data_type == "Table":
        # For a Table node that doesn't fit when appended to the buffer, just chunk it by itself and summarize it.
        # We can revisit this to determine if a Table should be included with other nodes in the buffer.
        # Update COMMITTED tree
        _add_chunks_and_summarize_node(config, cache.committed_nodes)
    elif (
        data_type == "HeadingSection"
        and cache.next_node_alone_fits
        and cache.next_node_alone_large_enough_to_commit
    ):
        # If an entire HeadingSection is sufficiently large by itself and fits in a chunk by itself, then create a chunk for it
        logger.debug("Putting HeadingSection %s into separate chunk", next_node)
        # Commit next_node as a chunk by itself, ignoring the buffer
        config.add_chunk(cache.next_node_alone_protochunk)
        # Update COMMITTED tree, adding summaries to replace the chunked nodes
        _summarize_node(cache.committed_nodes, config)
    elif not next_node.node.has_children() and cache.next_node_alone_large_enough_to_commit:
        # If next_node is a large-enough leaf node, chunk (possibly into multiple chunks) and summarize it
        # For such large text blocks, doesn't make sense to mix parts of it with other chunks.
        assert data_type in [
            "Paragraph",
            "BlockCode",
        ], f"Unexpected data_type {data_type} for leaf node"

        # Create chunk(s) for next_node by itself, ignoring the buffer
        if cache.next_node_alone_fits:
            logger.debug("Putting %s into its own chunk", next_node)
            config.add_chunk(cache.next_node_alone_protochunk)
        else:
            logger.debug("Splitting %s into multiple chunks", next_node)
            config.add_chunks_for_node(cache.committed_nodes)
        # Update COMMITTED tree, adding summaries to replace the chunked nodes
        _summarize_node(cache.committed_nodes, config)
    elif config.full_enough_to_commit(
        [txn.buffer_tree.first_child()], breadcrumb_node=txn.breadcrumb_node
    ):
        # If the buffer is full enough, create a chunk from the buffer
        logger.debug("Full enough! %s", [n.data_id for n in txn.buffer_tree])
        # Flush the buffer to a chunk
        config.add_chunk(
            config.create_protochunk(
                [txn.buffer_tree.first_child()], breadcrumb_node=txn.breadcrumb_node
            )
        )

        # Update COMMITTED tree, adding summaries to replace the chunked nodes
        for nwi in txn.buffer:
            committed_nodes = _nodes_in_committed_tree(nwi, txn.committed_tree)
            _summarize_node(committed_nodes, config)
    elif next_node.node.has_children() and config.should_examine_children(next_node, txn):
        # If next_node has children and should_examine_children(),
        # then go deeper into the tree to assess smaller content to include in the buffer
        return False
    else:
        assert data_type in [
            "ListItem",
            "List",
            "Paragraph",
            "BlockCode",
        ], f"Unexpected data_type {data_type}"
        # Chunk and summarize next_node, splitting as needed
        # Update COMMITTED tree
        _add_chunks_and_summarize_node(config, cache.committed_nodes)
    return True


def _copy_next_node_to(buffer_tree: Tree, next_node: NodeWithIntro) -> NodeWithIntro:
    "Returns copied next_node in the buffer_tree"
    with assert_no_mismatches(buffer_tree):
        # Copy next_node.intro_node branch to buffer_tree BEFORE copying next_node.node branch
        # in case intro_node is a parent (e.g., ListItem) of next_node.node (e.g., a sub-List)
        new_intro_node = None
        if next_node.intro_node:
            # If intro_node is not in the buffer_tree, copy it over
            if not (new_intro_node := find_node(buffer_tree, next_node.intro_node.data_id)):
                # Copy next_node.intro_node branch to buffer_tree
                new_intro_node = copy_with_ancestors(
                    next_node.intro_node, buffer_tree, include_descendants=True
                )

        # If it doesn't exist, copy next_node.node branch to buffer_tree
        if not (new_node := find_node(buffer_tree, next_node.node.data_id)):
            new_node = copy_with_ancestors(next_node.node, buffer_tree, include_descendants=True)
        return NodeWithIntro(new_node, new_intro_node)


def split_list_or_table_node_into_chunks(
    node_with_intro: NodeWithIntro, config: ChunkingConfig
) -> None:
    """
    Copy the node's subtree, then gradually remove the last child until the content fits.
    If that doesn't work, summarize each sublist.
    """
    node = node_with_intro.node
    intro_node = node_with_intro.intro_node
    assert node.data_type in ["List", "Table"]
    assert node.children, f"{node.id_string} should have children to split"
    logger.info("Splitting large %s into multiple chunks", node.id_string)

    chunks_to_create: list[list[Node]] = []
    children_ids = {c.data_id: c for c in node.children}

    # Only the first subtree will have the intro_node, if it exists
    candidate_node = _new_tree_for_partials("PARTIAL", node, children_ids, intro_node)
    while children_ids:  # Repeat until all the children are in some chunk
        block_node = candidate_node.node
        logger.debug(
            "Trying to fit %s into a chunk by gradually removing children: %s",
            block_node.data_id,
            data_ids_for(block_node.children),
        )
        while (
            not config.nodes_fit_in_chunk(candidate_node.as_list, block_node)
            and block_node.has_children()
        ):
            block_node.last_child().remove()

        if block_node.has_children():
            logger.debug("Fits into a chunk: %s", data_ids_for(block_node.children))
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
                logger.debug(
                    "Summarized big list items into %s: children_ids=%s",
                    summarized_node,
                    children_ids.keys(),
                )
                continue  # Try again with the reset tree and candidate_node
            else:
                # TODO: Fall back to use RecursiveCharacterTextSplitter
                raise AssertionError(f"{block_node.data_id} should have at least one child")

        if children_ids:  # Prep for the next loop iteration
            # Subsequent subtrees don't need an intro_node
            candidate_node = _new_tree_for_partials("PARTIAL", node, children_ids)

    _add_chunks_from_partitions(config, node, chunks_to_create)


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
        if config.full_enough_to_commit([li], breadcrumb_node=candidate_node.node):
            logger.debug("Summarizing big list item %s", li.data_id)
            li_candidate = _add_chunks_and_summarize_node(config, li_candidate)
            return li_candidate
    return None


def split_heading_section_into_chunks(node: Node, config: ChunkingConfig) -> None:
    assert node.data_type in ["Document", "HeadingSection", "ListItem"]
    logger.debug(
        "Splitting large %s into chunks: children nodes=%s",
        node.id_string,
        data_ids_for(node.children),
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
            is_summarizable_type = node_with_intro.node.data_type in [
                "HeadingSection",
                "List",
                "Table",
            ]
            if is_summarizable_type and config.full_enough_to_commit(
                node_with_intro.as_list, breadcrumb_node=node
            ):
                node_with_intro = _add_chunks_and_summarize_node(config, node_with_intro)
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
                config.add_chunks_for_node(node_with_intro)

    assert not intro_node, f"Was intro_node {intro_node.data_id} added to a node_buffer?"
    if node_buffer:  # Create a chunk with the remaining nodes
        if config.nodes_fit_in_chunk(node_buffer, node_buffer[0]):
            chunks_to_create.append(node_buffer)
        else:
            raise AssertionError(f"node_buffer should always fit: {node_buffer}")

    _add_chunks_from_partitions(config, node, chunks_to_create)


def _add_chunks_and_summarize_node(
    config: ChunkingConfig, node_with_intro: NodeWithIntro
) -> NodeWithIntro:
    "Creates chunk(s) and may split node_with_intro into multiple chunks"
    node = node_with_intro.node
    # See if the node's contents fit, including descendants
    if config.nodes_fit_in_chunk(node_with_intro.as_list, node_with_intro.node):
        config.add_chunk(config.create_protochunk(node_with_intro.as_list))
    elif node.data_type in ["Document", "HeadingSection", "ListItem"]:
        # ListItem can have similar children as HeadingSection
        logger.debug("%s is too large for one chunk", node.data_id)
        # TODO: Do something with the intro_node if it exists
        split_heading_section_into_chunks(node, config)
    elif node.data_type in ["List", "Table"]:
        # List and Table nodes are container nodes and never have their own content.
        # Renderable content are in their children, which are either ListItem or TableRow nodes.
        # Split these specially since they can have an intro sentence (and table header)
        # to include for each chunk
        # The intro_node will be rendered fully in the first of the split chunks
        # Remaining chunks will use the short node.data["intro"] text instead
        split_list_or_table_node_into_chunks(node_with_intro, config)
    elif node.data_type in ["TableRow"]:
        # TODO: split TableRow into multiple chunks
        raise NotImplementedError(f"TableRow node {node.data_id} should be handled")
    else:
        raise AssertionError(f"Unexpected data_type: {node.id_string}")

    # Then set a shorter summary text in a custom attribute
    # assert node.data["summary"] is None, "Summary should not be set yet"
    # node.data["summary"]
    return _summarize_node(node_with_intro, config)


def _summarize_node(node_with_intro: NodeWithIntro, config: ChunkingConfig) -> NodeWithIntro:
    node = node_with_intro.node
    if node.data["is_summary"]:
        raise AssertionError(f"Node {node.data_id} is already summarized")

    if node.data_type == "ThematicBreak":
        # ThematicBreak example: horizontal rule
        node.data["chunked"] = True
        assert (
            not node_with_intro.intro_node
        ), f"Unexpected intro_node {node_with_intro.intro_node!r} for {node.id_string}"
        return node_with_intro

    summary = config.compose_summary_text(node)
    logger.debug("Adding SUMMARY to %s: %r", node.data_id, summary)
    p_nodedata = _create_summary_paragraph_node_data(node.data.line_number, summary)

    if node.data_type in ["Document", "List", "HeadingSection", "ListItem", "Quote"]:
        # For these container-like data_types, keep the node's data_type to retain its semantic meaning
        # Replace all children with a Paragraph summary as the only child
        node.remove_children()
        # Add summary Paragraph
        node.add_child(p_nodedata)
        # Mark the node as chunked so it can be skipped in future chunking
        node.data["chunked"] = True
        # Remove only the intro_node, if it exists
        if node_with_intro.intro_node:
            node_with_intro.intro_node.remove()
        return NodeWithIntro(node)
    elif node.data_type in ["Heading", "Paragraph", "BlockCode", "Table"]:
        # For these data_types, replace them with a summary Paragraph
        parent = node.parent
        p_node = parent.add_child(p_nodedata, before=node_with_intro.node)
        if parent.has_token():
            assert parent.data_type in ["Document", "ListItem", "List", "Table"]
        elif isinstance(parent.data, HeadingSectionNodeData):
            pass
        else:
            raise AssertionError(f"Unexpected parent.data_type: {parent.id_string}")
        # Remove both node and intro_node
        node_with_intro.remove()
        return NodeWithIntro(p_node)
    else:
        raise AssertionError(f"Unexpected data type: {node.id_string}")


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
    p_nodedata["is_summary"] = True
    return p_nodedata


def _add_chunks_from_partitions(
    config: ChunkingConfig, node: Node, partitions: list[list[Node]]
) -> None:
    "Create chunks based on partitions, which are splits of the node's children."
    logger.debug(
        "Creating chunks for %s: %s",
        node.data_id,
        [
            [n.data_id for node in nodes for n in node.iterator(add_self=True)]
            for nodes in partitions
        ],
    )
    if len(partitions) == 1:
        chunk_nodes = partitions[0]
        if len(chunk_nodes) == 1 and chunk_nodes[0].data_type in ["Heading"]:
            # Don't chunk lone heading nodes
            return
        chunk = config.create_protochunk(chunk_nodes, chunk_id_suffix=f"{node.data_id}")
        config.add_chunk(chunk)
    else:
        # If there are multiple splits for the node, use a different chunk_id_suffix to make it obvious.
        for i, chunk_nodes in enumerate(partitions):
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
