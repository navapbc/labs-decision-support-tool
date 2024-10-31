import logging
import textwrap
from copy import copy
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from nutree import Node, Tree

from src.ingestion.markdown_tree import (
    TokenNodeData,
    get_parent_headings_raw,
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
    logger.info("Creating new tree from subtree %s", node.data_id)
    subtree = Tree(f"{node.data_id} subtree", shadow_attrs=True)
    # Copy the nodes and descendants; this does not deep-copy node.data objects
    # For some reason, copy_to() assigns a random data_id to the new node in subtree
    new_node = node.copy_to(subtree, deep=True)

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

    assert subtree[node.data_id], f"Expected data_id {node.data_id!r} for {subtree.first_child()}"

    # Now that copies of node.data and node.data.token are created, update references to the tokens
    # Update all node.data.token.children to point to the new token objects in the subtree
    for n in new_node.iterator(add_self=True):
        if isinstance(n.data, TokenNodeData) and not n.data["freeze_token_children"]:
            n.data.token.children = [
                c.token for c in n.children if isinstance(c.data, TokenNodeData)
            ]
            for c in n.data.token.children:
                # token.parent was indirectly updated when token.children was set
                assert c.parent == n.data.token
    # At this point, no object in the subtree should be pointing to objects in the original tree,
    # except for tokens associated with "freeze_token_children". We are free to modify the subtree.
    return subtree


def remove_child(node: Node, child: Node) -> None:
    logger.info("Removing child %s from %s", child.data_id, node.data_id)
    # Update node.token.children since that's used for rendering
    node.data.token.children.remove(child.data.token)
    # Then remove the child from the tree
    child.remove()


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

    while node.parent:
        if does_match(node.parent):
            return node.parent
        node = node.parent
    return None


def nodes_as_markdown(nodes: Sequence[Node]) -> str:
    # Don't render Heading nodes by themselves
    if len(nodes) == 1 and nodes[0].data_type in ["Heading"]:
        return ""

    md_list: list[str] = []
    for node in nodes:
        # node.data["summary"] is set when node is too large to fit with existing chunk;
        # it may equal empty string "" (to not include summary text), so check for None
        if node.data["summary"] is None:
            node_md = render_subtree_as_md(node, normalize=True)
        else:
            node_md = node.data["summary"]
        md_list.append(node_md)
    return normalize_markdown("".join(md_list))


@dataclass
class ProtoChunk:
    "Temporary data structure for storing chunk data before creating a Chunk object"
    id: str
    headings: list[str]
    markdown: str  # Markdown content of the chunk
    length: int
    # to_embed: str  # TODO: create string to embed from headings and markdown


class ChunkingConfig:

    def __init__(self, max_length: int) -> None:
        self.max_length = max_length
        self.chunks: dict[str, ProtoChunk] = {}

    def text_length(self, markdown):
        return len(markdown.split())

    def nodes_fit_in_chunk(self, nodes: Sequence[Node]) -> bool:
        return self.text_length(nodes_as_markdown(nodes)) < self.max_length

    def create_chunk(
        self,
        nodes: Sequence[Node],
        chunk_id_suffix: Optional[str] = None,
        breadcrumb_node: Optional[Node] = None,
    ) -> ProtoChunk:
        if not chunk_id_suffix:
            chunk_id_suffix = nodes[0].data_id
        chunk_id = f"{len(self.chunks)}:{chunk_id_suffix}"
        headings = get_parent_headings_raw(breadcrumb_node or nodes[0])
        if doc_name := nodes[0].tree.first_child().data["name"]:
            headings.insert(0, doc_name)
        markdown = nodes_as_markdown(nodes)
        chunk = ProtoChunk(
            chunk_id,
            headings,
            markdown,
            self.text_length(markdown),
        )
        if not self.text_length(chunk.markdown) < self.max_length:
            raise AssertionError(f"{chunk_id} is too large! Check before calling create_chunk()")
        logger.info("Created chunk %s from %i nodes", chunk_id, len(nodes))
        self.chunks[chunk.id] = chunk
        return chunk

    def create_chunks_for_next_nodes(self, node: Node, intro_node: Optional[Node] = None) -> None:
        # TODO: Splitting the contents of the 2 nodes into chunks
        raise AssertionError(
            f"{node.parent.data_id}: These node(s) cannot fit into a single chunk:"
            f" {node.data_id} {intro_node.data_id if intro_node else ''}"
        )
        # TODO: Add to self.chunks
        # self.chunks[chunk.id] = chunk

    def should_summarize(self, next_nodes: Sequence[Node], node_buffer: Sequence[Node]) -> bool:
        next_nodes_portion = self.text_length(nodes_as_markdown(next_nodes)) / self.max_length
        if next_nodes_portion > 0.75:
            # Example on https://edd.ca.gov/en/jobs_and_training/FAQs_WARN/
            # Only the 1 larger accordion is chunked by itself and summarized.
            # The smaller accordions are included alongside other accordions.
            return True

        # node_buffer_portion = self.text_length(nodes_as_markdown(node_buffer)) / self.max_length
        # if node_buffer_portion

        return False

    def compose_summary_text(self, node: Node) -> str:
        return (
            shorten(node.render().splitlines()[0], 100, placeholder="...")
            + f" (SUMMARY of {node.data_id})\n\n"
        )


def chunk_tree(tree: Tree, config: ChunkingConfig) -> dict[str, ProtoChunk]:
    # Reset the tree for chunking
    for n in tree:
        for attr in ["summary"]:
            n.data[attr] = None

    hierarchically_chunk_nodes(tree.first_child(), config)
    return config.chunks


def hierarchically_chunk_nodes(node: Node, config: ChunkingConfig) -> None:
    assert (
        not isinstance(node.data, TokenNodeData) or node.is_block_token()
    ), f"Expecting block-token, not {node.token}"

    # Try to chunk as much content as possible, so see if the node's contents fit, including descendants
    if config.nodes_fit_in_chunk([node]):
        config.create_chunk([node])
        # Don't need to recurse through child nodes
        return

    # The remainder of this function deals with splitting up node's content into multiple chunks

    if node.data_type in ["List", "Table"]:
        # Split these specially since they have an intro sentence (and table header) to include for each chunk
        split_list_or_table_node_into_chunks(node, config)
        return

    if node.data_type in ["Document", "HeadingSection"]:
        logger.info("%s is too large for one chunk", node.data_id)
        split_heading_section_into_chunks(node, config)
        return

    raise AssertionError(f"Unexpected data_type: {node.id_string}")


def split_list_or_table_node_into_chunks(node: Node, config: ChunkingConfig) -> None:
    assert node.data_type in ["List", "Table"]
    logger.info("Splitting large %s into multiple chunks", node.id_string)

    def create_new_tree_with(children_ids: set[str]) -> Node:
        "Create a new tree keeping only the children in children_ids"
        subtree = copy_subtree(node)
        block_node = subtree.first_child()  # the List or Table node
        # show_intro should be True since block_node's content is being split
        block_node.data["show_intro"] = True
        to_remove = {c.data_id for c in block_node.children} - children_ids
        remove_children_from(block_node, to_remove)
        assert {c.data_id for c in block_node.children} == children_ids
        return block_node

    chunks_to_create: list[list[Node]] = []
    children_ids = {c.data_id for c in node.children}
    # Copy the node's subtree, then gradually remove the last child until the content fits
    while children_ids:  # Repeat until all the children are in some chunk
        block_node = create_new_tree_with(children_ids)
        while not config.nodes_fit_in_chunk([block_node]) and block_node.has_children():
            remove_child(block_node, block_node.last_child())

        if block_node.has_children():
            chunks_to_create.append([block_node])
            for child_node in block_node.children:
                children_ids.remove(child_node.data_id)
        else:
            raise AssertionError(f"{block_node.data_id} should have at least one child")
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
        else:  # candidate_node_list doesn't fit
            # TODO: Summarize next_nodes vs add it to the next chunk

            # For these data_types, if should_summarize(), then next_nodes (and its descendants)
            # can be chunked and summarized. Use the summary
            if c.data_type in ["HeadingSection", "List", "Table"]:
                if config.should_summarize(next_nodes, node_buffer):
                    # summarize child node that can be chunked by themselves
                    hierarchically_chunk_nodes(c, config)
                    # Then set a shorter summary text in a custom attribute
                    assert c.data["summary"] is None, "Summary should not be set yet"
                    c.data["summary"] = config.compose_summary_text(c)
                    logger.debug("Added summary to %s: %s", c.data_id, c.data["summary"])

                    # Try again now that c has been chunked and summarized
                    if config.nodes_fit_in_chunk(candidate_node_list):
                        # nodes_fit_in_chunk() calls nodes_as_markdown(), which will use the shorter
                        # summary text instead of the full text
                        node_buffer.extend(next_nodes)
                        continue
                    else:
                        # candidate_node_list still doesn't fit using the summarized next_nodes
                        # Remove the summary since we don't want calls to nodes_as_markdown() to use it
                        c.data["summary"] = None

            # Either no summary was created or candidate_node_list still doesn't fit using the summary

            # Split candidate_node_list (node_buffer + next_nodes) across multiple chunks
            # 1. put node_buffer in its own chunk
            if node_buffer:
                # Create a chunk with the current node_buffer contents
                chunks_to_create.append(node_buffer)
                # and reset node_buffer to a new list
                node_buffer = []

            # 2. Handle next_nodes
            # Check if next_nodes can be the new node_buffer
            if config.nodes_fit_in_chunk(next_nodes):
                # Reset node_buffer to be next_nodes
                node_buffer = next_nodes
            else:  # next_nodes needs to be split into multiple chunks
                assert {c, intro_paragraph_node} == set(next_nodes)
                config.create_chunks_for_next_nodes(c, intro_paragraph_node)
                assert not node_buffer, f"node_buffer should be empty: {node_buffer}"

    if node_buffer:  # Create a chunk with the remaining nodes
        if config.nodes_fit_in_chunk(node_buffer):
            chunks_to_create.append(node_buffer)
        else:
            raise AssertionError(f"node_buffer should always fit: {node_buffer}")

    _create_chunks(config, node, chunks_to_create)


def _create_chunks(config: ChunkingConfig, node: Node, chunks_to_create: list[list[Node]]) -> None:
    """
    Create chunks based on chunks_to_create, which are some partitioning of node's children.
    If there are multiple chunks for the node, use a different chunk_id_suffix to make it obvious.
    """
    if len(chunks_to_create) == 1:
        config.create_chunk(chunks_to_create[0], chunk_id_suffix=f"{node.data_id}")
    else:
        for i, chunk_nodes in enumerate(chunks_to_create):
            # Make sure first_node is different from node. They can be the same when splitting Lists and Tables.
            first_node_id = (
                chunk_nodes[0].first_child().data_id
                if chunk_nodes[0].data_id == node.data_id
                else chunk_nodes[0].data_id
            )
            # The chunk id identifies the node being split, the split number, and the first node in the chunk
            config.create_chunk(
                chunk_nodes,
                chunk_id_suffix=f"{node.data_id}[{i}]:{first_node_id}",
                breadcrumb_node=node,
            )
