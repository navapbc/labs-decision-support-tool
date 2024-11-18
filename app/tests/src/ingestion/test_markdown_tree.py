import json
import logging
import re

import pytest
from mistletoe import block_token
from nutree import Tree

from src.ingestion.markdown_tree import (
    TokenNodeData,
    add_list_and_table_intros,
    assert_no_mismatches,
    copy_subtree,
    create_heading_sections,
    create_markdown_tree,
    data_ids_for,
    describe_tree,
    find_closest_ancestor,
    find_node,
    get_parent_headings_md,
    get_parent_headings_raw,
    hide_span_tokens,
    markdown_tokens_as_json,
    nest_heading_sections,
    new_tree,
    next_renderable_node,
    remove_blank_lines,
    remove_children_from,
    render_subtree_as_md,
    tokens_vs_tree_mismatches,
)

logger = logging.getLogger(__name__)


def create_paragraph(paragraph_id: str, sentence_count: int) -> str:
    return " ".join([f"Paragraph {paragraph_id}, sentence {i + 2}." for i in range(sentence_count)])


def create_list(list_id: str, item_count: int, indent_level: int = 0) -> str:
    return "\n".join([f'{"  " * indent_level}* Item {list_id}.{i + 1}' for i in range(item_count)])


def create_table(table_id: str, row_count: int, column_count: int) -> str:
    header = f"| {' | '.join(f'{table_id}: header {c + 1}' for c in range(column_count))} |"
    separator = f"| {' | '.join(['---' for _ in range(column_count)])} |"
    rows = [
        f"| {" | ".join(f'{table_id}: row {r + 1}, col {c + 1}' for c in range(column_count))} |"
        for r in range(row_count)
    ]
    return "\n".join([header, separator] + rows)


@pytest.fixture
def markdown_text() -> str:
    return f"""
This is the first paragraph with no heading.

# Heading 1

First paragraph under Heading 1. {create_paragraph('H1.p1', 3)} Last sentence of 'H1.p1'.

Second paragraph under Heading 1. {create_paragraph('H1.p2', 5)} Last sentence of 'H1.p2'.

## Heading 2

Paragraph 1 under Heading 2 with [a link](http://to.nowhere.com). {create_paragraph('H2.p1', 3)} Last sentence of 'H2.p1'.

Paragraph 2 under Heading 2. {create_paragraph('H2.p2', 5)} Last sentence of 'H2.p2'.

List intro:

{create_list('H2.3.L1', 3)}

### Heading 3

Only paragraph under **Heading 3**. {create_paragraph('H3.p1', 3)} Last sentence.

Table intro:

{create_table('H3.2.T1', 3, 4)}

# Second H1 without a paragraph

### Skip to H3

A paragraph under "Second H1>Heading 3". {create_paragraph('H1>H3.p1', 2)} Following list has *this last sentence* as the intro.

{create_list('H1>H3.L1', 2)}
{create_list('H1>H3.L1.subL', 3, indent_level=1)}
{create_list('H1>H3.L1', 2)}

Paragraph before list with long list items.

* H1>H3.L2.1 -- {create_paragraph('L2.item1', 3)}
* H1>H3.L2.2 -- {create_paragraph('L2.item2', 4)}
* H1>H3.L2.3 -- {create_paragraph('L2.item3', 5)}

Final paragraph.
"""


def assert_content(tree: Tree):
    "These assertions should be true after any tree modification"
    heading_nodes = tree.find_all(match=lambda n: n.data_type == "Heading")
    assert len(heading_nodes) == 5

    list_nodes = tree.find_all(match=lambda n: n.data_type == "List")
    assert len(list_nodes) == 4
    assert len(list_nodes[0].children) == 3
    assert len(list_nodes[1].children) == 4
    # Check sublist ListItem on line 42
    assert tree["LI_42"].render() == "* Item H1>H3.L1.subL.1\n"
    # Indented correctly when entire list is rendered
    assert tree["L_40"].render() == (
        "* Item H1>H3.L1.1\n"  #
        "* Item H1>H3.L1.2\n"  #
        "  * Item H1>H3.L1.subL.1\n"  #
        "  * Item H1>H3.L1.subL.2\n"  #
        "  * Item H1>H3.L1.subL.3\n"  #
        "* Item H1>H3.L1.1\n"  #
        "* Item H1>H3.L1.2\n"  #
    )

    table_nodes = tree.find_all(match=lambda n: n.data_type == "Table")
    assert len(table_nodes) == 1
    assert len(table_nodes[0].children) == 3
    assert "| H3.2.T1: row 1, col 1 |" in table_nodes[0].first_child().render()
    assert "| H3.2.T1: row 3, col 4 |" in table_nodes[0].last_child().render()

    paragraph_nodes = tree.find_all(match=lambda n: n.data_type == "Paragraph")
    assert len(paragraph_nodes) == 24


