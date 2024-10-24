from itertools import count
import mistletoe
from mistletoe import block_token
from mistletoe.block_token import TableRow
from mistletoe.markdown_renderer import MarkdownRenderer
from nutree import Tree, Node, StopTraversal, IterMethod


def new_md_renderer() -> MarkdownRenderer:
    block_token.reset_tokens()
    return MarkdownRenderer(normalize_whitespace=False)


def normalize_markdown(markdown: str) -> str:
    with new_md_renderer() as renderer:
        doc = mistletoe.Document(markdown)
        return renderer.render(doc)


def create_nutree_from_md(markdown, normalize_md=False) -> Tree:
    if normalize_md:
        markdown = normalize_markdown(markdown)
    doc = mistletoe.Document(markdown)
    tree = Tree("MD Document")
    create_nutree(tree, doc)
    return tree


def create_md_renderer() -> MarkdownRenderer:
    # Refering to MarkdownRenderer:335.render_table()
    def custom_render_table_row(token: TableRow, max_line_length: int | None = None):
        content = []

        table_token = token.parent if token.parent else None
        # get from parent Table token; table header doesn't have a parent
        column_align = table_token.column_align if token.parent else [None]
        if table_token:
            # content = [["my header 1", "2", "3"],[]] # TODO: get header from sibling TableRow token
            table_header = token.parent.header
            print("Table header", table_header)
            table_header_list = [["my header 1", "2", "3"], []]

        self = renderer
        content.append(self.table_row_to_text(token))
        col_widths = self.calculate_table_column_widths(content)
        # if table_header_list:
        #     content[1] = self.table_separator_line_to_text(col_widths, column_align)

        return [self.table_row_to_line(col_text, col_widths, column_align) for col_text in content]

    renderer = new_md_renderer()
    renderer.render_map["TableRow"] = custom_render_table_row
    print("Creating custom MarkdownRenderer:", renderer)
    return renderer


TYPE_ATTRIBUTES = {
    # https://www.markdownguide.org/extended-syntax/#footnotes
    # Footnote definitions can be found anywhere in the document,
    # but footnotes will always be listed in the order they are referenced
    # to in the text (and will not be shown if they are not referenced).
    "Document": {"type", "line_number", "token", "footnotes"},
    "Heading": {"type", "line_number", "token", "level"},
    "Link": {"title", "target", "type", "token"},
    "List": {"start", "loose", "token", "type", "line_number"},
    # loose: indicates whether the list items are separated by blank lines
    # leader: The prefix number or bullet point
    "ListItem": {"indentation", "leader", "line_number", "loose", "prepend", "token", "type"},
    "Paragraph": {"type", "line_number", "token"},
    "RawText": {"type", "token", "content"},
    "Strong": {"type", "token"},
    "Table": {"column_align", "header", "line_number", "token", "type"},
    "TableCell": {"align", "type", "line_number", "token"},
    "TableRow": {"row_align", "type", "line_number", "token"},
}

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
]


renderer = create_md_renderer()

# TODO: allow this to be extensible to store other attributes
class MyNode:
    counter = count()

    def __init__(self, token, type, heading_token=None):
        self.id = f"my.{self.counter.__next__()}"
        self.token = token
        self.type = type
        self.chunked = False  # if this node and its children are chunked
        self.summaries = (
            []
        )  # list of summaries for this node, ordered by char/token length; longest first
        self.heading_token = heading_token

    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        if key in _KNOWN_Node_Attribs:
            setattr(self, key, value)
        elif key in ["type"]:
            assert value == self.type, f"Type mismatch: {value} != {self.type}"
        elif key in ["children"]:
            print("Ignoring children attribute")
        else:
            print(f"New attrib?: {key}={value}", self)
            setattr(self, key, value)

    def __repr__(self):
        md_str = getattr(self, "content", "")[:100]
        if not md_str:
            if self.type in ["Heading", "TableRow", "Paragraph", "ListItem"]:
                # print(self.renderer)
                md_str = renderer.render(self.token)
            elif self.type in ["HeadingSection"]:
                md_str = renderer.render(self.heading_token)
        return f"MyNode {self.id}: {self.type}: {md_str}"


def create_nutree(parent, token):
    node = MyNode(token, getattr(token, "type", "None"))
    tnode = parent.add(node, data_id=node.id)
    # Python 3.6 uses [ordered dicts] [1].
    # Put in 'type' entry first to make the final tree format somewhat
    # similar to [MDAST] [2].
    #
    #   [1]: https://docs.python.org/3/whatsnew/3.6.html
    #   [2]: https://github.com/syntax-tree/mdast
    node.type = token.__class__.__name__
    for attrname in ["content", "footnotes"]:
        if attrname in vars(token):
            node[attrname] = getattr(token, attrname)
    for attrname in token.repr_attributes:
        node[attrname] = getattr(token, attrname)
    if "header" in vars(token):  # e.g., Table header
        node["header"] = create_nutree(tnode, getattr(token, "header"))
        # assert False, f"What is this? {getattr(token, 'header')}"
        # tnode.add(node['header'])
    if token.children is not None:
        [create_nutree(tnode, child) for child in token.children]
        # for tchild in children_tnodes:
        #     tnode.add(tchild, data_id=f"my.{counter.__next__()}")

    return tnode


