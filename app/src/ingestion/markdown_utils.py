import logging
import itertools
import textwrap
from collections import defaultdict
from typing import Iterable, Sequence

import mistletoe
from mistletoe import block_token
from mistletoe.token import Token
from mistletoe.block_token import TableRow, BlockToken
from mistletoe.markdown_renderer import MarkdownRenderer

from nutree import Tree, Node, StopTraversal, IterMethod


logger = logging.getLogger(__name__)


def _new_md_renderer() -> MarkdownRenderer:
    # MarkdownRenderer() calls block_token.remove_token(block_token.Footnote), so reset tokens to avoid failure
    # See https://github.com/miyuchina/mistletoe/issues/210
    block_token.reset_tokens()
    return MarkdownRenderer(normalize_whitespace=False)


def normalize_markdown(markdown: str) -> str:
    with _new_md_renderer() as renderer:
        # the parsing phase is currently tightly connected with initiation and closing of a renderer.
        # Therefore, you should never call Document(...) outside of a with ... as renderer block,
        # unless you know what you are doing.
        doc = mistletoe.Document(markdown)
        return renderer.render(doc)


def create_markdown_tree(markdown, name="Markdown tree", normalize_md=False) -> Tree:
    if normalize_md:
        markdown = normalize_markdown(markdown)
    doc = mistletoe.Document(markdown)
    tree = Tree(name)
    create_nutree(tree, doc)
    return tree


render_table_headings_for_rows = False


def _create_md_renderer() -> MarkdownRenderer:
    renderer = _new_md_renderer()

    # Referenced MarkdownRenderer:335.render_table()
    def custom_render_table_row(token: TableRow, max_line_length: int | None = None):
        content: list[list] = []

        table_token = token.parent if render_table_headings_for_rows and token.parent else None
        # get from parent table_token
        column_align = table_token.column_align if table_token else [None]
        if table_token:
            # Get header from sibling TableRow token
            content.append([c.children[0].content for c in table_token.header.children])
            # Append "|---|---|..." line
            content.append([])

        content.append(renderer.table_row_to_text(token))
        col_widths = renderer.calculate_table_column_widths(content)
        if table_token:
            content[1] = renderer.table_separator_line_to_text(col_widths, column_align)

        return [
            renderer.table_row_to_line(col_text, col_widths, column_align) for col_text in content
        ]

    renderer.render_map["TableRow"] = custom_render_table_row
    print("Creating custom MarkdownRenderer:", renderer)
    return renderer


md_renderer = _create_md_renderer()


def render_token(token: Token) -> str:
    with md_renderer:
        return md_renderer.render(token)


def describe_tree(tree: Tree) -> dict:
    attribs = defaultdict(set)
    parents = defaultdict(set)
    children = defaultdict(set)
    for node in tree.iterator(method=IterMethod.POST_ORDER):
        attribs[node.data.type].update(node.data.__dict__.keys())
        children[node.data.type].update([child.data.type for child in node.children])
        parents[node.data.type].add(node.data.token.parent.__class__.__name__)
    return {
        "attribs": attribs,
        "parents": parents,
        "children": children,
    }


# For reference
# {
#     # https://www.markdownguide.org/extended-syntax/#footnotes
#     # Footnote definitions can be found anywhere in the document,
#     # but footnotes will always be listed in the order they are referenced
#     # to in the text (and will not be shown if they are not referenced).
#     "Document": {"footnotes"},
#     "Heading": {"level", "closing_sequence"},
#     "List": {"start", "loose"},
#     # loose: indicates whether the list items are separated by blank lines
#     # leader: The prefix number or bullet point
#     "ListItem": {"indentation", "leader", , "loose", "prepend", , },
#     "Table": {"column_align", "header"},
#     "TableCell": {"align"},
#     "TableRow": {"row_align"},

#     "Link": {"title", "target", "dest_type"="uri", "label", },
#     "RawText": {, , "content"},
# }

_KNOWN_Node_Attribs = [
    "token",
    "content",
    "line_number",
    "level",
    "header",
    "column_align",
    "align",
    "row_align",
    "start",
    "leader",
    "prepend",
    "indentation",
    "title",
    "target",
    "loose",
    "footnotes",
    "closing_sequence",
    "label",
    "title_delimiter",
    "dest_type",
    "delimiter",
    "header_node",
    "children_tokens",
    "collapsed_content_str",
]

VERBOSE = False


