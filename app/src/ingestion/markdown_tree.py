import itertools
import logging
import textwrap
from collections import defaultdict
from typing import Any, Iterable

import mistletoe
from mistletoe import block_token
from mistletoe.ast_renderer import AstRenderer
from mistletoe.markdown_renderer import MarkdownRenderer
from mistletoe.token import Token
from nutree import IterMethod, Node, Tree

logger = logging.getLogger(__name__)


def create_markdown_tree(
    markdown: str, name: str = "Markdown tree", normalize_md: bool = True
) -> Tree:
    """
    Returns a tree reflecting the structure of the Tokens parsed from the markdown text.
    The tree is created using mistletoe's Tokens and the TokenNodeData class.
    Note that the structure of the tree (i.e., each node's parent and children) is independent of each Token's parent and children.
    To render the tree to markdown text, use render_tree_as_md() or render_subtree_as_md().
    """
    if normalize_md:
        markdown = normalize_markdown(markdown)
    with _new_md_renderer():
        # Never call Document(...) outside of a with ... as renderer block"
        # Otherwise, markdown_renderer.BlankLine will not be created
        doc = mistletoe.Document(markdown)
    # The shadow_attrs=True argument allows accessing node.data.age as node.age -- see validate_tree()
    tree = Tree(name, shadow_attrs=True)
    tree.system_root.set_meta("prep_funcs", [])
    _populate_nutree(tree.system_root, doc)
    validate_tree(tree)
    return tree


def describe_markdown_as_json(markdown: str) -> str:
    """
    For the given markdown, returns mistletoe's resulting Tokens as JSON.
    Useful for examining the tokens used to create nodes in a create_markdown_tree().
    """
    with AstRenderer() as ast_renderer:
        doc = mistletoe.Document(markdown)
        ast_json = ast_renderer.render(doc)
        return ast_json


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
    renderer = MarkdownRenderer(normalize_whitespace=True)

    return renderer


def _populate_nutree(parent: Node, token: Token) -> Node:
    data = TokenNodeData(token, parent.tree)
    node = parent.add(data, data_id=data.data_id)
    if token.children:
        # Recurse to create children nodes
        for child_token in token.children:
            _populate_nutree(node, child_token)
    return node


def validate_tree(tree: Tree) -> None:
    for node in tree:
        assert (
            node.data_id == node.data.data_id
        ), f"Node {node.data_id!r} has mismatched data_id: {node.data_id!r} and {node.data.data_id!r}"

        if isinstance(node.data, TokenNodeData):
            assert (
                node.data_id == node.data.token.data_id
            ), f"Node {node.data_id!r} has mismatched data_id: {node.data_id!r} and {node.data.token.data_id!r}"
            assert (
                node.data_type
                == node.data.data_type
                == node.data.token.type
                == node.data.token.__class__.__name__
            ), f"Node {node.data_id!r} has mismatched data_type: {node.data.data_type!r} and {node.data.token.type!r}"


def describe_tree(tree: Tree) -> dict:
    parents = defaultdict(set)
    children = defaultdict(set)
    tokens = defaultdict(set)
    counts: dict[str, int] = defaultdict(int)
    for node in tree:
        counts[node.data_type] += 1
        if node.children:
            children[node.data_type].update([child.data_type for child in node.children])
        if node.parent:
            parents[node.data_type].add(node.parent.data_type)
        if isinstance(node.data, TokenNodeData):
            tokens[node.data_type].update(node.token.__dict__.keys())
    return {
        "counts": counts,
        "children": children,
        "parents": parents,
        "tokens": tokens,
    }


def tokens_vs_tree_mismatches(tree: Tree) -> dict:
    "Check the tokens' parent and children match against the tree structure."
    memo: dict[str, list[str]] = defaultdict(list)
    for node in tree:
        if node.data_type == "Document":
            continue
        if not isinstance(node.data, TokenNodeData) or not node.is_block_token():
            continue

        if node.parent:
            if isinstance(node.parent.data, TokenNodeData):
                if node.token.parent != node.parent.token:
                    memo["diff_parent"].append(
                        f"Different token parent for {node.data_id}: {node.token.parent} vs {node.parent.token}"
                    )
        elif node.token.parent:
            memo["has_parent"].append(f"Token has parent for {node.data_id}: {node.token.parent}")

        if node.children:
            node_children_tokens = [
                c.token for c in node.children if isinstance(c.data, TokenNodeData)
            ]
            if node_children_tokens != node.token.children:
                memo["diff_children"].append(
                    f"Different token children for {node.data_id}: {node_children_tokens} vs {node.token.children}"
                )
        elif node.token.children:
            token_children = [
                c
                for c in node.token.children
                if isinstance(c, block_token.BlockToken) and c.__class__.__name__ != "TableCell"
            ]
            if token_children:
                memo["has_children"].append(
                    f"Token has block-token children for {node.data_id}: {token_children}"
                )
    return memo


