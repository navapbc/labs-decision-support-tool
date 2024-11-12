import itertools
import logging
import pprint
import textwrap
from collections import defaultdict
from contextlib import contextmanager
from copy import copy
from typing import Any, Callable, Iterator, Iterable, Optional, Sequence

import mistletoe
from mistletoe import block_token
from mistletoe import span_token
from mistletoe import token as token_cls
from mistletoe.ast_renderer import AstRenderer
from mistletoe.markdown_renderer import MarkdownRenderer
from mistletoe.token import Token
from nutree import IterMethod, Node, Tree

from src.util.string_utils import remove_links

logger = logging.getLogger(__name__)


#  TODO: Handle footnotes in Document node
#     # https://www.markdownguide.org/extended-syntax/#footnotes
#     # Footnote definitions can be found anywhere in the document,
#     # but footnotes will always be listed in the order they are referenced
#     # to in the text (and will not be shown if they are not referenced).


# region ##### Custom tree node to handle updates to mistletoe tokens


class TokenAwareNode(Node):
    """
    block_types = container_types + list_types
    container_types = "Document", "HeadingSection", "ListItem", and probably "TableCell"
        - we have to update token.children (to render partials) based on tree structure;
    list_types = "List", "Table"
        - List has "ListItem"s
        - Table has "TableRow"s (which has "TableCell"s)
        - we have to update token.children (to render partials) based on tree structure

    leaf_types = non-block_types = no children = "Paragraph", "Heading"
        - we don't modify token.children; these tokens are frozen as indicated by node.data["freeze_token_children"]
    """

    def __init__(self, data, **kwargs):
        super().__init__(data, **kwargs)
        if self._copy_data_flag():
            logger.debug("Copying data for new node %s in %s", self.data_id, self.tree.name)
            self.set_data(copy(data))
            if self.has_token():
                self._copy_token()

                # If token is not frozen (frozen=children have been hidden and shouldn't be modified),
                # then we'll be manipulating the children as a result of modifying the tree,
                # so reset token children to be consistent with the tree
                if not self._is_token_frozen():
                    self.data.token.children = []

    def _copy_token(self):
        logger.debug("Copying token for new node %s in %s", self.data_id, self.tree.name)
        if self.data_type == "Paragraph":
            # Calling copy() on Paragraph tokens doesn't work, so copy it manually
            doc_token = self.tree.first_child().data.token
            assert doc_token.type == "Document", f"Expected Document, got {doc_token.type}"
            self.data.token = _copy_paragraph_token(self.data.token, doc_token)
        else:
            self.data.token = copy(self.data.token)

    def add_child(
        self,
        child: Node | Tree | Any,
        *,
        before: Node | None = None,
        deep: bool | None = None,
        data_id=None,
        node_id=None,
    ) -> Node:
        logger.debug("%s add_child: %s", self.data_id, child.data_id)
        child_node = super().add_child(
            child, before=before, deep=deep, data_id=data_id, node_id=node_id
        )

        if self._sync_token_applicable() and child_node.has_token():
            self.assert_unfrozen_token()
            if self.data.token.children is None:
                self.data.token.children = []
            if child_node.data.token not in self.data.token.children:
                logger.debug("Updating token.children of %s in %s", self.data_id, self.tree.name)
                if before:
                    self._add_child_token(child_node, before)
                else:
                    self.data.token.children += [child_node.data.token]
        return child_node

    def _add_child_token(self, child_node: Node, before: Node):
        while not before.has_token() and before.next_sibling():
            before = before.next_sibling()
        if before.has_token():
            children = list(self.data.token.children)
            index = children.index(before.data.token)
            children.insert(index, child_node.data.token)
            self.data.token.children = children
        else:
            logger.debug("Before-node %r has no token; appending to the end", before.data_id)
            self.data.token.children += [child_node.data.token]

    # Many tree and node  methods call add()
    add = add_child

    def _copy_data_flag(self) -> bool:
        return self.tree.system_root.get_meta("data_and_token_copying")

    def _sync_token_applicable(self) -> bool:
        return self.has_token() and self.tree.system_root.get_meta("sync_token")

    def has_token(self) -> bool:
        return isinstance(self.data, TokenNodeData)

    def assert_unfrozen_token(self) -> None:
        assert (
            self.has_token() and not self._is_token_frozen()
        ), f"Cannot modify node {self.data_id}"

    def _is_token_frozen(self) -> bool:
        return bool(
            find_closest_ancestor(
                self,
                lambda p: p.has_token() and p.data["freeze_token_children"],
                include_self=True,
            )
        )

    def remove(self, *, keep_children=False, with_clones=False) -> None:
        logger.info("Removing %s from %s", self.data_id, self.tree.name)
        if self._sync_token_applicable() and self.parent and self.parent.has_token():
            parent_token = self.parent.data.token
            if self.data.token in parent_token.children:
                # Parent token must be modifiable
                self.parent.assert_unfrozen_token()
                logger.info("Removing token %s from %s", self.data_id, self.tree.name)
                parent_token.children.remove(self.data.token)

            if keep_children:
                # Parent token must be modifiable
                self.parent.assert_unfrozen_token()
                logger.debug("Moving grandchildren to be children for %s", self.data_id)
                parent_token.children += self.data.token.children

        return super().remove(keep_children=keep_children, with_clones=with_clones)

    def remove_children(self) -> None:
        if self._sync_token_applicable() and not self._is_token_frozen():
            self.assert_unfrozen_token()
            logger.debug("Removing all children tokens of %s in %s", self.data_id, self.tree.name)
            self.data.token.children = None

        return super().remove_children()


