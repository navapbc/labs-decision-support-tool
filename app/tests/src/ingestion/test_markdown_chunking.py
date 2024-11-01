import logging

import pytest
from nutree import Tree

from src.ingestion.markdown_chunking import (
    ChunkingConfig,
    chunk_tree,
    copy_subtree,
    find_closest_ancestor,
    remove_children_from,
    shorten,
)
from src.ingestion.markdown_tree import (
    add_list_and_table_intros,
    create_heading_sections,
    create_markdown_tree,
    hide_span_tokens,
    nest_heading_sections,
)
from tests.src.ingestion.test_markdown_tree import markdown_text  # noqa: F401


def test_shorten():
    assert shorten("This is a test.", 10) == "This is..."
    assert shorten("This is a test.", 10, placeholder=" ...") == "This ..."
    assert shorten("This is a test.", 15) == "This is a test."


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


@pytest.fixture
def tiny_tree():
    tree = Tree("NodeData tree")

    test_markdown = """
# My Heading 1

First paragraph.

List intro:
* Item 1
* Item 2
"""
    tree = create_markdown_tree(test_markdown)
    hide_span_tokens(tree)
    return tree


def test_copy_subtree(tiny_tree):
    list_tree = copy_subtree(tiny_tree["L_7"]).tree
    assert list_tree["L_7"] == list_tree["L_7"]
    assert repr(list_tree["L_7"].data) == repr(tiny_tree["L_7"].data)
    assert list_tree["L_7"].data is not tiny_tree["L_7"].data

    assert len(list_tree["L_7"].children) == 2
    for node_copy, node in zip(list_tree["L_7"].children, tiny_tree["L_7"].children, strict=True):
        assert repr(node_copy.data) == repr(node.data)
        assert node_copy.data is not node.data


def test_copy_one_node_subtree(tiny_tree):
    p_node = copy_subtree(tiny_tree["P_4"])
    assert len(p_node.children) == 0
    assert repr(p_node.data) == repr(tiny_tree["P_4"].data)


def test_remove_children(caplog, tiny_tree):
    list_node = copy_subtree(tiny_tree["L_7"])
    assert [c.data_id for c in list_node.children] == ["LI_7", "LI_8"]
    # Remove the first child
    remove_children_from(list_node, {"LI_7"})
    assert [c.data_id for c in list_node.children] == ["LI_8"]

    # Remove remaining child
    remove_children_from(list_node, {"LI_8"})
    assert len(list_node.children) == 0

    # Restart with a fresh copy
    list_node = copy_subtree(tiny_tree["L_7"])
    with caplog.at_level(logging.WARNING):
        remove_children_from(list_node, {"LI_nonexistant"})
        assert [c.data_id for c in list_node.children] == ["LI_7", "LI_8"]
        assert "Expected to remove {'LI_nonexistant'}, but found only set()" in caplog.messages

    # Remove the last child
    with caplog.at_level(logging.WARNING):
        remove_children_from(list_node, {"LI_8", "LI_nonexistant"})
        assert [c.data_id for c in list_node.children] == ["LI_7"]
        assert any("found only {'LI_8'}" in msg for msg in caplog.messages)


# Uses the imported markdown_text fixture
@pytest.fixture
def prepped_tree(markdown_text) -> Tree:  # noqa: F811
    tree = create_markdown_tree(markdown_text)
    hide_span_tokens(tree)
    create_heading_sections(tree)
    nest_heading_sections(tree)
    add_list_and_table_intros(tree)
    return tree


def test_chunk_tree(markdown_text, prepped_tree):  # noqa: F811
    config = ChunkingConfig(60)
    chunks = chunk_tree(prepped_tree, config)
    assert len(chunks) == 13

    table_chunks = [chunk for id, chunk in chunks.items() if ":T_" in id]
    table_context = (
        "(Table intro:)\n\n"
        "| H3.2.T1: header 1     | H3.2.T1: header 2     | H3.2.T1: header 3     | H3.2.T1: header 4     |\n"
    )
    for chunk in table_chunks:
        assert chunk.markdown.startswith(table_context)
        assert chunk.headings == ["Heading 1", "Heading 2", "Heading 3"]

    # Ensure all lines in the original markdown text are present in the chunked markdown
    all_chunk_text = "\n".join([chunk.markdown for chunk in chunks.values()])
    for line in markdown_text.splitlines():
        # Ignore blank lines and table separators
        if line and "| --- |" not in line:
            assert line in all_chunk_text

    chunks_wo_headings = [chunk for _id, chunk in chunks.items() if not chunk.headings]
    # 1 doc intro paragraph + 2 H1 HeadingSections
    assert len(chunks_wo_headings) == 3