def render_tree_as_md(tree: Tree, normalize: bool = True) -> str:
    return render_subtree_as_md(tree.system_root.first_child(), normalize=normalize)


def render_subtree_as_md(node: Node, normalize: bool = True) -> str:
    """
    Render the node and its descendants (a subtree) to markdown text.
    Useful for creating markdown text for chunks.
    Since the structure of the tree (i.e., each node's parent and children) is independent of each Token's parent and children,
    we cannot rely on mistletoe's renderer (which is based on Tokens) to render the tree correctly. Hence, we have this function.
    """
    if node.data_type == "HeadingSection":  # Render the custom HeadingSection node specially
        out_str = []
        for c in node.children:
            out_str.append(render_subtree_as_md(c, normalize=normalize))
    elif isinstance(node.data, TokenNodeData):
        out_str = []
        if intro := _intro_if_needed(node):
            out_str.append(intro)
            # out_str.append("\n")
        out_str.append(TokenNodeData.render_token(node.token))
    else:
        raise ValueError(f"Unexpected node type: {node.id_string}")

    md_str = "\n\n".join(map(lambda s: s.strip(), out_str)) + "\n"
    if normalize:
        return normalize_markdown(md_str)
    return md_str


def _intro_if_needed(node: Node) -> str | None:
    "Return intro text if intro has text and show_intro is True."
    if (intro := node.data["intro"]) and node.data["show_intro"]:
        return f"({intro.strip()})"
    return None


#  TODO: Render footnotes in Document node
#     # https://www.markdownguide.org/extended-syntax/#footnotes
#     # Footnote definitions can be found anywhere in the document,
#     # but footnotes will always be listed in the order they are referenced
#     # to in the text (and will not be shown if they are not referenced).


class MdNodeData:
    def __init__(
        self,
        data_type: str,
        data_id: str,
        tree: Tree,
    ):
        self.data_type = data_type
        self.data_id = data_id
        self.tree = tree

    # Allow adding custom attributes to this node data object; useful during tree manipulation or chunking
    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key, None)

    @property
    def node(self) -> Node | None:
        return self.tree.find_first(data_id=self.data_id)

    @property
    def id_string(self) -> str:
        return f"{self.data_type} {self.data_id}"

    def render(self) -> str:
        if node := self.node:
            return "\n\n".join(child.data.render() for child in node.children)
        return ""

    def __repr__(self) -> str:
        "This is called from tree.print()"
        oneliner = [self.id_string]

        # Metadata
        if node := self.node:
            oneliner.append(f"with {len(node.children)} children")

        # Provide some text content for referencing back to the markdown text
        content = self.content_oneliner()

        return " ".join(oneliner) + (f": {content!r}" if content else "")

    ONELINER_CONTENT_LIMIT = 100

    def content_oneliner(self) -> str:
        content = self["oneliner_of_hidden_nodes"]
        if not content:
            content = getattr(self, "content", "")[: MdNodeData.ONELINER_CONTENT_LIMIT]
        return content