def _copy_paragraph_token(
    token: block_token.Paragraph, doc_token: block_token.Document
) -> block_token.Paragraph:
    assert token.type == "Paragraph", f"Expected Paragraph, got {token.type}"
    assert doc_token, "doc_token not provided"
    # Paragraph tokens can have children, so rather than recursively copying them,
    # just render the markdown text and reparse it to create new tokens
    md = TokenNodeData.render_token(token)
    with TokenNodeData.md_renderer:
        # token_cls._root_node needs to be set for Paragraphs that appear to reference footnotes
        token_cls._root_node = doc_token
        copied = block_token.Paragraph(lines=[md])
        token_cls._root_node = None

    copied.line_number = token.line_number
    copied.data_id = token.data_id
    copied.type = token.type

    # Ensure the copied token renders the same as the original token
    rendering = TokenNodeData.render_token(copied)
    assert md == rendering, f"{md!r} != {rendering!r}"

    return copied


# endregion
# region ##### Tree creation and validation functions


def markdown_tokens_as_json(markdown: str) -> str:
    """
    For the given markdown, returns mistletoe's resulting Tokens as JSON.
    Useful for examining the tokens used to create nodes in a create_markdown_tree().
    """
    with AstRenderer() as ast_renderer:
        doc = mistletoe.Document(markdown)
        ast_json = ast_renderer.render(doc)
        return ast_json


