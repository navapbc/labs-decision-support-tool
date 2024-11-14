import logging
import re
from pprint import pformat

import pytest
from nutree import Tree

from src.ingestion.markdown_chunking import ChunkingConfig, chunk_tree, shorten
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

    assert_all_text_in_some_chunk(markdown_text, chunks)

    chunks_wo_headings = [chunk for chunk in chunks if not chunk.headings]

    # first chunk with intro paragraph at the top-level + last chunk that includes a H3 and the last heading
    assert len(chunks_wo_headings) == 2
    assert chunks_wo_headings[0].markdown.startswith(
        "This is the first paragraph with no heading.\n\n# Heading 1"
    )
    assert chunks_wo_headings[1].markdown.startswith("### Heading 3\n")
    assert "# Second H1 without a paragraph" in chunks_wo_headings[1].markdown


def assert_all_text_in_some_chunk(text, chunks):
    "Ensure all lines in the original markdown text are present in the chunked markdown"
    all_chunk_text = "\n".join([chunk.markdown for chunk in chunks])
    all_text_minimal_spaces = re.sub(r" +", " ", all_chunk_text)
    for line in text.splitlines():
        # Ignore blank lines
        if line:
            if line.startswith("|"):  # It's part of a table
                if "| --- |" in line:
                    # Ignore table separators
                    continue
                # Check against the text with extra spaces removed
                assert line in all_text_minimal_spaces
                continue

            # Remove list bullets from line since sublists can be chunked separately
            # and the parent List node may be replaced with intro text
            line = re.sub(r"^ *[\-\*] ", "", line)
            # Paragraph may be split into multiple chunks so the whole line may not be present
            for sentence in line.split(". "):
                assert sentence.strip() in all_chunk_text


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
    assert len(paragraph_chunks) == 3

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
    * Sublist item 1.1. {create_paragraph('item 1.1', 10)}
    * Sublist item 1.2. {create_paragraph('item 1.2', 20)}
      Continued item 1.2 {create_paragraph('continued item 1.2', 10)}
"""
    config = ChunkingConfig(175)
    tree = create_markdown_tree(test_markdown, doc_name="Long paragraph doc")
    chunks = chunk_tree(tree, config)
    logger.info(test_markdown)
    logger.info(tree.format())
    logger.info(pformat(chunks, width=140))

    assert_all_text_in_some_chunk(test_markdown, chunks)

    # Separate chunks for the big text in the second sublist item
    p8_chunks = [chunk for chunk in chunks if "P_8" in chunk.id]
    assert len(p8_chunks) == 3

    # Chunks for the first sublist item
    l7_chunks = [chunk for chunk in chunks if "L_7" in chunk.id]
    assert len(l7_chunks) == 2
    assert l7_chunks[0].markdown.startswith("Sublist 1\n\n* Sublist item 1.1.")
    assert l7_chunks[1].markdown == "(Sublist 1)\n\n* (* Sublist item 1.2. Paragraph item 1.2,...)"

    # Final chunk with frontmatter text
    doc_chunk = next(chunk for chunk in chunks if "D_1" in chunk.id)
    assert (
        doc_chunk.markdown
        == "Markdown with a list with very big sublists.\n\n# Heading 1\n\nList intro:\n\n-"
    )

    assert len(chunks) == 6

    # assert False