class MdItem:
    counter = itertools.count()

    @staticmethod
    def get_id_prefix(item_type: str, token: Token) -> str:
        if item_type == "ListItem":
            return "LI"
        elif item_type == "TableRow":
            return "TR"
        elif item_type == "Heading":
            return f"H{token.level}."
        return item_type[:1]

    def __init__(
        self,
        token: Token,
        node_type: str | None = None,
    ):
        self.token = token
        self.type = node_type if node_type else token.__class__.__name__

        if self.type == "HeadingSection":
            # HeadingSection acts as a custom container for Heading and its associated content
            self.id = f"_{token.level}.{next(self.counter)}"
        elif self.type == "TableCell":
            # Use lowercase "tc" b/c it's typically collapsed into TableRow like a span token
            self.id = f"tc{next(MdItem.counter)}."
        elif isinstance(token, BlockToken):
            self.id = f"{self.get_id_prefix(self.type, token)}{token.line_number}"
        else:  # span token
            self.id = f"s.{next(self.counter)}"

    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        if key in _KNOWN_Node_Attribs:
            setattr(self, key, value)
        else:
            # TODO: remove before merging
            print(f"New attrib?: {key}={value} for {self.type} {self.id}")
            # assert False, f"New attrib?: {key}={value} for {self.type} {self.id}"

    def __repr__(self):
        "This is called from tree.print()"
        oneliner = [f"{self.type} ({self.id})"]

        # Metadata
        if self.type == "Paragraph":
            oneliner.append(
                f"of length {len (render_token(self.token))} across {len(self.token.children)} children"
            )
        elif self.type == "HeadingSection":
            oneliner.append(f"with {len(self["children_tokens"])} children")

        # Text content
        content = getattr(self, "collapsed_content_str", None)
        if not content:
            content = getattr(self, "content", "")[:100]
        if not content:
            if self.type in ["Heading", "TableRow", "ListItem", "Link"]:
                content = render_token(self.token)
            elif self.type in ["Table"]:
                content = render_token(self.token.header)
            elif self.type in ["HeadingSection", "Paragraph", "TableCell"]:
                content = None
            else:
                content = f"{self.token}"

        return " ".join(oneliner) + (f": {content!r}" if content else "")


def create_nutree(parent: Node, token: Token) -> Node:
    data = MdItem(token)
    node = parent.add(data, data_id=data.id)
    for attr in vars(token):
        if not attr.startswith("_"):  # Ignore private attributes: _parent, _children
            data[attr] = getattr(token, attr)

    # Table tokens have a TableRow that represents the table header however it is not a child of the Table token
    # so create a separate node for it
    # if "header" in vars(token):  # for table header
    #     node["header_node"] = create_nutree(node, getattr(token, "header"))

    # Recurse to create children nodes
    if token.children:
        for child_token in token.children:
            create_nutree(node, child_token)
    return node


def collapse_span_tokens(tree):
    for node in tree.iterator(method=IterMethod.POST_ORDER):  # Depth-first-traversal, post-order
        token = node.data.token
        if not isinstance(token, block_token.BlockToken):
            continue

        # Unless node is a TableRow, if any descendant is a BlockToken, then don't collapse.
        data_type = node.data.type
        if data_type in ["TableRow"]:
            # TODO: Address complex tables with BlockTokens nested in TableRows.
            #   For now, collapse TableRow assuming no nested BlockTokens.
            pass
        elif any_descendant_of_type(node, block_token.BlockToken):
            continue

        # Ignore these b/c they're collapsed by other block tokens
        if data_type in ["TableCell", "Document"]:
            # TableCell is collapsed into TableRow
            # It doesn't make sense to collapse Document
            continue

        logger.debug("Collapsing %s with %i children", node.data.type, len(node.children))
        node.data["collapsed_content_str"] = textwrap.shorten(
            render_token(token), 30, placeholder="..."
        )
        node.remove_children()


def any_descendant_of_type(node: Node, token_class: type) -> Node:
    def is_block_token(node: Node, memo):
        if isinstance(node.data.token, token_class):
            memo["found_node"] = node
            # print("Found descendant", node.data.token)
            return StopTraversal

    memo = {"found_node": None}
    node.visit(is_block_token, memo=memo)
    return memo["found_node"]


def create_heading_sections(tree: Tree):
    heading_nodes = tree.find_all(match=lambda n: n.data.type == "Heading")
    for n in heading_nodes:
        # Get all siblings up to next Heading
        body_nodes = list(get_siblings_up_to(n, "Heading"))
        hs_item = MdItem(n.data.token, "HeadingSection")
        hs_item["children_tokens"] = [n.data.token, *[s.data.token for s in body_nodes]]
        hsection_node = n.prepend_sibling(hs_item, data_id=hs_item.id)
        # Move Heading and associated body content to HeadingSection node
        n.move_to(hsection_node)
        for body in body_nodes:
            print("> ", body.data)
            body.move_to(hsection_node)