def create_markdown_tree(
    markdown: str,
    name: str = "Markdown tree",
    normalize_md: bool = True,
    doc_name: Optional[str] = None,
    doc_source: Optional[str] = None,
    prepare: bool = True,
) -> Tree:
    """
    Returns a tree reflecting the structure of the Tokens parsed from the markdown text.
    The tree is created using mistletoe's Tokens and our TokenNodeData class.

    Tokens represents the markdown text and are for rendering the markdown text.
    Tokens have `_parent` and `_children` attributes which are used by mistletoe.
    (Mistletoe's MarkdownRenderer expects the structure of the tokens to be a certain way,
    so modifications to tokens should be done carefully.)

    Tree nodes are for reasoning about splitting and chunking --
    we don't want to change the markdown text so the tokens can stay unmodified.
    An exception to this is for a special case where we need to split up large lists/tables and
    want to still have an intro sentence (and table header) in each split. In this case,
    some of the List/Table's token.children need to be removed so that MarkdownRenderer
    doesn't render the entire list/table -- it's not sufficient to remove the child tree node.

    Hence, the structure of the tree (i.e., each node's parent and children) is independent of
    each Token's parent and children. The structures are initially the same at the end of this
    function but may differ after tree preparation functions are applied.
    For example, when nest_heading_sections() moves the tree nodes around
    (i.e., nesting H2 nodes under corresponding H1 nodes), the tokens are unmodified
    (so a Heading token's children does *not* include a Heading token)
    because MarkdownRenderer does not expect this.

    To render markdown text, use render_*_as_md(node), which uses MarkdownRenderer on the
    tokens wrapped within the node desired to be rendered.
    """
    if normalize_md:
        markdown = normalize_markdown(markdown)
    with _new_md_renderer():
        # "Never call Document(...) outside of a with ... as renderer block"
        # Otherwise, markdown_renderer.BlankLine, HtmlSpan, etc will not be created and possibly other features
        doc = mistletoe.Document(markdown)
    # The shadow_attrs=True argument allows accessing node.data.age as node.age -- see validate_tree()
    with new_tree(name) as tree:
        _populate_nutree(tree.system_root, doc)
        doc_node = tree.first_child()
        if doc_name:
            assert doc_node.data_type == "Document"
            doc_node.data["name"] = doc_name
        if doc_source:
            doc_node.data["source"] = doc_source

    # Now that tree is populated, enable syncing of tokens to ensure no token mismatches
    tree.system_root.set_meta("sync_token", True)
    # Initialize prep_funcs meta attribute to record tree prep functions applied to the tree
    tree.system_root.set_meta("prep_funcs", [])
    if prepare:
        with assert_no_mismatches(tree):
            _prepare_tree(tree)
    return tree


@contextmanager
def assert_no_mismatches(tree: Tree) -> Iterator[Tree]:
    "Use this to ensure that the tree's nodes and tokens are in sync after tree structure modifications"
    yield tree
    if mismatches := tokens_vs_tree_mismatches(tree):
        logger.error("Mismatches %s", pprint.pformat(mismatches, sort_dicts=False, width=170))
    assert not mismatches, "Mismatches found in tree"


@contextmanager
def new_tree(name: str, copying_tree: bool = False) -> Iterator[Tree]:
    # Setting calc_data_id allows the data_id to be correctly set for nodes created
    # by functions that don't take a data_id argument, like node.copy_to().
    # Otherwise, copy_to() assigns a random data_id to the new node.
    tree = Tree(name, factory=TokenAwareNode, calc_data_id=_get_node_data_id, shadow_attrs=True)

    if copying_tree:
        tree.system_root.set_meta("data_and_token_copying", True)
        tree.system_root.set_meta("sync_token", True)

    with assert_no_mismatches(tree):
        yield tree
        validate_tree(tree)


def _get_node_data_id(_tree: Tree, data: Any) -> str:
    """
    In addition to being used to set the data_id of a node, this is called by nutree to find a node
    e.g., tree['H1_2'] and tree[node.token]
    """
    if isinstance(data, MdNodeData):
        return data.data_id
    elif isinstance(data, Token):
        return data.data_id
    raise ValueError(f"Cannot find node: {data!r}")


def normalize_markdown(markdown: str) -> str:
    """
    Markdown includes multiple ways of specifying headers, table header separators, etc.
    Normalize the markdown text to a consistent standard to ensure consistent parsing and rendering.
    """
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


def _populate_nutree(parent: Node, child_token: Token):
    child_node = parent.add(TokenNodeData(child_token))
    if isinstance(child_node.token.children, tuple):
        # Some token.children are tuples; convert them into lists for consistency
        child_node.token.children = list(child_node.token.children)
    if child_token.children:
        # Recurse to create children nodes
        for grandchild in child_token.children:
            _populate_nutree(child_node, grandchild)


