import logging
import textwrap
from copy import copy
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Sequence

from nutree import Node, Tree

from src.ingestion.markdown_tree import (
    TokenNodeData,
    get_parent_headings_md,
    normalize_markdown,
    render_subtree_as_md,
)

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


def copy_subtree(node: Node) -> Tree:
    subtree = Tree(f"{node.data_id} subtree", shadow_attrs=True)
    # Copy the nodes and descendants; this does not deep-copy node.data objects
    # For some reason, copy_to() assigns a random data_id to the new node in subtree
    new_node = node.copy_to(subtree, deep=True)

    # Set the data_id back to the original, along with creating copies of objects
    for n in subtree:
        n.set_data(copy(n.data), data_id=n.data.data_id)
        n.data.tree = subtree
        if isinstance(n.data, TokenNodeData):
            are_tokens_frozen = n.data["freeze_token_children"] or find_closest_ancestor(
                n,
                lambda p: isinstance(p.data, TokenNodeData) and p.data["freeze_token_children"],
            )
            # Why check for are_tokens_frozen? Because calling copy() on Paragraph tokens doesn't work.
            # Fortunately if we use "freeze_token_children", then we don't need to copy Paragraph tokens
            if not are_tokens_frozen:
                n.data.token = copy(n.data.token)

    assert subtree[node.data_id], f"Expected data_id {node.data_id!r} for {subtree.first_child()}"

    # Now that copies of node.data and node.data.token are created, update references to the tokens
    # Update all node.data.token.children to point to the new token objects in the subtree
    for n in new_node.iterator(add_self=True):
        if isinstance(n.data, TokenNodeData) and not n.data["freeze_token_children"]:
            n.data.token.children = [
                c.token for c in n.children if isinstance(c.data, TokenNodeData)
            ]
    # At this point, no object in the subtree should be pointing to objects in the original tree,
    # except for tokens associated with "freeze_token_children". We are free to modify the subtree.
    return subtree


def find_closest_ancestor(node: Node, does_match: Callable[[Node], bool]) -> Node:
    "Return the first parent/ancestor node that matches the does_match function"
    while node.parent:
        if does_match(node.parent):
            return node.parent
        node = node.parent
    return None


@dataclass
class ProtoChunk:
    id: str
    headings: list[str]
    markdown: str  # Markdown content of the chunk
    # to_embed: str  # string to embed


class ChunkingConfig:

    def __init__(self, max_char_length: int) -> None:
        self.max_char_length = max_char_length
        self.chunks: dict[str, ProtoChunk] = {}

    def fits_in_chunk(self, markdown: str) -> bool:
        return len(markdown) < self.max_char_length

    def nodes_fit_in_chunk(self, nodes: Sequence[Node]) -> bool:
        return self.fits_in_chunk(nodes_as_markdown(nodes))

    def create_chunk(
        self,
        nodes: Sequence[Node],
        chunk_id_suffix: Optional[str] = None,
        breadcrumb_node: Optional[Node] = None,
    ) -> ProtoChunk:
        if not chunk_id_suffix:
            chunk_id_suffix = nodes[0].data_id
        chunk_id = f"{len(self.chunks)}:{chunk_id_suffix}"
        chunk = ProtoChunk(
            chunk_id,
            get_parent_headings_md(breadcrumb_node or nodes[0]),
            nodes_as_markdown(nodes),
        )
        print(
            f"Created chunk {chunk_id}: {len(nodes)} nodes, len {len(chunk.markdown)}: {shorten(chunk.markdown, 120)!r}"
        )
        if not self.fits_in_chunk(chunk.markdown):
            raise AssertionError(f"{chunk_id} Too long {len(chunk.markdown)}: {chunk.markdown}")
        self.chunks[chunk.id] = chunk
        return chunk

    def create_chunks_for_next_nodes(self, node: Node, intro_node: Optional[Node] = None) -> None:
        # TODO: Handle this case by splitting the 2 nodes (optional intro node + other node) into smaller chunks
        raise AssertionError(
            f"{node.parent.data_id}: These node(s) cannot fit into a single chunk:"
            f" {node.data_id} {intro_node.data_id if intro_node else ''}"
        )
        # TODO: Add to self.chunks
        # self.chunks[chunk.id] = chunk

    def compose_summary_text(self, node: Node) -> str:
        return (
            shorten(node.render().splitlines()[0], 100, placeholder="...")
            + f" (SUMMARY of {node.data_id})\n"
        )


def nodes_as_markdown(nodes: Sequence[Node]) -> str:
    # Don't render Heading nodes by themselves
    if len(nodes) == 1 and nodes[0].data_type in ["Heading"]:
        return ""

    md_list: list[str] = []
    for node in nodes:
        # node.data["summary"] is set when node is chunked
        node_md = node.data["summary"] or render_subtree_as_md(node, normalize=True)
        md_list.append(node_md)
    return normalize_markdown("".join(md_list))


def chunk_tree(tree: Tree, config: ChunkingConfig) -> None:
    # Reset the tree for chunking
    for n in tree:
        for attr in ["summary"]:
            n.data[attr] = None

    hierarchically_chunk_nodes(tree.first_child(), config)


