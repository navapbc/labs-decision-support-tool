import pytest

from src.util.string_utils import (
    headings_as_markdown,
    parse_heading_markdown,
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


def test_split_list():
    text = (
        "Following are list items:\n"
        "    - This is a sentence.\n"
        "    - This is another sentence.\n"
        "    - This is a third sentence."
    )
    assert split_list(text, 90) == [
        (
            "Following are list items:\n"
            "    - This is a sentence.\n"
            "    - This is another sentence."
        ),
        (
            "Following are list items:\n"  #
            "    - This is a third sentence."
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


def test_resolve_urls_scenario_anchor():
    base_url = "https://example.com"
    markdown = "Go to [this heading](#some_heading)"
    assert resolve_urls(base_url, markdown) == markdown


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


def test_headings_as_markdown():
    assert headings_as_markdown([]) == ""

    assert headings_as_markdown(["Heading 1"]) == "# Heading 1"

    assert (
        headings_as_markdown(["Heading 1", "Heading 2", "Heading 3"])
        == "# Heading 1\n## Heading 2\n### Heading 3"
    )


def test_parse_heading_markdown():
    assert parse_heading_markdown("# Heading at level 1") == (1, "Heading at level 1")
    assert parse_heading_markdown("### Heading at level 3") == (3, "Heading at level 3")
    with pytest.raises(ValueError):
        assert parse_heading_markdown("Non-heading text")


def test_remove_links():
    markdown = "[This is a link](relative/path) and [another](https://example.com/absolute/path)"
    assert remove_links(markdown) == "This is a link and another"
