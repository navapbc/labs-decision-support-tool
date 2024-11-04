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
    create_markdown_tree,
    hide_span_tokens,
    prepare_tree,
    render_nodes_as_md,
)
from tests.src.ingestion.test_markdown_tree import create_paragraph, markdown_text  # noqa: F401


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
    prepare_tree(tree)
    return tree


from pprint import pprint


def test_chunk_tree(markdown_text, prepped_tree):  # noqa: F811
    config = ChunkingConfig(70)
    prepped_tree.print()
    chunks = chunk_tree(prepped_tree, config)
    pprint(list(chunks.values()), sort_dicts=False, width=140)
    assert len(chunks) == 13

    for _id, chunk in chunks.items():
        assert chunk.length <= config.max_length

    table_chunks = [chunk for id, chunk in chunks.items() if ":T_" in id]
    table_heading = "| H3.2.T1: header 1     | H3.2.T1: header 2     | H3.2.T1: header 3     | H3.2.T1: header 4     |\n"
    for i, chunk in enumerate(table_chunks):
        table_intro = "Table intro:\n\n" if i == 0 else "(Table intro:)\n\n"
        assert chunk.markdown.startswith(table_intro + table_heading)
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


def test_create_chunks_for_next_nodes():
    test_markdown = f"""Markdown with a very long paragraph that will trigger chunks_for_next_nodes() to be called.

# Heading 1
Sentence 1. {create_paragraph('H0.p1', 30)}
"""
    tree = create_markdown_tree(test_markdown, doc_name="Long paragraph doc")
    prepare_tree(tree)
    paragraph_node = tree["P_4"]
    paragraph_md = render_nodes_as_md([paragraph_node])

    config = ChunkingConfig(65)
    assert not config.nodes_fit_in_chunk([paragraph_node])
    chunks = chunk_tree(tree, config)

    pprint(list(chunks.values()), sort_dicts=False, width=140)
    paragraph_chunks = [chunk for chunk in chunks.values() if "P_4" in chunk.id]
    assert len(paragraph_chunks) == 6

    joined_chunk_md = "\n".join([chunk.markdown for chunk in paragraph_chunks])
    sentences = [sentence.strip() for sentence in paragraph_md.split(". ")]
    sentence_counts = {sentence: joined_chunk_md.count(sentence) for sentence in sentences}
    # Ensure all sentences in the P_4 paragraph are present in the chunked markdown
    assert all(sentence_counts[sentence] >= 1 for sentence in sentences)

    # Ensure there are repeated sentences (chunk_overlap) in the chunked markdown
    repeated_sentences = [sentence for sentence, count in sentence_counts.items() if count > 1]
    assert len(repeated_sentences) > 7

    for chunk in paragraph_chunks:
        assert chunk.headings == ["Long paragraph doc", "Heading 1"]