def nest_heading_sections(tree: Tree):
    "Move HeadingSection nodes under other HeadingSection nodes to coincide with their heading level"
    heading_stack: list[Node] = [None for _ in range(7)]
    heading_stack[0] = tree.children[0]  # Document node
    assert heading_stack[0].data.type == "Document"

    heading_sections = [
        n for n in tree.iterator(method=IterMethod.POST_ORDER) if n.data.type == "HeadingSection"
    ]
    last_heading_level = 0
    for hs_node in heading_sections:
        # print(hs_node)
        heading_level = hs_node.data.token.level
        if heading_level > last_heading_level:
            for i in range(last_heading_level + 1, heading_level):
                heading_stack[i] = None
        else:
            for i in range(heading_level, len(heading_stack)):
                heading_stack[i] = None
        heading_stack[heading_level] = hs_node
        # print("heading_stack:", heading_stack[1:])

        parent_hs_node = next(hs for hs in reversed(heading_stack[:heading_level]) if hs)
        # print("parent_hs_node:", parent_hs_node)
        hs_node.move_to(parent_hs_node)
        last_heading_level = hs_node.data.token.level


def get_siblings_up_to(node: Node, data_type: str) -> Iterable[Node]:
    sibling = node.next_sibling()
    while sibling and sibling.data.type != data_type:
        yield sibling
        sibling = sibling.next_sibling()


def render_node_as_markdown(node: Node) -> str:
    token = node.data.token
    # print(isinstance(token, block_token.BlockToken), node.data.type)
    if node.data.type == "HeadingSection":
        md_str_list = []
        for c in node.children:
            if c.data.type == "TableCell":
                raise ValueError(f"TableCell's parent should be a TableRow: {c.data}")
            elif isinstance(c.data.token, block_token.BlockToken):
                md_str_list.append(render_token(c.data.token))
            else:
                logger.debug("Not rendering under HeadingSection: %s", c.data.token)
                print("Not rendering under HeadingSection:", c.data.token)
        md_str = "\n\n".join(md_str_list)
    elif isinstance(token, block_token.BlockToken):
        md_str = render_token(token)
    else:
        raise ValueError(f"Rendered empty string: {node.data}")
    return md_str


def summarize(node):
    if "summary" in node.data:
        return node.data["summary"]
    
    md_str = render_node_as_markdown(node)
    summary = textwrap.shorten(md_str, 50, placeholder="...(SUMMARIZED)")
    node.data["summary"] = summary
    return summary


CHAR_LIMIT = 512


def chunk_nodes(node: Node, memo):
    md_str = render_node_as_markdown(node)
    if len(md_str) < CHAR_LIMIT:
        print(
            f"YAY: Chunked {node.data.type} ({node.data.id}) with len {len(md_str)}: {md_str[:20]}...{md_str[-10:]}"
        )
        memo[node.data.id].append(md_str)
        # Don't visit child nodes
        return

    print(f"?? Chunking {node.data.type} {node.data.id} with {len(md_str)}")
    chunked_list = []
    # First iteration: chunk heading sections
    childs = (n.data.type for n in node.children)
    print("Childs", list(childs))
    for n in (n for n in node.children if n.data.type == "HeadingSection"):
        chunk_nodes(n, memo)
        if n.data.id in memo or n.data.id + ".0" in memo:  # if chunked
            chunked_list.append(n)

    # Try chunking again but with shortened heading sections
    md_str_list = []
    for n in node.children:
        if n in chunked_list:
            md_str_list.append(summarize(n))
            continue
        else:
            md_str = render_node_as_markdown(n)
            if len(md_str) > CHAR_LIMIT:
                assert (
                    False
                ), f"Child section too long for {n.data.type} {n.data.id} with {len(md_str)}"
            else:
                md_str_list.append(md_str)

    # If fit in single chunk
    md_str = "\n".join(md_str_list)
    if len(md_str) <= CHAR_LIMIT:
        print(
            f"YAY: Chunked {node.data.type} ({node.data.id}) with len {len(md_str)}: {md_str[:20]!r}...{md_str[-10:]!r}"
        )
        memo[node.data.id].append(md_str)
        return

    # Split into chunks
    print(f"Retrying chunking {node.data.type} {node.data.id} with {len(md_str)}")
    counter = itertools.count()
    md_str = ""
    for md in md_str_list:
        if len(md_str) > CHAR_LIMIT:
            assert False, f"Too long {len(md_str)}: {md_str}"
        next_md_str = md_str + "\n" + md
        if len(next_md_str) > CHAR_LIMIT:
            memo_key = node.data.id + f".{next(counter)}"
            memo[memo_key].append(md_str)
            print(f"Chunked {memo_key} with len {len(md_str)}")
            md_str = md
    if md_str:  # Last chunk
        memo_key = node.data.id + f".{next(counter)}"
        memo[memo_key].append(md_str)
        print(f"Chunked {memo_key} with len {len(md_str)}")

    if next(counter) == 0:
        print(f"!! Overfilling chunk for {node.data.type} {node.data.id}")  # FIXME
        md_str = render_node_as_markdown(n)
        memo[node.data.id].append(md_str)