def assert_tree_structure(tree: Tree):
    "These assertions should be true after any tree modification"
    tree_descr = describe_tree(tree)

    assert tree_descr["counts"]["Document"] == 1
    assert tree_descr["counts"]["Paragraph"] == 24
    assert tree_descr["counts"]["Heading"] == 5
    assert tree_descr["counts"]["List"] == 4
    assert tree_descr["counts"]["ListItem"] == 13
    assert tree_descr["counts"]["Table"] == 1
    assert tree_descr["counts"]["TableRow"] == 3

    children_of = tree_descr["children"]
    assert "Paragraph" in children_of["Document"]
    assert children_of["List"] == {"ListItem"}
    # ListItem can have a child Paragraph or List (i.e., nested list)
    assert children_of["ListItem"] == {"List", "Paragraph"}
    assert children_of["Table"] == {"TableRow"}
    return tree_descr


def test_create_markdown_tree(markdown_text):
    _tree = create_markdown_tree(markdown_text, prepare=False)
    tree_descr = assert_tree_structure(_tree)
    parent_of = tree_descr["parents"]
    # These are true initially but will change after tree preparation
    assert parent_of["Heading"] == {"Document"}
    assert parent_of["RawText"] == {
        "Heading",
        "Paragraph",
        "Emphasis",
        "Strong",
        "Link",
        "TableCell",
    }

    children_of = tree_descr["children"]
    assert "Heading" in children_of["Document"]
    assert children_of["Heading"] == {"RawText"}
    assert children_of["Paragraph"] == {"RawText", "Emphasis", "Strong", "Link"}
    assert children_of["TableRow"] == {"TableCell"}
    assert children_of["TableCell"] == {"RawText"}

    doc_node = _tree.children[0]
    assert len(doc_node.children) == 40
    assert_content(_tree)
    assert len(tokens_vs_tree_mismatches(_tree)) == 0


@pytest.fixture
def tree(markdown_text):
    return create_markdown_tree(markdown_text, prepare=False)


def test_markdown_tokens_as_json(markdown_text):
    json_str = markdown_tokens_as_json(markdown_text)
    tokens = json.loads(json_str)
    assert tokens["type"] == "Document"

    assert tokens["children"][0]["type"] == "Paragraph"
    assert tokens["children"][0]["children"][0]["type"] == "RawText"
    assert (
        tokens["children"][0]["children"][0]["content"]
        == "This is the first paragraph with no heading."
    )

    assert tokens["children"][1]["type"] == "Heading"
    assert tokens["children"][1]["children"][0]["content"] == "Heading 1"