def validate_tree(tree: Tree) -> None:
    for node in tree:
        # Check data_id
        if tree[node.data_id] is not node:
            nodes = tree.find_all(data_id=node.data_id)
            logger.error("Found %d nodes with data_id %r", len(nodes), node.data_id)
            raise AssertionError(
                f"Node {node.data_id!r} has mismatched node: {tree[node.data_id]} != {node!r}"
            )
        assert (
            node.data_id == node.data.data_id
        ), f"Node {node.data_id!r} has mismatched data_id: {node.data_id!r} != {node.data.data_id!r}"

        # Check data_type
        assert (
            node.data_type == node.data.data_type
        ), f"Node {node.data_id!r} has mismatched data_type: {node.data.data_type!r} and {node.data.token.type!r}"

        if node.has_token():
            # Check token data_id
            assert (
                node.data_id == node.data.token.data_id
            ), f"Node {node.data_id!r} has mismatched data_id: {node.data_id!r} != {node.data.token.data_id!r}"

            # Check token data_type
            assert (
                node.data_type == node.data.token.type == node.data.token.__class__.__name__
            ), f"Node {node.data_id!r} has mismatched data_type: {node.data.data_type!r} and {node.data.token.type!r}"


def tokens_vs_tree_mismatches(tree: Tree) -> dict:
    """
    Return the tokens' parent-and-children mismatches compared to the tree structure.
    Use this as a sanity check after manipulating the tree.
    """
    mismatches: dict[str, list[str]] = defaultdict(list)
    for node in tree:
        if node.tree is not tree:
            mismatches["wrong_tree"].append(f"{node.data_id}: {node.tree} is not {tree}")

        if not node.has_token() or not node.is_block_token():
            continue

        if node.parent:
            if node.parent.has_token() and node.token.parent != node.parent.token:
                mismatches["diff_parent"].append(
                    f"{node.data_id}: {node.token.parent} != {node.parent.token}"
                )
        elif node.token.parent:
            mismatches["has_parent"].append(
                f"{node.data_id} is missing a parent node for {node.token.parent}"
            )

        if node.children:
            node_children_tokens = [c.token for c in node.children if c.has_token()]
            if node_children_tokens != node.token.children:
                mismatches["diff_children"].append(
                    f"{node.data_id}: {node_children_tokens} != {node.token.children}"
                )
        elif node.token.children:
            token_children = [
                c
                for c in node.token.children
                # Special case: TableCell tokens are hidden by hide_span_tokens()
                if isinstance(c, block_token.BlockToken) and c.type != "TableCell"
            ]
            if token_children:
                mismatches["has_children"].append(
                    f"{node.data_id} is missing block-token children: {token_children}"
                )
    return mismatches


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
        if node.has_token():
            tokens[node.data_type].update(node.token.__dict__.keys())
    return {
        "counts": counts,
        "children": children,
        "parents": parents,
        "tokens": tokens,
    }


# endregion
# region ##### Tree and node copy functions


def copy_subtree(name: str, node: Node, include_descendants: bool = True) -> Tree:
    """
    Returns a new tree for the node, its descendants, and optionally its ancestors (to capture headings).
    Each node's contents is deep-copied, including node.data and node.data.token.
    """
    with new_tree(f"{name}:{node.data_id}", copying_tree=True) as subtree:
        logger.info("Copying to subtree %r", subtree.name)
        # Copy the nodes and descendants
        new_node = copy_with_ancestors(node, subtree, include_descendants=include_descendants)
        assert new_node.data_id == node.data_id, f"Expected data_id {node.data_id!r} for {new_node}"

        # Copy the meta attributes from the original tree so that get_parent_headings() works
        # Do this after populating tree so meta values don't interfere
        for k, v in node.tree.system_root.meta.items():
            if not subtree.system_root.get_meta(k):
                subtree.system_root.set_meta(k, copy(v))

    # At this point, no object in the subtree should be pointing to objects in the original tree,
    # except for tokens associated with "freeze_token_children", which should never be modified.
    # We can now modify the new tree without affecting the original tree.
    return new_node


def copy_with_ancestors(node: Node, tree: Tree, include_descendants: bool = True):
    logger.debug("copy_with_ancestors %s to %s", node.data_id, tree.name)
    # Ancestors are needed to get_parent_headings()
    new_parent = copy_ancestors(node, tree)
    # Copy the nodes and descendants
    return node.copy_to(new_parent, deep=include_descendants)