class TokenNodeData(MdNodeData):
    counter = itertools.count()

    @staticmethod
    def get_id_prefix(token: block_token.BlockToken) -> str:
        if token.type == "Heading":
            return f"H{token.level}"
        return "".join(char for char in token.type if char.isupper())

    def __init__(self, token: Token, tree: Tree):
        self.token = token
        # Add 'type' attribute to token object for consistently referencing a token's and MdNodeData's type
        token.type = token.__class__.__name__

        if token.type == "TableCell":
            # Use lowercase "tc" prefix b/c it's typically encapsulated into TableRow like a span token
            _id = f"tc{next(self.counter)}_{token.line_number}"
        elif (
            self.is_block_token()
        ):  # Block tokens start on a new line so use the line number in the id
            _id = f"{self.get_id_prefix(token)}_{token.line_number}"
        else:  # Span tokens use a lower case prefix; they can be ignored and are hidden by hide_span_tokens()
            _id = f"s.{next(self.counter)}"
        super().__init__(token.type, _id, tree)

        # Add 'data_id' attribute to the token object for easy cross-referencing -- see validate_tree()
        token.data_id = self.data_id

        # Table tokens needs special initialization for rendering partial tables later
        if token.type == "Table":
            self._init_for_table()

    def is_block_token(self) -> bool:
        return isinstance(self.token, block_token.BlockToken)

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
        for row in [t.header, *t.children]:
            row.column_align = t.column_align
            row.col_widths = col_widths
            row.sep_line = sep_line

    # Use this single renderer for all instances
    md_renderer = _new_md_renderer()

    @classmethod
    def render_token(cls: type["TokenNodeData"], token: Token) -> str:
        "Render the token and its descendants using the custom MarkdownRenderer"
        # MD renderer should always be used within a context manager
        with cls.md_renderer as renderer:
            if token.type in ["TableRow"]:
                return renderer.table_row_to_line(
                    renderer.table_row_to_text(token),
                    token.col_widths,
                    token.column_align,
                )
            return renderer.render(token)

    def render(self) -> str:
        return self.render_token(self.token)

    def __repr__(self) -> str:
        "Returns oneliner that is shown in tree.print()"
        oneliner = [self.id_string]

        # Metadata
        if self.data_type == "Paragraph":
            oneliner.append(
                f"of length {len(self.render())} across {len(self.token.children)} children"
            )

        # Provide single-line text content for referencing back to the markdown text
        content = self.content_oneliner()
        if not content:
            if self.data_type == "BlankLine":
                content = ""
            elif self.data_type in ["Heading", "Link", "TableRow"]:
                # Render these single-line types. Assume TableRow is a single line for now.
                content = self.render()
            elif self.data_type in ["ListItem"]:
                # Handle multiline list items
                content = f"{self.render()[: self.ONELINER_CONTENT_LIMIT]!r}"
            elif self.data_type in ["Table"]:
                # Render just the header row
                content = self.render_token(self.token.header)
            elif self.data_type in ["Paragraph", "TableCell"]:
                # These have RawText children that will show the content
                # When those children are hidden, self["oneliner_of_hidden_nodes"] from content_oneliner() will be used
                content = ""
            else:  # for Document, List, etc
                content = f"{self.token}"

        return " ".join(oneliner) + (f": {content!r}" if content else "")


def hide_span_tokens(tree: Tree) -> int:
    hide_counter = 0
    for node in tree.iterator(method=IterMethod.POST_ORDER):  # Depth-first-traversal, post-order
        if (
            not node.children
            or not isinstance(node.data, TokenNodeData)
            or not node.is_block_token()
        ):
            continue

        data_type = node.data_type
        # Unless node is a TableRow, if any descendant is a BlockToken, then don't hide.
        if data_type in ["TableRow"]:
            # TODO: Address complex tables with BlockTokens nested in TableRows.
            #   For now, allow TableRow's children to be hidden assuming it has no nested BlockTokens besides TableCell.
            pass
        elif node.find_first(match=lambda n: n.is_block_token()):
            continue

        # Ignore these data types
        if data_type in [
            "TableCell",  # TableCell will be hidden when the associated TableRow is processed
            "Document",  # It doesn't make sense to hide Document's children
        ]:
            continue

        logger.info("Hiding %i children span-tokens under %s", len(node.children), data_type)
        # Create custom attribute for the hidden text so that tree.print() renders some of the text
        node.data["oneliner_of_hidden_nodes"] = textwrap.shorten(
            node.render(), 50, placeholder="...(hidden)", drop_whitespace=False
        )

        # Add raw text content for Heading nodes to use the text in heading breadcrumbs
        if data_type == "Heading":
            raw_text_nodes = node.find_all(match=lambda n: n.data_type == "RawText")
            assert len(raw_text_nodes) == 1, f"Expected 1 RawText node for {node.data_id}"
            node.data["raw_text"] = raw_text_nodes[0].token.content

        # Ensure node.token.children tokens are never removed
        node.data["freeze_token_children"] = True
        node.remove_children()
        hide_counter += 1

    tree.system_root.meta["prep_funcs"].append("hide_span_tokens")
    return hide_counter


def create_heading_sections(tree: Tree) -> int:
    "Create custom HeadingSection nodes for each Heading node and its associated content"
    hsection_counter = 0
    heading_nodes = tree.find_all(match=lambda n: n.data_type == "Heading")
    for n in heading_nodes:
        if n.parent.data_type == "HeadingSection":
            # Skip if the Heading is already part of a HeadingSection
            continue

        hsection_counter += 1
        hs_node_data = MdNodeData(
            "HeadingSection", f"_S{n.token.level}_{n.token.line_number}", tree
        )
        # Create tree node and insert so that markdown rendering of tree is consistent with original markdown
        hs_node = n.prepend_sibling(hs_node_data, data_id=hs_node_data.data_id)
        # Get all siblings up to next Heading; these will be HeadingSection's new children
        children = list(get_siblings_up_to(n, "Heading"))
        # Move in order the Heading and associated children to the new HeadingSection node
        n.move_to(hs_node)
        for body in children:
            body.move_to(hs_node)
        logger.info("Created new %s", hs_node.data)

    tree.system_root.meta["prep_funcs"].append("create_heading_sections")
    return hsection_counter


