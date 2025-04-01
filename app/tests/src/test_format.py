import re

from src.citations import CitationFactory, split_into_subsections
from src.format import FormattingConfig, _get_breadcrumb_html, format_response
from src.generate import MessageAttributes
from src.retrieve import retrieve_with_scores
from tests.src.test_retrieve import _create_chunks


def _get_chunks_with_scores():
    _create_chunks()
    return retrieve_with_scores("Very tiny words.", retrieval_k=2, retrieval_k_min_score=0.0)


def _unique_accordion_ids(html):
    return set(
        [html[m.start() + 4 : m.end() - 1] for m in re.finditer(" id=accordion-\\d*>", html)]
    )


def to_subsections(chunks_with_scores):
    return split_into_subsections([c.chunk for c in chunks_with_scores], factory=CitationFactory())


def test__get_breadcrumb_html():
    headings = []
    assert _get_breadcrumb_html(headings, "Doc name") == "<div>&nbsp;</div>"

    # Omit first heading
    headings = ["Heading 1", "Heading 2", "Heading 3"]
    assert _get_breadcrumb_html(headings, "Doc name") == "<div><b>Heading 2 → Heading 3</b></div>"

    # Omit empty headings
    headings = ["Heading 1", "", "Heading 3"]
    assert _get_breadcrumb_html(headings, "Doc name") == "<div><b>Heading 1 → Heading 3</b></div>"

    # Omit headings that match doc name
    headings = ["Doc name", "Heading 2"]
    assert _get_breadcrumb_html(headings, "Doc name") == "<div><b>Heading 2</b></div>"


def test_format_response(chunks_with_scores):
    subsections = to_subsections(chunks_with_scores)

    config = FormattingConfig()
    msg_attribs = MessageAttributes(needs_context=True, translated_message="")
    # Test empty response
    assert format_response(subsections, "", config, msg_attribs) == "<div></div>"

    # Test non-existent citation
    assert (
        format_response([], "Non-existent citation: (citation-0)", config, msg_attribs)
        == "<div><p>Non-existent citation: </p></div>"
    )

    # Test markdown list formatting
    assert (
        format_response([], "List intro sentence: \n- item 1\n- item 2", config, msg_attribs)
        == "<div><p>List intro sentence: </p>\n<ul>\n<li>item 1</li>\n<li>item 2</li>\n</ul></div>"
    )

    # Test real citations
    html = format_response(
        subsections, "Some real citations: (citation-1) (citation-2)", config, msg_attribs
    )
    assert len(_unique_accordion_ids(html)) == 2
    assert "Source(s)" in html
    assert "usa-accordion__button" in html
    assert "usa-accordion__content" in html