def test_tree_preparation(tree):
    tree_descr = assert_tree_structure(tree)
    assert tree_descr["counts"]["RawText"] > 0
    assert tree_descr["counts"]["Strong"] > 0
    assert tree_descr["counts"]["Emphasis"] > 0
    assert tree_descr["counts"]["Link"] == 1
    assert tree_descr["counts"]["TableCell"] == 12

    for run_no in range(2):
        # Step 0: Remove BlankLine nodes
        removed_count = remove_blank_lines(tree)
        if run_no == 0:
            assert removed_count > 0
        else:
            assert removed_count == 0
        bl_nodes = tree.find_all(match=lambda n: n.data_type == "BlankLine")
        assert len(bl_nodes) == 0

    # Run multiple times to ensure idempotency
    for run_no in range(2):
        # Step 1: Hide all span-level tokens to simplify the tree
        hide_count = hide_span_tokens(tree)
        if run_no == 0:
            assert hide_count > 0
        else:
            assert hide_count == 0
        tree_descr = assert_tree_structure(tree)
        # All span-level tokens are collapsed into a Paragraph, Heading, ListItem, or TableRow
        assert tree_descr["counts"]["RawText"] == 0
        assert tree_descr["counts"]["Strong"] == 0
        assert tree_descr["counts"]["Emphasis"] == 0
        assert tree_descr["counts"]["Link"] == 0
        # TableCells are collapsed into a single TableRow
        assert tree_descr["counts"]["TableCell"] == 0
        children_of = tree_descr["children"]
        assert len(children_of["Heading"]) == 0
        assert len(children_of["Paragraph"]) == 0
        assert len(children_of["TableRow"]) == 0

    for run_no in range(2):
        # Step 2: Create HeadingSection nodes to group Headings with their text content
        nodes_created = create_heading_sections(tree)
        tree_descr = assert_tree_structure(tree)
        if run_no == 0:
            assert nodes_created == tree_descr["counts"]["Heading"] == 5
        else:
            assert nodes_created == 0
        assert tree_descr["counts"]["HeadingSection"] == tree_descr["counts"]["Heading"] == 5
        parent_of = tree_descr["parents"]
        assert parent_of["Heading"] == {"HeadingSection"}
        assert parent_of["HeadingSection"] == {"Document"}
        children_of = tree_descr["children"]
        assert children_of["HeadingSection"] == {
            "Heading",
            "List",
            "Paragraph",
            "Table",
        }

    for run_no in range(2):
        # Step 3: Move HeadingSection nodes to be under their respective Heading parent
        nodes_moved = nest_heading_sections(tree)
        if run_no == 0:
            assert nodes_moved == 3  # The other 2 headings are H1 and don't need moving
        else:
            assert nodes_moved == 0
        tree_descr = assert_tree_structure(tree)
        parent_of = tree_descr["parents"]
        assert parent_of["HeadingSection"] == {"Document", "HeadingSection"}
        children_of = tree_descr["children"]
        assert children_of["HeadingSection"] == {
            "Heading",
            "List",
            "Paragraph",
            "Table",
            "HeadingSection",
        }

    for run_no in range(2):
        nodes_changed = add_list_and_table_intros(tree)
        if run_no == 0:
            assert (
                nodes_changed == tree_descr["counts"]["List"] + tree_descr["counts"]["Table"] == 5
            )
        else:
            assert nodes_changed == 0

        list_nodes = tree.find_all(match=lambda n: n.data_type == "List")
        assert list_nodes[0].data["intro"] == "List intro:\n"
        assert (
            list_nodes[1].data["intro"] == "Following list has *this last sentence* as the intro.\n"
        )
        table_node = tree.find_first(match=lambda n: n.data_type == "Table")
        assert table_node.data["intro"] == "Table intro:\n"

        assert_content(tree)


def test_subtree_rendering(tree):
    md = render_subtree_as_md(tree.first_child())
    # Check that various markdown elements are present in the rendered text
    assert "This is the first paragraph with no heading." in md
    assert "# Second H1 without a paragraph" in md
    assert "Paragraph 1 under Heading 2 with [a link](http://to.nowhere.com)." in md
    assert "Paragraph H3.p1, sentence 4. Last sentence." in md
    assert "| H3.2.T1: row 2, col 3 |" in md
    assert "* Item H1>H3.L1.2" in md
    assert "  * Item H1>H3.L1.subL.3" in md
    assert "Final paragraph." in md

    remove_blank_lines(tree)
    hide_span_tokens(tree)
    create_heading_sections(tree)
    nest_heading_sections(tree)
    add_list_and_table_intros(tree)
    heading_section_md = render_subtree_as_md(tree["_S2_10"])
    assert "## Heading 2" in heading_section_md
    assert "under Heading 2 with [a link](http://to.nowhere.com)." in heading_section_md
    assert "* Item H2.3.L1.1" in heading_section_md
    assert "### Heading 3" in heading_section_md
    assert "| H3.2.T1: header 1     | H3.2.T1: header 2" in heading_section_md

    # The following relies on remove_blank_lines(tree) being called above
    rendered_md = render_subtree_as_md(tree["D_1"])
    assert_extra_newlines_removed(rendered_md)

    rendered_md = render_subtree_as_md(tree["_S2_10"])
    assert_extra_newlines_removed(rendered_md)


def assert_extra_newlines_removed(markdown: str):
    "Assert that there are no extra blank lines"
    assert "\n\n\n" not in markdown
    # Each block markdown element should be separated by exactly two newlines
    for block_str in markdown.split("\n\n"):
        # Check for no extraneous newlines within blocks
        if re.search(r"^\* ", block_str) or re.search(r"^\| ", block_str):
            # Handle list items and table rows individually
            list_items = block_str.split("\n")
            assert all("\n" not in list_item for list_item in list_items)
        else:
            assert "\n" not in block_str


