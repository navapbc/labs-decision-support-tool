import logging
import re
from pprint import pformat, pprint

import pytest
from nutree import Tree

from src.ingest_edd_web import EddChunkingConfig
from src.ingestion.markdown_chunking import (
    ChunkingConfig,
    NodeWithIntro,
    _add_chunks_for_list_or_table,
    chunk_tree,
    shorten,
)
from src.ingestion.markdown_tree import create_markdown_tree, render_nodes_as_md
from tests.src.ingestion.test_markdown_tree import create_paragraph, markdown_text  # noqa: F401

logger = logging.getLogger(__name__)


def test_shorten():
    assert shorten("This is a test.", 10) == "This is..."
    assert shorten("This is a test.", 10, placeholder=" ...") == "This ..."
    assert shorten("This is a test.", 15) == "This is a test."


# Uses the imported markdown_text fixture
@pytest.fixture
def prepped_tree(markdown_text) -> Tree:  # noqa: F811
    return create_markdown_tree(markdown_text)


def test_chunk_tree(markdown_text, prepped_tree):  # noqa: F811
    config = ChunkingConfig(175)
    chunks = chunk_tree(prepped_tree, config)
    logger.info(markdown_text)
    logger.info(prepped_tree.format())
    logger.info(pformat(chunks, width=140))
    assert len(chunks) == 8

    for chunk in chunks:
        assert chunk.length <= config.max_length

    table_chunks = [chunk for chunk in chunks if ":T_" in chunk.id]
    table_heading = "| H3.2.T1: header 1     | H3.2.T1: header 2     | H3.2.T1: header 3     | H3.2.T1: header 4     |\n"
    for i, chunk in enumerate(table_chunks):
        table_intro = "Table intro:\n\n" if i == 0 else "(Table intro:)\n\n"
        assert chunk.markdown.startswith(table_intro + table_heading)
        assert chunk.headings == ["Heading 1", "Heading 2", "Heading 3"]

    # Ensure all lines in the original markdown text are present in the chunked markdown
    all_chunk_text = "\n".join([chunk.markdown for chunk in chunks])
    all_text_min_spaces = re.sub(r" +", " ", all_chunk_text)
    for line in markdown_text.splitlines():
        # Ignore blank lines
        if line:
            if line.startswith("|"):  # It's part of a table
                if "| --- |" in line:
                    # Ignore table separators
                    continue
                # Check against the text with extra spaces removed
                assert line in all_text_min_spaces
            else:
                assert line in all_chunk_text

    chunks_wo_headings = [chunk for chunk in chunks if not chunk.headings]

    # first chunk with intro paragraph at the top-level + last chunk that includes a H3 and the last heading
    assert len(chunks_wo_headings) == 2
    assert chunks_wo_headings[0].markdown.startswith(
        "This is the first paragraph with no heading.\n\n# Heading 1"
    )
    assert chunks_wo_headings[1].markdown.startswith("### Heading 3\n")
    assert "# Second H1 without a paragraph" in chunks_wo_headings[1].markdown


def test_create_chunks_for_next_nodes():
    test_markdown = f"""Markdown with a very long paragraph that will trigger chunks_for_next_nodes() to be called.

# Heading 1
Sentence 1. {create_paragraph('H0.p1', 30)}
"""
    tree = create_markdown_tree(test_markdown, doc_name="Long paragraph doc")
    paragraph_node = tree["P_4"]
    paragraph_md = render_nodes_as_md([paragraph_node])

    config = ChunkingConfig(165)
    assert not config.nodes_fit_in_chunk([paragraph_node], paragraph_node)
    chunks = chunk_tree(tree, config)

    logger.info(pformat(chunks, width=140))
    paragraph_chunks = [chunk for chunk in chunks if "P_4" in chunk.id]
    assert len(paragraph_chunks) == 4

    joined_chunk_md = "\n".join([chunk.markdown for chunk in paragraph_chunks])
    sentences = [sentence.strip() for sentence in paragraph_md.split(". ")]
    sentence_counts = {sentence: joined_chunk_md.count(sentence) for sentence in sentences}
    # Ensure all sentences in the P_4 paragraph are present in the chunked markdown
    assert all(sentence_counts[sentence] >= 1 for sentence in sentences)

    # Ensure there are repeated sentences (chunk_overlap) in the chunked markdown
    repeated_sentences = [sentence for sentence, count in sentence_counts.items() if count > 1]
    assert len(repeated_sentences) > 3

    for chunk in paragraph_chunks:
        assert chunk.headings == ["Long paragraph doc", "Heading 1"]


def test_big_sublist_chunking():
    test_markdown = f"""Markdown with a list with very big sublists.

# Heading 1

List intro:
- Sublist 1
    * Sublist item 1.1. {create_paragraph('item 1.1', 30)}
    * Sublist item 1.2. {create_paragraph('item 1.2', 20)}
      Continued item 1.2 {create_paragraph('continued item 1.2', 10)}
"""
    pprint(test_markdown)

    if False:
        tree = create_markdown_tree(test_markdown, doc_name="Long paragraph doc")
        tree.print()

        config = EddChunkingConfig()

        node = tree["L_6"]
        intro_node = tree["H1_3"]
        nwi = NodeWithIntro(node, intro_node)
        _add_chunks_for_list_or_table(nwi, config)
        list_md = render_nodes_as_md([node])

        # paragraph_node = tree["P_4"]
        logger.info(pformat(config.chunks, width=140))

        joined_chunk_md = "\n".join([chunk.markdown for chunk in config.chunks])
        sentences = [sentence.strip() for sentence in re.split(r"(\. |\n)", list_md)]
        sentence_counts = {sentence: joined_chunk_md.count(sentence) for sentence in sentences}
        # Ensure all sentences in the P_4 paragraph are present in the chunked markdown
        # pprint(sentence_counts)
        assert all(sentence_counts[sentence] >= 1 for sentence in sentences)

    if True:
        config = ChunkingConfig(175)
        tree = create_markdown_tree(test_markdown, doc_name="Long paragraph doc")
        tree.print()
        chunks = chunk_tree(tree, config)
        logger.info(pformat(chunks, width=140))

    # assert False
