import logging
import textwrap
from copy import copy
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from nutree import Node, Tree

from src.ingestion.markdown_tree import (
    get_parent_headings_md,
    TokenNodeData,
    render_subtree_as_md,
    normalize_markdown,
)


logger = logging.getLogger(__name__)


def heading_breadcrumb_for(node: Node) -> str | None:
    assert node
    if parent_headings := get_parent_headings_md(node):
        # print("Parent Headings: ", node.data, "\n  ", parent_headings)
        return "\n".join(parent_headings) + "\n---\n"
    else:
        return None


def nodes_as_markdown(
    nodes: Sequence[Node], breadcrumb_node: Optional[Node] = None, add_context: bool = False
) -> str:
    # Don't render Heading nodes by themselves
    if len(nodes) == 1 and nodes[0].data_type in ["Heading"]:
        return ""

    context_str = heading_breadcrumb_for(breadcrumb_node or nodes[0]) if add_context else ""

    md_list: list[str] = []
    if context_str:
        md_list.append(context_str)
    for node in nodes:
        # node.data["summary"] is set when node is chunked
        node_md = node.data["summary"] or render_subtree_as_md(node, normalize=True)
        md_list.append(node_md)
    return normalize_markdown("".join(md_list))


def shorten(body: str, char_limit: int, placeholder="...") -> str:
    new_body = []
    char_remaining = char_limit
    for line in body.splitlines()[:2]:
        line = textwrap.shorten(
            line, char_remaining, placeholder=placeholder, break_long_words=False
        )
        new_body.append(line)
        char_remaining -= len(line)
        if char_remaining < len(placeholder):
            break
    return "\n".join(new_body)


def add_summary_text(node: Node) -> str:
    if not (summary := node.data["summary"]):
        # TODO: make this configurable
        summary = (
            shorten(node.render().splitlines()[0], 100, placeholder="...")
            + f" (SUMMARY of {node.data_id})\n"
        )
        # Create custom attribute to store the summary
        logger.info("Add summary to %s: %s", node.data_id, summary)
        node.data["summary"] = summary
    else:
        logger.info("Skipping %s: already has summary %s", node.data_id, summary)
    return summary


def capacity_used(markdown: str) -> float:
    return len(markdown) / 630


@dataclass
class Chunk:
    id: str
    headings: list[str]
    markdown: str  # Markdown content of the chunk
    # to_embed: str  # string to embed


all_chunks: dict[str, Chunk] = {}


def chunk_tree(tree: Tree):
    all_chunks.clear()
    for n in tree:
        n.data["chunked"] = None
        n.data["summary"] = None

    hierarchically_chunk_nodes(tree.first_child())
    return all_chunks


def create_chunk(
    nodes: Sequence[Node],
    chunk_id_suffix: Optional[str] = None,
    breadcrumb_node: Optional[Node] = None,
) -> Chunk:
    if not chunk_id_suffix:
        chunk_id_suffix = nodes[0].data_id
    chunk_id = f"{len(all_chunks)}:{chunk_id_suffix}"
    md_str = nodes_as_markdown(nodes, breadcrumb_node)
    if capacity_used(md_str) > 1.0:
        raise AssertionError(f"{chunk_id} Too long {len(md_str)}: {md_str}")

    print(
        f"==> Chunked {chunk_id}: {len(nodes)} nodes, len {len(md_str)}: {shorten(md_str, 120)!r}"
    )
    chunk = Chunk(
        chunk_id,
        get_parent_headings_md(breadcrumb_node or nodes[0]),
        nodes_as_markdown(nodes, add_context=False),
    )
    all_chunks[chunk_id] = chunk
    for node in nodes:
        node.data["chunked"] = chunk_id
    return chunk


def copy_subtree(node: Node) -> Tree:
    subtree = Tree(f"{node.data_id} subtree", shadow_attrs=True)
    # Copy the nodes and descendants; this does not deep-copy node.data objects
    # For some reason, copy_to() assigns a random data_id to the new node in subtree
    node.copy_to(subtree, deep=True)

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
    # Now that node.data and node.data.token are no longer pointing to objects in the original tree, we can modify them
    update_tokens(subtree.system_root)
    return subtree


def find_closest_ancestor(node: Node, does_match: Callable[[Node], bool]) -> Node:
    "Return the first parent/ancestor node that matches the does_match function"
    while node.parent:
        if does_match(node.parent):
            return node.parent
        node = node.parent
    return None


def update_tokens(node: Node):
    for n in node.iterator(add_self=True):
        if isinstance(n.data, TokenNodeData) and not n.data["freeze_token_children"]:
            n.data.token.children = [
                c.token for c in n.children if isinstance(c.data, TokenNodeData)
            ]


