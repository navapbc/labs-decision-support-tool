import itertools
import logging
import textwrap
import types
from collections import defaultdict
from copy import copy
from typing import Any, Callable, Iterable, Optional

import mistletoe
from mistletoe import block_token
from mistletoe.block_token import TableRow
from mistletoe.markdown_renderer import MarkdownRenderer
from mistletoe.token import Token
from nutree import IterMethod, Node, StopTraversal, Tree

logger = logging.getLogger(__name__)


def create_markdown_tree(
    markdown: str, name: str = "Markdown tree", normalize_md: bool = True
) -> Tree:
    if normalize_md:
        markdown = normalize_markdown(markdown)
    doc = mistletoe.Document(markdown)
    tree = Tree(name)
    _create_nutree(tree, doc)
    validate_tree(tree)
    return tree


def normalize_markdown(markdown: str) -> str:
    with _new_md_renderer() as renderer:
        # "the parsing phase is currently tightly connected with initiation and closing of a renderer.
        # Therefore, you should never call Document(...) outside of a with ... as renderer block"
        doc = mistletoe.Document(markdown)
        return renderer.render(doc)


def _new_md_renderer() -> MarkdownRenderer:
    "Create a new MarkdownRenderer instance with consistent settings. Remember to use in a context manager."
    # MarkdownRenderer() calls block_token.remove_token(block_token.Footnote), so reset tokens to avoid failure
    # See https://github.com/miyuchina/mistletoe/issues/210
    block_token.reset_tokens()
    return MarkdownRenderer(normalize_whitespace=False)


def _create_nutree(parent: Node, token: Token) -> Node:
    data = TokenNodeData(token)
    node = parent.add(data, data_id=data.id)
    data.node = node
    if token.children:
        # Recurse to create children nodes
        for child_token in token.children:
            _create_nutree(node, child_token)
    return node


def validate_tree(tree: Tree) -> None:
    def validate_node(node: Node, memo: dict) -> None:
        assert (
            node.data.id == node.data_id
        ), f"Node {node.data_id!r} has mismatched data.id {node.data.id!r}"

    tree.visit(validate_node)


def describe_tree(tree: Tree) -> dict:
    attribs = defaultdict(set)
    parents = defaultdict(set)
    children = defaultdict(set)
    for node in tree.iterator(method=IterMethod.POST_ORDER):
        attribs[node.data.type].update(node.data.__dict__.keys())
        children[node.data.type].update([child.data.type for child in node.children])
        parents[node.data.type].add(node.data.type)
    return {
        "attribs": attribs,
        "parents": parents,
        "children": children,
    }


def render_tree(tree: Tree, normalize: bool = True) -> str:
    """
    Render the tree to markdown text.
    For creating text for chunks, create small trees for each chunk and render them separately.
    """
    out_str = []
    render = TokenNodeData.render_token
    for node in tree.iterator(method=IterMethod.PRE_ORDER):
        if node.data.type in ["Document", "HeadingSection", "TableCell"]:
            continue  # Don't need to render these

        token = node.data.token
        match node.data.type:
            case "Heading":
                out_str.append("\n")
                out_str.append(render(token))
            case "Paragraph":
                # Only render Paragraphs that are not rendered as part of a List or Table
                if node.parent.data.type not in ["ListItem", "TableRow"]:
                    # Don't add extra newline if it's the first child of a Document
                    if node.parent.data.type not in ["Document"]:
                        out_str.append("\n")
                    out_str.append(render(token))
            case "List":
                if intro := intro_if_needed(node):
                    out_str.append(intro)
                if node.parent.data.type not in ["ListItem"]:
                    out_str.append("\n")
            case "ListItem":
                token2 = copy(token)
                # Remove children that are List or ListItem so that they are not rendered
                # TODO: If it's possible to have children: [Paragraph, List, Paragraph], that's not handled well.
                token2.children = [c for c in token2.children if c.type != "List"]
                out_str.append(render(token2))
            case "Table":
                if intro := intro_if_needed(node):
                    out_str.append(intro)
                out_str.append("\n")
                out_str.append(render(token.header))
                out_str.append("| " + " | ".join(token.header.sep_line) + " |\n")
            case "TableRow":
                out_str.append(render(token))
            case _:
                raise ValueError(f"Unexpected node type {node.data.type}: {node.data_id}")

    md_str = "".join(out_str)
    if normalize:
        return normalize_markdown(md_str)
    return md_str