def test_get_parent_headings(tree):
    hide_span_tokens(tree)  # copies heading text to Heading nodes
    create_heading_sections(tree)  # creates HeadingSections used by get_parent_headings()
    nest_heading_sections(tree)  # creates a hierarchy of HeadingSections

    table_node = tree.find_first(match=lambda n: n.data_type == "Table")
    headings = get_parent_headings_md(tree[table_node.data_id])
    assert headings == ["# Heading 1", "## Heading 2", "### Heading 3"]

    assert tree["H3_22"].data_type == "Heading"
    assert tree["H3_22"].token.level == 3
    # tree["_S3_22"] is a level 3 Heading
    headings = get_parent_headings_md(tree["H3_22"])
    # The result should not include the level 3 Heading itself
    assert headings == ["# Heading 1", "## Heading 2"]

    headings = get_parent_headings_md(tree["LI_42"])
    assert headings == ["# Second H1 without a paragraph", "### Skip to H3"]

    headings = get_parent_headings_raw(tree["LI_42"])
    assert headings == ["Second H1 without a paragraph", "Skip to H3"]


def test_raw_text_on_headings():
    test_markdown = """
# Heading with [a link](google.com)

Sentence 1.
"""
    tree = create_markdown_tree(test_markdown, prepare=True)
    assert tree["H1_2"].data["raw_text"] == "Heading with a link"


def create_paragraph_node_data(line_number: int, lines: list[str]) -> TokenNodeData:
    token = block_token.Paragraph(lines=lines)
    token.line_number = line_number

    ndata = TokenNodeData(token, id_suffix="_para")
    ndata["freeze_token_children"] = True
    return ndata


def test_new_tree():
    test_markdown = """Intro

Sentence 1.
"""
    tree = create_markdown_tree(test_markdown, doc_name="test tree", doc_source="nowhere.com")
    doc_node = tree.first_child()
    assert doc_node.data["name"] == "test tree"
    assert doc_node.data["source"] == "nowhere.com"
    assert tree["D_1"].data.data_type == tree["D_1"].data_type == "Document"
    assert tree["P_3"].data.data_type == tree["P_3"].data_type == "Paragraph"
    with pytest.raises(ValueError):
        tree["nonexistent_id"]

    d1 = tree["D_1"]
    p3 = tree["P_3"]
    with new_tree("test tree copying", copying_tree=True) as subtree:
        d1.copy_to(subtree, deep=True)

    assert subtree.count == 3
    assert subtree["D_1"].data.data_type == "Document"

    # Check that copies were made
    assert subtree["D_1"] is not d1
    assert subtree["D_1"].data is not d1.data
    assert subtree["D_1"].data.id_string == d1.data.id_string
    assert subtree["D_1"].data.token is not d1.data.token

    # Check that copies of child were made
    assert subtree["P_3"] is not p3
    assert subtree["P_3"].data is not p3.data
    assert subtree["P_3"].data.id_string == p3.data.id_string
    assert subtree["P_3"].data.token is not p3.data.token
    assert subtree["P_3"].data.token.line_number == p3.data.token.line_number

    # More quick checks for increased code coverage
    assert subtree["P_3"].data.token.line_number == subtree["P_3"].data.line_number
    assert data_ids_for(subtree["D_1"]) == ["P_1", "P_3"]
    assert find_node(subtree, "D_1") is subtree["D_1"]
    assert find_node(subtree, "Non-existant") is None

    # Check retrieval by token
    assert subtree[subtree["P_3"].data.token] == subtree["P_3"]

    # Check that the tree structure is the same, except for the first line which has the tree name
    assert tree.format().splitlines()[1:] == subtree.format().splitlines()[1:]
    # Check that they render markdown the same:
    d1_md = TokenNodeData.render_token(d1.token)
    subtree_d1_md = TokenNodeData.render_token(subtree["D_1"].data.token)
    assert d1_md == subtree_d1_md

    # Modifying subtree should not affect original tree
    with assert_no_mismatches(subtree):
        orig_child_count = len(tree["P_3"].parent.children)
        ndata = create_paragraph_node_data(2, ["New paragraph text"])
        p2 = subtree["P_3"].parent.add(ndata, before=subtree["P_3"])
    assert subtree.count == 4
    assert len(tree["P_3"].parent.children) == orig_child_count
    assert len(subtree["P_3"].parent.children) == orig_child_count + 1

    with assert_no_mismatches(subtree):
        p2.remove(keep_children=True)
    assert subtree.count == 3
    assert len(tree["P_3"].parent.children) == orig_child_count
    assert len(subtree["P_3"].parent.children) == orig_child_count