def copy_ancestors(node: Node, target_tree: Tree) -> Node:
    "Copy the ancestors of node to target_tree, returning the deepest ancestor in the target tree"
    tgt_node = target_tree.system_root
    for src_parent in node.get_parent_list():
        existing_node = next(
            (c for c in tgt_node.children if c.data_id == src_parent.data_id), None
        )
        if not existing_node:
            logger.debug("Copying %s to parent %s", src_parent.data_id, tgt_node.data_id)
        tgt_node = existing_node or src_parent.copy_to(tgt_node, deep=False)
    return tgt_node


def remove_children_from(node: Node, child_data_ids: set[str]) -> None:
    "Remove children nodes with data_id in child_data_ids from node. Used on tree from copy_subtree()."
    # Create a list of child nodes to remove, then remove them
    # Do not remove children while iterating through them
    nodes_to_remove = [c for c in node.children if c.data_id in child_data_ids]
    if len(nodes_to_remove) != len(child_data_ids):
        logger.warning(
            "Expected to remove %s, but found only %s",
            child_data_ids,
            [n.data_id for n in nodes_to_remove],
        )
    for child_node in nodes_to_remove:
        child_node.remove()


# endregion
# region ##### Rendering functions


def render_nodes_as_md(nodes: Sequence[Node]) -> str:
    "Render nodes as markdown text for chunking"
    return "".join([render_subtree_as_md(node) for node in nodes])


def render_subtree_as_md(node: Node) -> str:
    """
    Render the node and its descendants (a subtree) to markdown text.
    Since the structure of the tree (i.e., each node's parent and children) is independent of each Token's parent and children,
    we cannot rely on mistletoe's renderer (which is based on Tokens) to render the tree correctly. Hence, we have this function.
    Whenever this method is called in a loop, join the result with no delimiter: `"".join(result)`
    """
    if node.data_type in [
        "HeadingSection",  # Doesn't have mistletoe's token for rendering
        "Document",  # Its token.children reference all headings and many paragraphs, which are now under HeadingSection nodes
        "ListItem",  # TODO: Try removing "ListItem" after rewriting unit tests that ensure their token.childen are consistent with the tree
    ]:
        # For these data_types, use node.children for rendering instead of relying on node.data.token.children
        # A result from render_subtree_as_md() ends with exactly 2 newlines, so join without a separator
        md_str = "".join([render_subtree_as_md(node) for node in node.children])
    elif node.has_token():
        out_str = []
        if intro := _intro_if_needed(node):
            out_str.append(intro)
        out_str.append(TokenNodeData.render_token(node.token))
        # Since each element ends exactly 1 newline "\n",
        # this join() will result in each element ending with "\n\n",
        # which is consistent with how markdown block elements are separated.
        md_str = "\n".join(out_str) + "\n"
    else:
        raise ValueError(f"Unexpected node type: {node.id_string}")
    return md_str


def _intro_if_needed(node: Node) -> str | None:
    "Return intro text if 'intro' has text and 'show_intro' is True."
    if (intro := node.data["intro"]) and node.data["show_intro"]:
        return f"({intro.strip()})\n"
    return None


# endregion
# region ##### NodeData classes wrapped by tree nodes


class MdNodeData:
    "Node.data points to instances of this class or its subclass"

    def __init__(self, data_type: str, data_id: str):
        self.data_type = data_type
        self.data_id = data_id

    # Allow adding custom attributes to this node data object; useful during tree manipulation or chunking
    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key, None)

    @property
    def id_string(self) -> str:
        return f"{self.data_type} {self.data_id}"

    def render(self) -> str:
        return ""

    def __repr__(self) -> str:
        "This is called from tree.print()"
        oneliner = [self.id_string]

        # Provide some text content for referencing back to the markdown text
        content = self.content_oneliner()

        return " ".join(oneliner) + (f": {content!r}" if content else "")

    ONELINER_CONTENT_LIMIT = 100

    def content_oneliner(self) -> str:
        content = self["oneliner_of_hidden_nodes"]
        if not content:
            content = getattr(self, "content", "")[: MdNodeData.ONELINER_CONTENT_LIMIT]
        return content


