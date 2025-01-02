import pytest

from src.util.string_utils import (
    format_highlighted_uri,
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


def test_citation_formatting():
    subsection_text = "* [CalFresh](https://www.getcalfresh.org/?source=edd) (formerly known as Food Stamps)  \n  CalFresh provides monthly food assistance to people and families with low income, including those who lost their job because of the pandemic. Visit [GetCalFresh.org](https://www.getcalfresh.org/?source=edd) to apply online.\n* [California Association of Food Banks](http://www.cafoodbanks.org/)  \n  In California, federal, state, and local community organizations coordinate to make sure that groceries are available at local food banks.\n* [Free Summer Lunch Programs](http://www.cde.ca.gov/ds/sh/sn/summersites.asp)  \n  Free lunches are available to all children under 18, regardless of income.\n* [School Meals](https://www.fns.usda.gov/school-meals/applying-free-and-reduced-price-school-meals)  \n  Free or reduced-price breakfast and lunch at public schools when in session.\n* [Women, Infants and Children (WIC) Program](https://www.cdph.ca.gov/Programs/CFH/DWICSN/Pages/Program-Landing1.aspx)  \n  Pregnant women and children under age 5 receive nutrition support at WIC."
    source_url = "https://edd.ca.gov/en/disability/options_to_file_for_pfl_benefits/"
    highlighted_url = format_highlighted_uri(source_url, subsection_text)

    assert (
        highlighted_url
        == "https://edd.ca.gov/en/disability/options_to_file_for_pfl_benefits#:~:text=CalFresh%20https%20www%20getcalfresh%20org,receive%20nutrition%20support%20at%20WIC"
    )