def any_descendants_block_tokens(node: Node, parent_class) -> Node:
    memo={"found_node": None}
    def is_block_token(node: Node, memo):
        if isinstance(node.data.token, parent_class):
            memo["found_node"] = node
            # print("Found descendant", node.data.token)
            return StopTraversal
    node.visit(is_block_token, memo=memo)
    return memo["found_node"]

def collapse_span_tokens(tree, renderer):
    rendering = []
    for node in tree.iterator(method=IterMethod.POST_ORDER): # Depth-first-traversal, post-order
        token = node.data.token
        token_class = token.__class__.__name__
        if isinstance(token, block_token.BlockToken):
            # If all children have no BlockTokens, then collapse unless one of these.
            # TODO: Address complex tables with BlockTokens nested in TableRows;
            #   For now, render TableRow assuming no nested BlockTokens
            if not token_class in ["TableRow"] and any_descendants_block_tokens(node, block_token.BlockToken):
                print("Not rendering; has descendant block_token:", node.data)
                continue

            # These ignored_token_blocks are rendered by other token_blocks
            if token_class in ["TableCell", "Document"]:
                print("Ignoring b/c handled elsewhere:", node.data.type)
                continue

            print("Collapsing", node.data.type, len(node.children))
            rendering.append(renderer.render(token))
            node.remove_children()
    return rendering

def siblings_up_to(node, stop_type):
    next = node.next_sibling()
    while next and next.data.type != stop_type:
        yield next
        next = next.next_sibling()

def create_heading_sections(tree):
    for n in tree:
        if n.data.type == "Heading":
            print(n.data)
            if siblings := list(siblings_up_to(n, "Heading")):
                hsection_node = n.prepend_sibling(MyNode("HeadingSection", "HeadingSection", heading_token=n.data.token))
                n.move_to(hsection_node)
                for sibling in siblings:
                    print("> ", sibling.data)
                    sibling.move_to(hsection_node)


def shorten(node):
    md_str = create_md_str(node)
    return f"{md_str[:20]!r}(SHORTENED)"

CHAR_LIMIT = 512

def create_md_str(node: Node):
    token = node.data.token
    print(isinstance(token, block_token.BlockToken), node.data.type)
    if isinstance(token, block_token.BlockToken):
        md_str = renderer.render(token)
    elif node.data.type == "HeadingSection":
        md_str_list = []
        for c in node.children:
            if isinstance(c.data.token, block_token.BlockToken) and c.data.type not in ["TableCell"]:
                md_str_list.append(renderer.render(c.data.token))
            else:
                print("create_md_str not rendering: ", c.data.token)
        md_str = "\n".join(md_str_list)
    else:
        assert False, f"Empty md_str for {node.data.type} {node.data.id}"
    return md_str

def chunk_nodes(node: Node, memo):
    md_str = create_md_str(node)
    if len(md_str) < CHAR_LIMIT:
        print(f"YAY: Chunked {node.data.type} ({node.data.id}) with len {len(md_str)}: {md_str[:20]}...{md_str[-10:]}")
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
        if n.data.id in memo or n.data.id+".0" in memo: # if chunked
            chunked_list.append(n)

    # Try chunking again but with shortened heading sections
    md_str_list = []
    for n in node.children:
        if n in chunked_list:
            md_str_list.append(shorten(n))
            continue
        else:
            md_str = create_md_str(n)
            if len(md_str) > CHAR_LIMIT:
                assert False, f"Child section too long for {n.data.type} {n.data.id} with {len(md_str)}"
            else:
                md_str_list.append(md_str)

    # If fit in single chunk
    md_str = "\n".join(md_str_list)
    if len(md_str) <= CHAR_LIMIT:
        print(f"YAY: Chunked {node.data.type} ({node.data.id}) with len {len(md_str)}: {md_str[:20]!r}...{md_str[-10:]!r}")
        memo[node.data.id].append(md_str)
        return

    # Split into chunks
    print(f"Retrying chunking {node.data.type} {node.data.id} with {len(md_str)}")
    counter = count()
    md_str = ""
    for md in md_str_list:
        if len(md_str) > CHAR_LIMIT:
            assert False, f"Too long {len(md_str)}: {md_str}"
        next_md_str = md_str + "\n" + md
        if len(next_md_str) > CHAR_LIMIT:
            memo_key = node.data.id+f".{counter.__next__()}"
            memo[memo_key].append(md_str)
            print(f"Chunked {memo_key} with len {len(md_str)}")
            md_str = md
    if md_str: # Last chunk
        memo_key = node.data.id+f".{counter.__next__()}"
        memo[memo_key].append(md_str)
        print(f"Chunked {memo_key} with len {len(md_str)}")
    
    if next(counter) == 0:
        print(f"!! Overfilling chunk for {node.data.type} {node.data.id}") # FIXME
        md_str = create_md_str(n)
        memo[node.data.id].append(md_str)
        