def intro_if_needed(node: Node) -> str | None:
    """
    Return intro text if it doesn't have a preceding Paragraph or Heading.
    For more control, use force_intro or remove the intro text from the particular node data.
    """
    if intro := node.data["intro"]:
        if (
            node.data["force_intro"]
            or not (prev_node := node.prev_sibling())
            or prev_node.data.type not in ["Paragraph", "Heading"]
        ):
            return intro
    return None


def _create_custom_md_renderer() -> MarkdownRenderer:
    def custom_render_table_row(
        self: MarkdownRenderer, token: TableRow, max_line_length: int
    ) -> list[str]:
        return [
            self.table_row_to_line(
                self.table_row_to_text(token), token.col_widths, token.column_align
            )
        ]

    renderer = _new_md_renderer()
    # Bind the custom method to the instance so that self is passed as the first argument
    renderer.render_table_row = types.MethodType(custom_render_table_row, renderer)
    # Register the custom method to render TableRow tokens
    renderer.render_map["TableRow"] = renderer.render_table_row
    logger.info("Created custom MarkdownRenderer: %s", renderer)
    return renderer


#  TODO: Render footnotes in Document node
#     # https://www.markdownguide.org/extended-syntax/#footnotes
#     # Footnote definitions can be found anywhere in the document,
#     # but footnotes will always be listed in the order they are referenced
#     # to in the text (and will not be shown if they are not referenced).
#     "Document": {"footnotes"},
#     "List": {"start", "loose"},
#     # loose: indicates whether the list items are separated by blank lines
#     # leader: The prefix number or bullet point
#     "ListItem": {"indentation", "leader", , "loose", "prepend", , },


class MdNodeData:
    def __init__(
        self,
        element_type: str,
        node_id: str = "",
    ):
        self.type = element_type
        self.id = node_id

        # Reference to the associated tree node; typically needed for custom types
        self.node: Optional[Node] = None

    # Allow adding custom attributes to this node data object; useful during tree manipulation or chunking
    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key, None)

    @property
    def id_string(self) -> str:
        return f"{self.type} ({self.id})"

    def render(self) -> str:
        if self.node:
            return "\n\n".join(child.data.render() for child in self.node.children)
        return ""

    def __repr__(self) -> str:
        "This is called from tree.print()"
        oneliner = [self.id_string]

        # Metadata
        if self.node:
            oneliner.append(f"with {len(self.node.children)} children")

        # Provide some text content for referencing back to the markdown text
        content = self.content_oneliner()

        return " ".join(oneliner) + (f": {content!r}" if content else "")

    ONELINER_CONTENT_LIMIT = 100

    def content_oneliner(self) -> str:
        content = self["collapsed_content_str"]
        if not content:
            content = getattr(self, "content", "")[: MdNodeData.ONELINER_CONTENT_LIMIT]
        return content