def get_siblings_up_to(node: Node, data_type: str) -> Iterable[Node]:
    sibling = node.next_sibling()
    while sibling and sibling.data_type != data_type:
        yield sibling
        sibling = sibling.next_sibling()


def nest_heading_sections(tree: Tree) -> int:
    "Move HeadingSection nodes under other HeadingSection nodes to coincide with their heading level"
    # heading_stack[1] corresponds to an H1 heading
    heading_stack: list[Node | None] = [None for _ in range(7)]
    if tree.first_child().data_type == "Document":
        heading_stack[0] = tree.first_child()

    # Get heading sections in order of appearance in markdown text
    heading_sections = [
        n for n in tree.iterator(method=IterMethod.PRE_ORDER) if n.data_type == "HeadingSection"
    ]
    move_counter = 0
    last_heading_level = 0
    for hs_node in heading_sections:
        # Traverse the headings in order and update the heading_stack
        heading_level = hs_node.first_child().token.level
        if heading_level > last_heading_level:
            # Handle the case where a heading level skips a level, compared to last heading
            for i in range(last_heading_level + 1, heading_level):
                heading_stack[i] = None
        heading_stack[heading_level] = hs_node
        # Fill in levels higher than heading_level with None
        for i in range(heading_level + 1, len(heading_stack)):
            heading_stack[i] = None
        logger.debug("Current headings: %s", heading_stack[1:])

        # Find the parent HeadingSection node to move hs_node under
        parent_hs_node = next(hs for hs in reversed(heading_stack[:heading_level]) if hs)
        if hs_node.parent != parent_hs_node:
            logger.info("Moving %r under parent %r", hs_node.id_string, parent_hs_node.id_string)
            hs_node.move_to(parent_hs_node)
            move_counter += 1

        last_heading_level = heading_level

    tree.system_root.meta["prep_funcs"].append("nest_heading_sections")
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
    list_nodes = tree.find_all(match=lambda n: n.data_type == "List")
    for n in list_nodes:
        if _add_intro_attrib(n):
            counter += 1

    table_nodes = tree.find_all(match=lambda n: n.data_type == "Table")
    for n in table_nodes:
        if _add_intro_attrib(n):
            counter += 1

    return counter


def _add_intro_attrib(node: Node) -> bool:
    # Get previous non-BlankLine node
    prev_node = node.prev_sibling()
    while prev_node and prev_node.data_type == "BlankLine":
        prev_node = prev_node.prev_sibling()

    if prev_node:
        if prev_node.data_type in ["Paragraph", "Heading"]:
            if node.data["intro"]:
                logger.info("Skipping %s: already has intro %r", node.data_id, node.data["intro"])
                return False  # Don't override existing intro

            intro_md = prev_node.data["raw_text"] or prev_node.render()
            # Limit size of intro by using only the last sentence
            node.data["intro"] = intro_md.split(". ")[-1]
            logger.info("Added intro to %s: %r", node.data_id, node.data["intro"])
            # Mark the node being used as the intro as a hint when chunking to keep intro with the List/Table
            prev_node.data["is_intro"] = True
            return True
        else:
            raise ValueError(f"Unexpected prev node type: {prev_node.id_string}")
    return False


def get_parent_headings(node: Node) -> Iterable[TokenNodeData]:
    """
    Return the list of node's parent Headings in order of appearance in the markdown text.
    Check headings[i].token.level for the heading level, which may not be consecutive.
    """
    assert node.tree, f"Node {node.data_id} has no tree"
    assert (
        "nest_heading_sections" in node.tree.system_root.meta["prep_funcs"]
    ), f"nest_heading_sections() must be called before get_parent_headings(): {node.tree.system_root.meta}"

    # If the node is a Heading and it's parent is a HeadingSection, start with the HeadingSection node instead
    # so that the node will not be included in the returned list.
    if node.data_type == "Heading" and node.parent.data_type == "HeadingSection":
        node = node.parent

    headings: list[TokenNodeData] = []
    while node := node.parent:
        if node.data_type == "HeadingSection":
            heading_node = node.first_child()
            headings.append(heading_node.data)

    for h in headings:
        assert isinstance(h.token.level, int), f"Expected int, got {h['level']!r}"
    return reversed(headings)


def get_parent_headings_raw(node: Node) -> list[str]:
    "Returns the raw text of node's parent headings in level order, which may not be consecutive"
    return [h["raw_text"] for h in get_parent_headings(node)]


def get_parent_headings_md(node: Node) -> list[str]:
    "Returns the markdown text of node's parent headings in level order, which may not be consecutive"
    return [f"{"#" * h.token.level} {h['raw_text']}" for h in get_parent_headings(node)]
