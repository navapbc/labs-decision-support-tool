from src.util.string_utils import (
    deconstruct_list,
    deconstruct_table,
    ensure_blank_line_suffix,
    headings_as_markdown,
    reconstruct_list,
    reconstruct_table,
    remove_links,
    resolve_urls,
    split_list,
    split_markdown_by_heading,
    split_paragraph,
)


def test_split_paragraph():
    text = "This is a sentence. This is another sentence. This is a third sentence."
    assert split_paragraph(text, 30) == [
        "This is a sentence.",
        "This is another sentence.",
        "This is a third sentence.",
    ]


def test_split_paragraph_on_overly_long_sentence():
    text = "This is a sentence. This is a really, really long sentence. This is a third sentence."
    assert split_paragraph(text, 30) == [
        "This is a sentence.",
        "This is a really,",
        " really long sentence.",
        "This is a third sentence.",
    ]


def test_ensure_blank_line_suffix():
    assert ensure_blank_line_suffix("This is a sentence.") == "This is a sentence.\n\n"
    assert ensure_blank_line_suffix("This is a sentence.\n") == "This is a sentence.\n\n"
    assert ensure_blank_line_suffix("This is a sentence.\n\n") == "This is a sentence.\n\n"


TEST_LIST_MARKDOWN = (
    "Following are list items:\n"
    "    - This is a sentence.\n"
    "    - This is another sentence.\n"
    "    - This is a third sentence."
)


CHUNKED_TEST_LIST = [
    (
        "Following are list items:\n\n"
        "    - This is a sentence.\n"
        "    - This is another sentence.\n"
    ),
    (
        "Following are list items:\n\n"  #
        "    - This is a third sentence."
    ),
]


def test_split_list():
    assert split_list(TEST_LIST_MARKDOWN, 90) == CHUNKED_TEST_LIST


def test_deconstruct_and_reconstruct_list():
    intro_sentence = "Following are list items:\n"
    deconstructed_list_items = [
        "    - This is a sentence.\n",
        "    - This is another sentence.\n",
        "    - This is a third sentence.",
    ]

    assert deconstruct_list(TEST_LIST_MARKDOWN) == (intro_sentence, deconstructed_list_items)

    assert reconstruct_list(90, intro_sentence, deconstructed_list_items) == CHUNKED_TEST_LIST


def test_deconstruct_and_reconstruct_table():
    table_markdown = (
        "Following is a table:\n"
        "| Header 1 | Header 2 |\n"
        "| --- | --- |\n"
        "| Row 1, col 1 | Row 1, col 2 |\n"
        "| Row 2, col 1 | Row 2, col 2 |\n"
    )

    intro_sentence = "Following is a table:\n"
    table_header = "| Header 1 | Header 2 |\n| --- | --- |\n"
    table_rows = [
        "| Row 1, col 1 | Row 1, col 2 |\n",
        "| Row 2, col 1 | Row 2, col 2 |\n",
    ]

    assert deconstruct_table(table_markdown) == (intro_sentence, table_header, table_rows)

    assert reconstruct_table(100, intro_sentence, table_header, table_rows) == [
        (
            "Following is a table:\n\n"
            "| Header 1 | Header 2 |\n"
            "| --- | --- |\n"
            "| Row 1, col 1 | Row 1, col 2 |\n"
        ),
        (
            "Following is a table:\n\n"
            "| Header 1 | Header 2 |\n"
            "| --- | --- |\n"
            "| Row 2, col 1 | Row 2, col 2 |\n"
        ),
    ]


def test_resolve_urls_scenario1():
    base_url = "https://example.com"
    markdown = "[This is a link](/relative/path) and [another](https://example.com/absolute/path)"
    assert (
        resolve_urls(base_url, markdown)
        == "[This is a link](https://example.com/relative/path) and [another](https://example.com/absolute/path)"
    )


def test_resolve_urls_scenario2():
    base_url = "https://example.com/some_webpage"
    markdown = "[This is a link](relative/path) and [another](path2/index.html)"
    assert (
        resolve_urls(base_url, markdown)
        == "[This is a link](https://example.com/some_webpage/relative/path) and [another](https://example.com/some_webpage/path2/index.html)"
    )


def test_split_markdown_by_heading():
    markdown = (
        "Intro text\n"
        "# Heading 1\n"
        "Some text under heading 1\n"
        "## Heading 2\n"
        "Some text under heading 2\n"
        "### Heading 3\n"
        "Some text under heading 3"
    )
    heading_sections = list(split_markdown_by_heading(markdown))
    assert heading_sections == [
        ((), "Intro text"),
        (("Heading 1",), "Some text under heading 1"),
        (("Heading 1", "Heading 2"), "Some text under heading 2"),
        (("Heading 1", "Heading 2", "Heading 3"), "Some text under heading 3"),
    ]
    assert len(heading_sections[0][0]) == 0
    assert len(heading_sections[1][0]) == 1
    assert len(heading_sections[2][0]) == 2


def test_headings_as_markdown():
    assert headings_as_markdown([]) == ""

    assert headings_as_markdown(["Heading 1"]) == "# Heading 1"

    assert (
        headings_as_markdown(["Heading 1", "Heading 2", "Heading 3"])
        == "# Heading 1\n## Heading 2\n### Heading 3"
    )


def test_remove_links():
    markdown = "[This is a link](https://example.com/relative/path) and [another](https://example.com/absolute/path)"
    assert remove_links(markdown) == "This is a link and another"