def hierarchically_chunk_nodes(
    node: Node,
    fits_in_chunk: Callable[[list[Node]], bool] = lambda nodes: capacity_used(
        nodes_as_markdown(nodes)
    )
    <= 1.0,
) -> None:
    assert (
        not isinstance(node.data, TokenNodeData) or node.is_block_token()
    ), f"Expecting block-token, not {node.token}"

    if not (md_str := nodes_as_markdown([node])):
        logger.info("Skipping empty node %s", node.data_id)
        return

    # Try to chunk as much content as possible, so see if the node's contents fit, including descendants
    if fits_in_chunk([node]):
        create_chunk([node])
        # Don't need to recurse through child nodes
        return

    if node.data_type in ["List", "Table"]:
        # Split these specially since they have an intro sentence and markdown rendering is tricky
        split_lt_node_into_chunks(node, fits_in_chunk)
        return

    if node.data_type in ["Document", "HeadingSection"]:
        # The remainder of this code deals with splitting up node's content into smaller chunks
        logger.info("%s with length %i is too large for one chunk", node.data_id, len(md_str))
        split_heading_section_into_chunks(node, fits_in_chunk)
        return

    raise AssertionError(f"Unexpected data_type: {node.id_string}")


def split_lt_node_into_chunks(node: Node, fits_in_chunk: Callable[[list[Node]], bool]):
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
        create_chunk([block_node], chunk_id_suffix=chunk_id_suffix, breadcrumb_node=node)


def _partition_list(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def split_heading_section_into_chunks(
    node: Node, fits_in_chunk: Callable[[list[Node]], bool]
) -> None:
    assert node.data_type in ["Document", "HeadingSection"]
    print(
        f"Splitting into chunks: {node.id_string} with children:",
        # Reduce verbosity by excluding BlankLine nodes
        ", ".join([c.data_id for c in node.children if c.data_type != "BlankLine"]),
    )
    # Iterate through each child node, adding them to node_buffer
    # Before chunk capacity is exceeded, flush node_buffer to a chunk
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
        if fits_in_chunk(candidate_node_list):
            node_buffer.extend(next_nodes)
        else:  # next_nodes doesn't fit, so summarize nodes that can be chunked by themselves
            if c.data_type in ["HeadingSection", "List", "Table"]:
                # For these data_types, c (and all its descendants) can be chunked by itself
                hierarchically_chunk_nodes(c)
                # Then set a shorter summary text on c
                add_summary_text(c)

            # Try again now that c has been chunked and has a summary.
            # nodes_to_markdown() will now use the shorter summary text instead of the full text.
            if fits_in_chunk(candidate_node_list):
                node_buffer.extend(next_nodes)
            elif node_buffer:
                # It still doesn't fit even using the summary, so split the children across multiple chunks
                # Create a chunk with the current node_buffer, saving next_nodes for the new chunk
                chunks_to_create.append(node_buffer.copy())

                # Test new node_buffer
                if fits_in_chunk(node_buffer):
                    # Reset and initialize node_buffer with next_nodes
                    node_buffer = next_nodes
                else:
                    split_nodes_into_chunks(node, next_nodes)
                    node_buffer = []
            else:  # node_buffer is empty, and next_nodes' contents is too long
                assert candidate_node_list == next_nodes
                split_nodes_into_chunks(node, next_nodes)
                node_buffer = []

    if node_buffer:  # Create a chunk with the remaining nodes
        if fits_in_chunk(node_buffer):
            chunks_to_create.append(node_buffer.copy())
        else:
            split_nodes_into_chunks(node, node_buffer)

    create_chunks(node, chunks_to_create)


def create_chunks(node: Node, chunks_to_create: list[list[Node]]) -> list[Chunk]:
    if len(chunks_to_create) > 1:
        chunks = []
        for i, chunk_nodes in enumerate(chunks_to_create):
            # The chunk id identifies the node being split, the split number, and the first node in the chunk
            chunks.append(
                create_chunk(
                    chunk_nodes, chunk_id_suffix=f"{node.data_id}[{i}]:{chunk_nodes[0].data_id}"
                )
            )
        return chunks
    else:
        assert len(chunks_to_create) == 1
        return [create_chunk(chunks_to_create[0])]


def split_nodes_into_chunks(parent_node: Node, nodes: list[Node]) -> None:
    raise AssertionError(
        f"{parent_node.data_id}: These node(s) cannot fit into a chunk: {[n.data_id for n in nodes]}"
    )
    # TODO: Handle this case by splitting the 2 nodes (optional intro node + other node) into smaller chunks