def test_MdNodeData_repr(tree):
    hide_span_tokens(tree)
    create_heading_sections(tree)
    nest_heading_sections(tree)
    out_str = tree.format()

    # Spot check a few lines
    assert "Tree<'Markdown tree'>" in out_str
    assert "╰── Document D_1 line_number=1" in out_str
    assert "    ├── Paragraph P_2 of length" in out_str
    assert "    ├── HeadingSection _S1_4" in out_str
    assert "    │   ╰── HeadingSection _S2_10" in out_str
    assert "    │       ├── List L_18 line_number=18 loose=False start=None" in out_str
    assert "    │       │   ├── ListItem LI_18: \"'* Item H2.3.L1.1" in out_str


def test_next_renderable_node(markdown_text):
    tree = create_markdown_tree(markdown_text)
    assert next_renderable_node(tree["P_2"]) == tree["_S1_4"]
    assert next_renderable_node(tree["LI_18"]) == tree["LI_19"]
    assert next_renderable_node(tree["LI_44"]) == tree["LI_45"]
    assert next_renderable_node(tree["LI_46"]) == tree["P_48"]
    assert next_renderable_node(tree["P_54"]) is None


@pytest.fixture
def tiny_tree():
    test_markdown = """
# My Heading 1

First paragraph.

List intro:
* Item 1
* Item 2
"""
    tree = create_markdown_tree(test_markdown, prepare=False)
    hide_span_tokens(tree)
    return tree


def test_copy_subtree(tiny_tree):
    list_tree = copy_subtree("TINY", tiny_tree["L_7"]).tree
    assert list_tree["L_7"] == list_tree["L_7"]
    assert repr(list_tree["L_7"].data) == repr(tiny_tree["L_7"].data)
    assert list_tree["L_7"].data is not tiny_tree["L_7"].data

    assert len(list_tree["L_7"].children) == 2
    for node_copy, node in zip(list_tree["L_7"].children, tiny_tree["L_7"].children, strict=True):
        assert repr(node_copy.data) == repr(node.data)
        assert node_copy.data is not node.data


def test_copy_one_node_subtree(tiny_tree):
    p_node = copy_subtree("TINY", tiny_tree["P_4"])
    assert len(p_node.children) == 0
    assert repr(p_node.data) == repr(tiny_tree["P_4"].data)


def test_remove_children(caplog, tiny_tree):
    list_node = copy_subtree("TINY", tiny_tree["L_7"])
    assert [c.data_id for c in list_node.children] == ["LI_7", "LI_8"]
    # Remove the first child
    remove_children_from(list_node, {"LI_7"})
    assert [c.data_id for c in list_node.children] == ["LI_8"]

    # Remove remaining child
    remove_children_from(list_node, {"LI_8"})
    assert len(list_node.children) == 0

    # Restart with a fresh copy
    list_node = copy_subtree("TINY", tiny_tree["L_7"])
    with caplog.at_level(logging.WARNING):
        remove_children_from(list_node, {"LI_nonexistant"})
        assert [c.data_id for c in list_node.children] == ["LI_7", "LI_8"]
        assert "Expected to remove {'LI_nonexistant'}, but found only []" in caplog.messages

    # Remove the last child
    with caplog.at_level(logging.WARNING):
        remove_children_from(list_node, {"LI_8", "LI_nonexistant"})
        assert [c.data_id for c in list_node.children] == ["LI_7"]
        assert any("found only ['LI_8']" in msg for msg in caplog.messages)


@pytest.fixture
def str_tree():
    tree = Tree("test tree")
    doc = tree.add("doc")
    child = doc.add("1child")
    grandchild = child.add("2grandchild")
    grandchild.add("3great_grandchild")
    return tree


def test_find_closest_ancestor(str_tree):
    ggchild = str_tree["3great_grandchild"]
    assert find_closest_ancestor(ggchild, lambda n: "child" in n.data) == str_tree["2grandchild"]
    assert find_closest_ancestor(ggchild, lambda n: "child" in n.data, include_self=True) == ggchild
    assert find_closest_ancestor(ggchild, lambda n: "1" in n.data) == str_tree["1child"]
    assert find_closest_ancestor(ggchild, lambda n: "nowhere" in n.data) is None
