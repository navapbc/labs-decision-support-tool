from pprint import pprint

import pytest
from nutree import Tree

from src.ingestion.markdown_chunking import ChunkingState, chunk_tree
from src.ingestion.markdown_tree import (
    add_list_and_table_intros,
    create_heading_sections,
    create_markdown_tree,
    hide_span_tokens,
    nest_heading_sections,
)

# import the markdown_text fixture
from tests.src.ingestion.test_markdown_tree import markdown_text  # noqa: F401


@pytest.fixture
def prepped_tree(markdown_text) -> Tree:  # noqa: F811
    tree = create_markdown_tree(markdown_text)
    hide_span_tokens(tree)
    create_heading_sections(tree)
    nest_heading_sections(tree)
    add_list_and_table_intros(tree)
    return tree


def test_chunk_tree(prepped_tree):
    state = ChunkingState(430)
    chunk_tree(prepped_tree, state)
    prepped_tree.print()
    pprint(state.chunks, sort_dicts=False, width=120)
    print(len(state.chunks))
    sum(len(c.markdown) for c in state.chunks.values())