class HeadingSectionNodeData(MdNodeData):
    "HeadingSection nodes have a Heading node and other nodes (including other HeadingSection nodes) as children"

    def __init__(self, heading_node: Node):
        assert isinstance(heading_node.token, block_token.Heading)
        self.heading_node = heading_node

        # "raw_text" is set if hide_span_tokens() has been called
        self.raw_text = heading_node.data["raw_text"]
        if self.raw_text is None:
            self.raw_text = _extract_raw_text(heading_node)

        data_id = f"_S{self.level}_{heading_node.token.line_number}"
        super().__init__("HeadingSection", data_id)

    @property
    def level(self) -> int:
        return self.heading_node.token.level

    @property
    def line_number(self) -> int:
        return self.heading_node.token.line_number

    @property
    def rendered_text(self) -> str:
        return self.heading_node.render()


class TokenNodeData(MdNodeData):
    counter = itertools.count()

    @staticmethod
    def get_id_prefix(token: block_token.BlockToken) -> str:
        if token.type == "Heading":
            return f"H{token.level}"
        return "".join(char for char in token.type if char.isupper())

    def __init__(self, token: Token, id_suffix: str = ""):
        self.token = token
        # Add 'type' attribute to token object for consistently referencing a token's and MdNodeData's type
        token.type = token.__class__.__name__

        if token.type == "TableCell":
            # Use lowercase "tc" prefix b/c it's typically encapsulated into TableRow like a span token
            _id = f"tc{next(self.counter)}_{token.line_number}"
        elif self.is_block_token():
            # Block tokens start on a new line so use the line number in the id
            _id = f"{self.get_id_prefix(token)}_{token.line_number}"
        else:  # Span tokens use a lower case prefix; they can be ignored and are hidden by hide_span_tokens()
            _id = f"s.{next(self.counter)}"
        _id += id_suffix
        super().__init__(token.type, _id)

        # Add 'data_id' attribute to the token object for easy cross-referencing -- see validate_tree()
        token.data_id = self.data_id

        # Table tokens needs special initialization for rendering partial tables later
        if token.type == "Table":
            self._init_for_table()

    def is_block_token(self) -> bool:
        return isinstance(self.token, block_token.BlockToken)

    @property
    def line_number(self) -> int:
        return self.token.line_number

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
        # md_renderer should always be used within a context manager
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
        elif self.data_type in ["List", "Document"]:
            for attrname in self.token.repr_attributes:
                attrvalue = getattr(self.token, attrname)
                oneliner.append(f"{attrname}={attrvalue}")

        # Provide single-line text content for referencing back to the markdown text
        content = self.content_oneliner()
        if not content:
            if self.data_type in ["Document"]:
                content = f"{self['name']!r}"
            elif self.data_type in ["List", "BlankLine"]:
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


# endregion
# region ##### Tree preparation functions


def _prepare_tree(tree: Tree) -> None:
    "Typical preparation to make the tree easier to work with for chunking"
    remove_blank_lines(tree)
    hide_span_tokens(tree)
    create_heading_sections(tree)
    nest_heading_sections(tree)
    add_list_and_table_intros(tree)
    # Update the Document node.token.children to reflect the revised tree structure
    _update_token_children(tree.first_child())


def _update_token_children(n: Node):
    n.assert_unfrozen_token()
    n.data.token.children = [c.token for c in n.children if c.has_token()]


def remove_blank_lines(tree: Tree) -> int:
    "Remove BlankLine nodes from the tree. They clutter the tree and aren't needed for chunking."
    blank_line_counter = 0
    for node in find_data_type_nodes(tree, "BlankLine"):
        node.remove()
        blank_line_counter += 1

    tree.system_root.meta["prep_funcs"].append("remove_blank_lines")
    return blank_line_counter


