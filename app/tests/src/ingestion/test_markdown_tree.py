import logging

import pytest
from nutree import Tree

from src.ingestion.markdown_tree import (
    add_list_and_table_intros,
    create_heading_sections,
    create_markdown_tree,
    describe_tree,
    hide_span_tokens,
    nest_heading_sections,
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

A paragraph under "Second H1>Heading 3". {create_paragraph('H1>H3.p1', 2)} Following list has *no* intro.

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
    tree = create_markdown_tree(markdown_text)
    print(markdown_text)
    tree.print()

    tree_descr = assert_tree_structure(tree)
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

    doc_node = tree.children[0]
    assert len(doc_node.children) == 40
    assert_content(tree)
    assert len(tokens_vs_tree_mismatches(tree)) == 0


def test_tree_preparation(markdown_text):
    tree = create_markdown_tree(markdown_text)
    tree_descr = assert_tree_structure(tree)
    assert tree_descr["counts"]["RawText"] > 0
    assert tree_descr["counts"]["Strong"] > 0
    assert tree_descr["counts"]["Emphasis"] > 0
    assert tree_descr["counts"]["Link"] == 1
    assert tree_descr["counts"]["TableCell"] == 12

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
            "BlankLine",
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
            "BlankLine",
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
        assert list_nodes[1].data["intro"] == "Following list has *no* intro.\n"
        table_node = tree.find_first(match=lambda n: n.data_type == "Table")
        assert table_node.data["intro"] == "Table intro:\n"

        assert_content(tree)
