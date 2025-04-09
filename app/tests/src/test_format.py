import re
from textwrap import dedent

from src.db.models.document import Subsection
from src.format import FormattingConfig, _get_breadcrumb_html, format_response
from src.generate import MessageAttributes
from tests.src.db.models.factories import ChunkFactory


def _unique_accordion_ids(html):
    return set(
        [html[m.start() + 4 : m.end() - 1] for m in re.finditer(" id=accordion-\\d*>", html)]
    )


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
    config = FormattingConfig()
    msg_attribs = MessageAttributes(needs_context=True, translated_message="")
    # Test empty response
    assert format_response([], "", config, msg_attribs) == "<div></div>"

    # Test markdown list formatting
    assert (
        format_response(
            [],
            dedent(
                """
                List intro sentence:
                - item 1
                - item 2

                List intro sentence:
                - item 1
                - item 2
                """
            ).strip(),
            config,
            msg_attribs,
        )
        == dedent(
            """
            <div><p>List intro sentence:</p>
            <ul>
            <li>item 1</li>
            <li>item 2</li>
            </ul>
            <p>List intro sentence:</p>
            <ul>
            <li>item 1</li>
            <li>item 2</li>
            </ul></div>
            """
        ).strip()
    )

    # Test nested list formatting
    assert (
        format_response(
            [],
            "List intro sentence: \n\n1. number 1\n   - subitem 1\n   - subitem 2",
            config,
            msg_attribs,
        )
        == dedent(
            """
            <div><p>List intro sentence: </p>
            <ol>
            <li>number 1<ul>
            <li>subitem 1</li>
            <li>subitem 2</li>
            </ul>
            </li>
            </ol></div>
            """
        ).strip()
    )

    # Test with citations
    subsections = [
        Subsection("1", ChunkFactory.build(), 0, ""),
        Subsection("2", ChunkFactory.build(), 1, ""),
    ]
    html = format_response(
        subsections, "Some real citations: (citation-1) (citation-2)", config, msg_attribs
    )
    assert len(_unique_accordion_ids(html)) == 2
    assert "Source(s)" in html
    assert "usa-accordion__button" in html
    assert "usa-accordion__content" in html
