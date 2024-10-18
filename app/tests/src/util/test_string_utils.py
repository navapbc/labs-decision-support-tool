from src.util import string_utils
from src.util.string_utils import (
    headings_as_markdown,
    remove_links,
    resolve_urls,
    split_list,
    split_markdown_by_heading,
    split_paragraph,
)


def test_split_paragraph():
    text = "This is a sentence. This is another sentence. This is a third sentence."
    assert string_utils.split_paragraph(text, 30) == [
        "This is a sentence.",
        "This is another sentence.",
        "This is a third sentence.",
    ]


def test_split_paragraph_on_overly_long_sentence():
    text = "This is a sentence. This is a really, really long sentence. This is a third sentence."
    assert string_utils.split_paragraph(text, 30) == [
        "This is a sentence.",
        "This is a really,",
        " really long sentence.",
        "This is a third sentence.",
    ]


def test_split_list():
    text = (
        "Following are list items:\n"
        "    - This is a sentence.\n"
        "    - This is another sentence.\n"
        "    - This is a third sentence."
    )
    assert string_utils.split_list(text, 90) == [
        (
            "Following are list items:\n"
            "    - This is a sentence.\n"
            "    - This is another sentence."
        ),
        ("Following are list items:\n    - This is a third sentence."),
    ]


def test_resolve_urls_scenario1():
    base_url = "https://example.com"
    markdown = "[This is a link](/relative/path) and [another](https://example.com/absolute/path)"
    assert (
        string_utils.resolve_urls(base_url, markdown)
        == "[This is a link](https://example.com/relative/path) and [another](https://example.com/absolute/path)"
    )


def test_resolve_urls_scenario2():
    base_url = "https://example.com/some_webpage"
    markdown = "[This is a link](relative/path) and [another](path2/index.html)"
    assert (
        string_utils.resolve_urls(base_url, markdown)
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