def hierarchically_chunk_nodes(node: Node, config: ChunkingConfig) -> None:
    assert (
        not isinstance(node.data, TokenNodeData) or node.is_block_token()
    ), f"Expecting block-token, not {node.token}"

    # Try to chunk as much content as possible, so see if the node's contents fit, including descendants
    if config.nodes_fit_in_chunk([node]):
        config.create_chunk([node])
        # Don't need to recurse through child nodes
        return

    if node.data_type in ["List", "Table"]:
        # Split these specially since they have an intro sentence and markdown rendering is tricky
        split_lt_node_into_chunks(node, config)
        return

    if node.data_type in ["Document", "HeadingSection"]:
        # The remainder of this code deals with splitting up node's content into smaller chunks
        logger.info("%s is too large for one chunk", node.data_id)
        split_heading_section_into_chunks(node, config)
        return

    raise AssertionError(f"Unexpected data_type: {node.id_string}")


def split_lt_node_into_chunks(node: Node, config: ChunkingConfig) -> None:
    assert node.data_type in ["List", "Table"]
    print(f"Splitting into chunks: {node.id_string}")
    # FIXME: determine size of each split using fits_in_chunk()
    splits = _partition_list(list(map(lambda c: c.data_id, node.children)), 2)
    for i, split in enumerate(splits):
        # Copy the whole subtree, then remove children not in the split
        subtree = copy_subtree(node)
        block_node = subtree.first_child()
        # show_intro should be True since block_node's content is being split
        block_node.data["show_intro"] = True

        nodes_to_remove = [
            child_node for child_node in block_node.children if child_node.data_id not in split
        ]
        for not_in_split in nodes_to_remove:
            block_node.token.children.remove(not_in_split.token)
            not_in_split.remove()

        chunk_id_suffix = f"{block_node.data_id}[{i}]:{block_node.first_child().data_id}"
        config.create_chunk([block_node], chunk_id_suffix=chunk_id_suffix, breadcrumb_node=node)


def _partition_list(lst: list[Node], n: int) -> Iterable[list[Node]]:
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def split_heading_section_into_chunks(node: Node, config: ChunkingConfig) -> None:
    assert node.data_type in ["Document", "HeadingSection"]
    print(
        f"Splitting into chunks: {node.id_string} with children:",
        # Reduce verbosity by excluding BlankLine nodes
        ", ".join([c.data_id for c in node.children if c.data_type != "BlankLine"]),
    )
    # Iterate through each child node, adding them to node_buffer
    # Before chunk capacity is exceeded, flush node_buffer to a chunk.
    # At any time, the contents of node_buffer should fit into a chunk,
    # so check if nodes_fit_in_chunk(node_buffer + [nodes]) before adding to node_buffer.
    node_buffer: list[Node] = []
    intro_paragraph_node = None
    chunks_to_create: list[list[Node]] = []
    for c in node.children:
        logger.debug("%s: Adding child node %s", node.data_id, c.data_id)

        if c.data["is_intro"] and c.data_type == "Paragraph":
            intro_paragraph_node = c
            continue

        if intro_paragraph_node:
            # Keep the (previous) intro paragraph with c
            next_nodes = [intro_paragraph_node, c]
            intro_paragraph_node = None
        else:
            # No intro paragraph, so only need to assess adding c
            next_nodes = [c]

        candidate_node_list = node_buffer + next_nodes
        if config.nodes_fit_in_chunk(candidate_node_list):
            node_buffer.extend(next_nodes)
        else:  # next_nodes doesn't fit, so summarize nodes that can be chunked by themselves
            if c.data_type in ["HeadingSection", "List", "Table"]:
                # For these data_types, c (and all its descendants) can be chunked by itself
                hierarchically_chunk_nodes(c, config)
                # Then set a shorter summary text in a custom attribute
                if not c.data["summary"]:
                    c.data["summary"] = config.compose_summary_text(c)
                    logger.debug("Added summary to %s: %s", c.data_id, c.data["summary"])

            # Try again now that c has been chunked and has a summary.
            # nodes_to_markdown() will now use the shorter summary text instead of the full text.
            if config.nodes_fit_in_chunk(candidate_node_list):
                node_buffer.extend(next_nodes)
            else:  # candidate_node_list still doesn't fit even using the summary!
                # Split candidate_node_list (node_buffer + next_nodes) across multiple chunks
                # 1. put node_buffer in its own chunk
                if node_buffer:
                    # Create a chunk with the current node_buffer contents
                    chunks_to_create.append(node_buffer.copy())
                    # and reset node_buffer
                    node_buffer = []

                # 2. Handle next_nodes
                # Check if next_nodes can be the new node_buffer
                if config.nodes_fit_in_chunk(next_nodes):
                    # Reset and initialize node_buffer with next_nodes
                    node_buffer = next_nodes
                else:  # next_nodes needs to be split into multiple chunks
                    config.create_chunks_for_next_nodes(c, intro_paragraph_node)
                    node_buffer = []

    if node_buffer:  # Create a chunk with the remaining nodes
        if config.nodes_fit_in_chunk(node_buffer):
            chunks_to_create.append(node_buffer.copy())
        else:
            raise AssertionError(
                "Should not occur since nothing should be added to node_buffer that would exceed chunk capacity."
            )

    _create_chunks(config, node, chunks_to_create)


def _create_chunks(config: ChunkingConfig, node: Node, chunks_to_create: list[list[Node]]) -> None:
    if len(chunks_to_create) > 1:
        for i, chunk_nodes in enumerate(chunks_to_create):
            # The chunk id identifies the node being split, the split number, and the first node in the chunk
            config.create_chunk(
                chunk_nodes, chunk_id_suffix=f"{node.data_id}[{i}]:{chunk_nodes[0].data_id}"
            )
    else:
        assert len(chunks_to_create) == 1
        config.create_chunk(chunks_to_create[0])