@contextmanager
def _ignore_token_updates(tree: Tree):
    "Only used for tree preparation. Normally tokens are synced"
    tree.system_root.set_meta("sync_token", False)
    yield tree
    tree.system_root.set_meta("sync_token", True)


def hide_span_tokens(tree: Tree) -> int:
    "Hide span tokens that are sufficiently represented by their parent block tokens"
    hide_counter = 0
    for node in tree.iterator(method=IterMethod.POST_ORDER):  # Depth-first-traversal, post-order
        if (
            not node.has_children()  # Node should have children to hide
            or not node.has_token()  # Only TokenNodeData have token.children to render
            or not node.is_block_token()  # Only block tokens have children span tokens that can be hidden
        ):
            continue

        # Unless node is a TableRow, if any descendant is a BlockToken, then don't hide.
        if node.data_type in ["TableRow"]:
            # TODO: Address complex tables with BlockTokens nested in TableRows.
            #   For now, allow TableRow's children to be hidden assuming it has no nested BlockTokens besides TableCell.
            pass
        elif node.find_first(match=lambda n: n.is_block_token()):
            # Skip hiding this node's children since it contains a BlockToken
            continue

        # Ignore these data types
        if node.data_type in [
            "TableCell",  # TableCell and descendants will be hidden when its parent TableRow is processed
            "Document",  # It doesn't make sense to hide Document's children
        ]:
            continue

        logger.debug("Hiding %i children span-tokens under %s", len(node.children), node.data_id)

        # Create custom attribute for the hidden children's text so that tree.print() renders it
        node.data["oneliner_of_hidden_nodes"] = textwrap.shorten(
            remove_links(node.render()), 50, placeholder="...(hidden)", drop_whitespace=False
        )

        if node.data_type == "Heading":
            # Before RawText children are removed, add raw text content for
            # Heading nodes to use in heading breadcrumbs
            node.data["raw_text"] = _extract_raw_text(node)

        # Remove the children nodes, but node.token.children tokens are still retained for rendering
        with _ignore_token_updates(tree):
            node.remove_children()

        # Set attribute to indicate that node.token.children tokens should never be modified
        # since they've been hidden/removed from the tree.
        node.data["freeze_token_children"] = True

        hide_counter += 1

    # Ensure that all Paragraph nodes have no children and "freeze_token_children" is set
    # Paragraph tokens and their descendants should never be modified
    paragraph_nodes = find_data_type_nodes(tree, "Paragraph")
    assert all(not paragraph_node.has_children() for paragraph_node in paragraph_nodes)
    assert all(paragraph_node.data["freeze_token_children"] for paragraph_node in paragraph_nodes)

    tree.system_root.meta["prep_funcs"].append("hide_span_tokens")
    return hide_counter


def _extract_raw_text(node: Node) -> str:
    """
    Returns a join of all the content in all descendant RawText nodes under the node,
    excluding any formatting like bold, italics, etc.
    """
    raw_text_nodes = find_data_type_nodes(node, "RawText")
    return "".join([n.token.content for n in raw_text_nodes])


def create_heading_sections(tree: Tree) -> int:
    "Create custom HeadingSection nodes for each Heading node and its associated content"
    hsection_counter = 0
    heading_nodes = find_data_type_nodes(tree, "Heading")
    with _ignore_token_updates(tree):
        for n in heading_nodes:
            if n.parent.data_type == "HeadingSection":
                # Skip if the Heading is already part of a HeadingSection
                continue

            hsection_counter += 1
            hs_node_data = HeadingSectionNodeData(n)
            # Create tree node and insert so that markdown rendering of tree is consistent with original markdown
            hs_node = n.prepend_sibling(hs_node_data)
            # Get all siblings up to next Heading; these will be HeadingSection's new children
            children = list(_siblings_up_to(n, "Heading"))
            # Move in order the Heading and associated children to the new HeadingSection node
            n.move_to(hs_node)
            for body in children:
                body.move_to(hs_node)
            logger.debug("Created new %s", hs_node.data)

    tree.system_root.meta["prep_funcs"].append("create_heading_sections")
    return hsection_counter