class TokenNodeData(MdNodeData):
    counter = itertools.count()

    @staticmethod
    def get_id_prefix(token: Token) -> str:
        if token.type == "Heading":
            return f"H{token.level}."
        return "".join(char for char in token.type if char.isupper())

    def __init__(self, token: Token):
        self.token = token
        # Add 'type' attribute to token object for consistently referencing a token's and MdNodeData's type
        token.type = token.__class__.__name__

        if token.type == "TableCell":
            # Use lowercase "tc" prefix b/c it's typically collapsed into TableRow like a span token
            _id = f"tc{next(self.counter)}"
        elif self.is_block_token():
            _id = f"{self.get_id_prefix(token)}{token.line_number}"
        else:  # span token
            _id = f"s.{next(self.counter)}"
        super().__init__(token.type, _id)

        if token.type == "Table":
            self._init_for_table()

    def _init_for_table(self) -> None:
        t = self.token
        # t.header is a TableRow token only referenced from t.header and not part of the token tree.
        # Hence, it won't be added as a tree node, TokenNodeData(t.header) won't be called, and t.header.type won't be set,
        # So set t.header's type here so t.header.type can be used for rendering later.
        t.header.type = t.header.__class__.__name__

        # Calculate table metadata for use in rendering of individual rows or partial tables split across chunks
        # Code is adapted from MarkdownRenderer.render_table()
        with TokenNodeData.md_renderer as renderer:
            content = [renderer.table_row_to_text(t.header), []]
            # Add all the rows so that the column widths can be calculated
            content.extend(renderer.table_row_to_text(row) for row in t.children)
            col_widths = renderer.calculate_table_column_widths(content)
            sep_line = renderer.table_separator_line_to_text(col_widths, t.column_align)

        # Set calculated values on the TableRow tokens so that they can be used for rendering
        for row in [t.header] + t.children:
            row.column_align = t.column_align
            row.col_widths = col_widths
            row.sep_line = sep_line

    def is_block_token(self) -> bool:
        return isinstance(self.token, block_token.BlockToken)

    # Use this single renderer for all instances
    md_renderer = _create_custom_md_renderer()

    @classmethod
    def render_token(cls: type["TokenNodeData"], token: Token) -> str:
        "Render the token and its children using the custom MarkdownRenderer"
        # MD renderer should always be used within a context manager
        with cls.md_renderer as renderer:
            return renderer.render(token)

    def render(self) -> str:
        return self.render_token(self.token)

    def __repr__(self) -> str:
        oneliner = [self.id_string]

        # Metadata
        if self.type == "Paragraph":
            oneliner.append(
                f"of length {len(self.render())} across {len(self.token.children)} children"
            )

        # Provide single-line text content for referencing back to the markdown text
        content = self.content_oneliner()
        if not content:
            if self.type in ["Heading", "Link", "TableRow"]:
                print("RENDERING", self.id_string)
                # Render these single-line types. Assume TableRow is a single line for now.
                content = self.render()
            elif self.type in ["ListItem"]:
                # Handle multiline list items
                content = f"{self.render()[: self.ONELINER_CONTENT_LIMIT]!r}"
            elif self.type in ["Table"]:
                # Render just the header row
                self.render_token(self.token.header)
            elif self.type in ["Paragraph", "TableCell"]:
                # These will have RawText children that will show the content
                content = ""
            else:  # for Document, List, etc
                content = f"{self.token}"

        return " ".join(oneliner) + (f": {content!r}" if content else "")


def collapse_span_tokens(tree: Tree) -> int:
    collapse_counter = 0
    for node in tree.iterator(method=IterMethod.POST_ORDER):  # Depth-first-traversal, post-order
        if not node.data.is_block_token():
            continue

        # Unless node is a TableRow, if any descendant is a BlockToken, then don't collapse.
        data_type = node.data.type
        if data_type in ["TableRow"]:
            # TODO: Address complex tables with BlockTokens nested in TableRows.
            #   For now, collapse TableRow assuming it has no nested BlockTokens.
            pass
        elif any_descendant_of_type(node, lambda n: n.data.is_block_token()):
            continue

        # Ignore these data types
        if data_type in [
            "TableCell",  # TableCell is collapsed into TableRow already
            "Document",  # It doesn't make sense to collapse Document
        ]:
            continue

        logger.info("Collapsing %s with %i children", node.data.type, len(node.children))
        # Create custom attribute to store the collapsed content so that tree.print() renders nicely
        node.data["collapsed_content_str"] = textwrap.shorten(
            node.data.render(), 50, placeholder="...(collapsed)", drop_whitespace=False
        )

        # Add raw text content for Heading nodes to use the text in heading breadcrumbs
        if data_type == "Heading":
            raw_text_node = any_descendant_of_type(node, lambda n: n.data.type == "RawText")
            node.data["raw_text"] = raw_text_node.data.token.content

        node.remove_children()
        collapse_counter += 1
    return collapse_counter


def any_descendant_of_type(node: Node, does_match: Callable[[Node], bool]) -> Node:
    "Return the first descendant node that matches the does_match function"

    def any_matching_node(node: Node, memo: dict) -> None | StopTraversal:
        if does_match(node):
            memo["matching_node"] = node
            return StopTraversal
        return None

    memo = {"matching_node": None}
    node.visit(any_matching_node, memo=memo)
    return memo["matching_node"]


def create_heading_sections(tree: Tree) -> int:
    "Create custom HeadingSection nodes for each Heading node and its associated content"
    hsection_counter = 0
    heading_nodes = tree.find_all(match=lambda n: n.data.type == "Heading")
    for n in heading_nodes:
        hsection_counter += 1
        hs_node_data = MdNodeData("HeadingSection", f"_H{n.data.token.level}.{hsection_counter}")
        # Create tree node and insert so that markdown rendering of tree is consistent with original markdown
        hsection_node = n.prepend_sibling(hs_node_data, data_id=hs_node_data.id)
        hs_node_data.node = hsection_node
        hs_node_data["level"] = n.data.token.level
        # Get all siblings up to next Heading; these will be HeadingSection's new children
        children = list(get_siblings_up_to(n, "Heading"))
        # Move in order the Heading and associated children to the new HeadingSection node
        n.move_to(hsection_node)
        for body in children:
            body.move_to(hsection_node)
        logger.info("Created new %s", hsection_node.data)
    return hsection_counter


def get_siblings_up_to(node: Node, data_type: str) -> Iterable[Node]:
    sibling = node.next_sibling()
    while sibling and sibling.data.type != data_type:
        yield sibling
        sibling = sibling.next_sibling()


def nest_heading_sections(tree: Tree) -> int:
    "Move HeadingSection nodes under other HeadingSection nodes to coincide with their heading level"
    # heading_stack[1] corresponds to an H1 heading
    heading_stack: list[Node | None] = [None for _ in range(7)]
    if tree.children[0].data.type == "Document":
        heading_stack[0] = tree.children[0]

    # Get heading sections in order of appearance in markdown text
    heading_sections = [
        n for n in tree.iterator(method=IterMethod.POST_ORDER) if n.data.type == "HeadingSection"
    ]
    move_counter = 0
    last_heading_level = 0
    for hs_node in heading_sections:
        # print(hs_node)
        heading_level = hs_node.data.level
        if heading_level > last_heading_level:
            # Handle the case where a heading level skips a level, compared to last heading
            for i in range(last_heading_level + 1, heading_level):
                heading_stack[i] = None
        heading_stack[heading_level] = hs_node
        # Fill in levels higher than heading_level with None
        for i in range(heading_level + 1, len(heading_stack)):
            heading_stack[i] = None
        # print("heading_stack:", heading_stack[1:])

        parent_hs_node = next(hs for hs in reversed(heading_stack[:heading_level]) if hs)
        if hs_node.parent != parent_hs_node:
            logger.info("Moving %r under parent %r", hs_node.data, parent_hs_node.data)
            hs_node.move_to(parent_hs_node)
            move_counter += 1

        last_heading_level = heading_level
    return move_counter


def add_list_and_table_intros(tree: Tree) -> int:
    """
    Add 'intro' attribute to List and Table block elements based on preceding Paragraph or Heading node.

    Reminder for the chunking step after the tree is prepped:
    If the block element is split across chunks, the List or Table token should be copied to each chunk.
    For the first of the split chunks, remove the 'intro' attribute if it already has the preceding text
    to avoid duplicate intro text in the chunk.
    """
    counter = 0
    list_nodes = tree.find_all(match=lambda n: n.data.type == "List")
    for n in list_nodes:
        if _add_intro_attrib(n):
            counter += 1

    table_nodes = tree.find_all(match=lambda n: n.data.type == "Table")
    for n in table_nodes:
        if _add_intro_attrib(n):
            counter += 1

    return counter