def _siblings_up_to(node: Node, data_type: str) -> Iterable[Node]:
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
    with _ignore_token_updates(tree):
        for hs_node in heading_sections:
            # Traverse the headings in order and update the heading_stack
            heading_level = hs_node.level
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
                logger.debug(
                    "Moving %r under parent %r", hs_node.id_string, parent_hs_node.id_string
                )
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
    list_nodes = find_data_type_nodes(tree, "List")
    for n in list_nodes:
        if _add_intro_attrib(n):
            counter += 1

    table_nodes = find_data_type_nodes(tree, "Table")
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
                logger.debug("Skipping %s: already has intro %r", node.data_id, node.data["intro"])
                return False  # Don't override existing intro

            # Use the unformatted raw_text (for Heading nodes)
            intro_md = prev_node.data["raw_text"] or prev_node.render()
            # Limit size of intro by using only the last sentence
            node.data["intro"] = intro_md.split(". ")[-1]
            logger.debug("Added intro to %s: %r", node.data_id, node.data["intro"])
            # Mark the node being used as the intro as a hint when chunking to keep intro with the List/Table
            prev_node.data["is_intro"] = True
            return True
        elif prev_node.data_type in ["List", "BlockCode", "ThematicBreak"]:
            # ThematicBreak example: horizontal rule
            pass
        else:
            raise ValueError(f"{node.data_id} Unexpected prev node type: {prev_node.id_string}")
    return False


# endregion
# region ##### Heading breadcrumbs functions


def get_parent_headings(node: Node) -> Iterable[HeadingSectionNodeData]:
    """
    Return the list of node's parent HeadingSections in order of appearance in the markdown text.
    Check headings[i].level for the heading level, which may not be consecutive.
    """
    assert node.tree, f"Node {node.data_id} has no tree"
    for func in [
        "hide_span_tokens",  # copies heading text to Heading nodes
        "create_heading_sections",  # creates HeadingSections
        "nest_heading_sections",  # creates a hierarchy of HeadingSections
    ]:
        assert (
            func in node.tree.system_root.meta["prep_funcs"]
        ), f"{func}() must be called before get_parent_headings(): {node.tree.system_root.meta}"

    # If the node is a Heading and it's parent is a HeadingSection, start with the HeadingSection node instead
    # so that the node will not be included in the returned list.
    if node.data_type == "Heading" and node.parent.data_type == "HeadingSection":
        node = node.parent

    hsections: list[HeadingSectionNodeData] = []
    while node := node.parent:
        if isinstance(node.data, HeadingSectionNodeData):
            hsections.append(node.data)
    return reversed(hsections)


def get_parent_headings_raw(node: Node) -> list[str]:
    "Returns the raw text of node's parent headings in level order, which may not be consecutive"
    return [hs.raw_text.strip() for hs in get_parent_headings(node)]


def get_parent_headings_md(node: Node) -> list[str]:
    "Returns the markdown text of node's parent headings in level order, which may not be consecutive"
    return [hs.rendered_text.strip() for hs in get_parent_headings(node)]


# endregion
# endregion
# region ##### Tree read-only functions


def find_data_type_nodes(branch: Tree | Node, data_type: str) -> list[Node]:
    return branch.find_all(match=lambda n: n.data_type == data_type)


def find_node(tree: Tree, data_id: str) -> Node | None:
    return tree.find_first(match=lambda n: n.data_id == data_id)


def find_closest_ancestor(
    node: Node, does_match: Callable[[Node], bool], include_self: bool = False
) -> Node:
    "Return the first parent/ancestor node where does_match() returns True"
    if include_self and does_match(node):
        return node

    while node := node.parent:
        if does_match(node):
            return node

    return None


def data_ids_for(nodes: Iterable[Node]) -> list[str]:
    return [n.data_id for n in nodes]


def next_renderable_node(node) -> Node | None:
    "Return the next node that would be rendered as markdown text"
    while not (next_s := node.next_sibling()):
        if not (node := node.parent):
            break
    return next_s


# endregion