def _add_intro_attrib(node: Node) -> bool:
    if prev_node := node.prev_sibling():
        if prev_node.data.type in ["Paragraph", "Heading"]:
            if node.data["intro"]:
                logger.info("Skipping %s: already has intro %r", node.data_id, node.data["intro"])
                return False  # Don't override existing intro

            intro_md = prev_node.data.render()
            # Limit size of intro by using only the last sentence
            node.data["intro"] = intro_md.split(".")[-1]
            logger.info("Added intro to %s: %r", node.data_id, node.data["intro"])
            return True
        else:
            print(f"Unexpected intro node {prev_node.data.type} {prev_node.data_id}")
    return False


def summarize(node: Node) -> str:
    if not (summary := node.data["summary"]):
        # TODO: make this configurable
        summary = textwrap.shorten(node.data.render(), 50, placeholder="...(SUMMARIZED)")
        # Create custom attribute to store the summary
        node.data["summary"] = summary
    return summary


def get_parent_headings(node: Node) -> Iterable[MdNodeData]:
    """
    Return the list of nested parent Headings in order of appearance in the markdown text.
    Check headings[i]["level"] for the heading level, which may not be consecutive.
    """
    headings: list[MdNodeData] = []
    while node.parent:
        if node.data.type == "HeadingSection":
            heading_node = node.children[0]
            headings.append(heading_node.data)
        node = node.parent
    return reversed(headings)


def get_raw_parent_headings(node: Node) -> list[str]:
    "Returns the text of nested parent headings in level order, which may not be consecutive"
    return [h["raw_text"] for h in get_parent_headings(node)]


CHAR_LIMIT = 512


def chunk_nodes(node: Node, memo: dict) -> None:
    # assert node.data.is_block_token(), f"Expecting block-token, not {node.data.token}"
    md_str = node.data.render()
    if len(md_str) < CHAR_LIMIT:
        print(
            f"YAY: Chunked {node.data_id} with len {len(md_str)}: {md_str[:20]!r}...{md_str[-10:]!r}"
        )
        memo[node.data_id].append(md_str)
        # Don't visit child nodes
        return

    print(f"?? Chunking {node.data_id} with {len(md_str)}")
    chunked_list = []
    # First iteration: chunk heading sections
    childs = (n.data.type for n in node.children)
    print("Childs", list(childs))
    for n in (n for n in node.children if n.data.type == "HeadingSection"):
        chunk_nodes(n, memo)
        if n.data_id in memo or n.data_id + ".0" in memo:  # if chunked
            chunked_list.append(n)

    # Try chunking again but with shortened heading sections
    md_str_list = []
    for n in node.children:
        if n in chunked_list:
            md_str_list.append(summarize(n))
            continue
        else:
            md_str = n.data.render()
            if len(md_str) > CHAR_LIMIT:
                raise AssertionError(
                    f"Child section too long for {n.data.type} {n.data_id} with {len(md_str)}"
                )
            else:
                md_str_list.append(md_str)

    # If fit in single chunk
    md_str = "\n".join(md_str_list)
    if len(md_str) <= CHAR_LIMIT:
        print(
            f"YAY: Chunked {node.data_id} with len {len(md_str)}: {md_str[:20]!r}...{md_str[-10:]!r}"
        )
        memo[node.data_id].append(md_str)
        return

    # Split into chunks
    print(f"Retrying chunking {node.data_id} with {len(md_str)}")
    counter = itertools.count()
    md_str = ""
    for md in md_str_list:
        if len(md_str) > CHAR_LIMIT:
            raise AssertionError(f"Too long {len(md_str)}: {md_str}")
        next_md_str = md_str + "\n" + md
        if len(next_md_str) > CHAR_LIMIT:
            memo_key = node.data_id + f".{next(counter)}"
            memo[memo_key].append(md_str)
            print(f"Chunked {memo_key} with len {len(md_str)}")
            md_str = md
    if md_str:  # Last chunk
        memo_key = node.data_id + f".{next(counter)}"
        memo[memo_key].append(md_str)
        print(f"Chunked {memo_key} with len {len(md_str)}")

    if next(counter) == 0:
        print(f"!! Overfilling chunk for {node.data_id}")  # FIXME
        md_str = n.data.render()
        memo[node.data_id].append(md_str)
