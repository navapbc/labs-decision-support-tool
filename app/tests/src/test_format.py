import re

from sqlalchemy import delete

from src.citations import CitationFactory, split_into_subsections
from src.db.models.document import Document
from src.format import (
    FormattingConfig,
<<<<<<< HEAD
=======
    _add_citation_links,
    _add_ellipses_for_bem,
>>>>>>> f57c2e8 (feat: Citation footnotes open accordions (#155))
    _format_guru_to_accordion_html,
    _get_breadcrumb_html,
    build_accordions,
    format_guru_cards,
    reify_citations,
)
from src.retrieve import retrieve_with_scores
from tests.src.db.models.factories import ChunkFactory
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


def test_format_guru_cards_with_score(monkeypatch, app_config, db_session, enable_factory_create):
    db_session.execute(delete(Document))

    chunks_with_scores = _get_chunks_with_scores()
    subsections = to_subsections(chunks_with_scores)

    html = format_guru_cards(
        chunks_shown_max_num=2,
        chunks_shown_min_score=0.0,
        chunks_with_scores=chunks_with_scores,
        subsections=subsections,
        raw_response="",
    )
    assert len(_unique_accordion_ids(html)) == len(chunks_with_scores)
    assert "Related Guru cards" in html
    assert chunks_with_scores[0].chunk.document.name in html
    assert chunks_with_scores[0].chunk.document.content in html
    assert chunks_with_scores[1].chunk.document.name in html
    assert chunks_with_scores[1].chunk.document.content in html
    assert "Similarity Score" in html

    # Check that a second call doesn't re-use the IDs
    next_html = format_guru_cards(
        chunks_shown_max_num=2,
        chunks_shown_min_score=0.0,
        chunks_with_scores=chunks_with_scores,
        subsections=subsections,
        raw_response="",
    )
    assert len(_unique_accordion_ids(html + next_html)) == 2 * len(chunks_with_scores)


def test_format_guru_cards_given_chunks_shown_max_num(chunks_with_scores):
    html = format_guru_cards(
        chunks_shown_max_num=2,
        chunks_shown_min_score=0.8,
        chunks_with_scores=chunks_with_scores,
        subsections=to_subsections(chunks_with_scores),
        raw_response="",
    )
    assert len(_unique_accordion_ids(html)) == 2


def test_format_guru_cards_given_chunks_shown_max_num_and_min_score(chunks_with_scores):
    html = format_guru_cards(
        chunks_shown_max_num=2,
        chunks_shown_min_score=0.91,
        chunks_with_scores=chunks_with_scores,
        subsections=to_subsections(chunks_with_scores),
        raw_response="",
    )
    assert len(_unique_accordion_ids(html)) == 1


def test__format_guru_to_accordion_html(app_config, db_session, enable_factory_create):
    db_session.execute(delete(Document))
    chunks_with_scores = _get_chunks_with_scores()
    document = chunks_with_scores[0].chunk.document
    score = 0.92
    html = _format_guru_to_accordion_html(document=document, score=score)
    assert document.name in html
    assert document.content in html
    assert "<p>Similarity Score: 0.92</p>" in html


def test_build_accordions(chunks_with_scores):
    subsections = to_subsections(chunks_with_scores)

    config = FormattingConfig()
    assert build_accordions(subsections, "", config) == "<div></div>"
    assert (
        build_accordions([], "Non-existant citation: (citation-0)", config)
        == "<div><p>Non-existant citation: </p></div>"
    )

    assert (
        build_accordions([], "List intro sentence: \n- item 1\n- item 2", config)
        == "<div><p>List intro sentence: </p>\n<ul>\n<li>item 1</li>\n<li>item 2</li>\n</ul></div>"
    )

    html = build_accordions(subsections, "Some real citations: (citation-1) (citation-2)", config)
    assert len(_unique_accordion_ids(html)) == 2


def test_reify_citations():
    chunks = ChunkFactory.build_batch(2)
    chunks[0].content = "This is the first chunk.\n\nWith two subsections"
    subsections = split_into_subsections(chunks, factory=CitationFactory())
    config = FormattingConfig()

    assert (
        reify_citations("This is a citation (citation-0)", [], config, None)
        == "This is a citation "
    )

    assert (
        reify_citations(
            f"This is a citation ({subsections[0].id}) and another ({subsections[1].id}).",
            subsections,
            config,
            None,
        )
        == "This is a citation <sup><a class='accordion_item' data-id='a-None' style='cursor:pointer'>1</a>&nbsp;</sup> and another <sup><a class='accordion_item' data-id='a-None' style='cursor:pointer'>2</a>&nbsp;</sup>."
    )


def test_add_citation_links():
    chunks = ChunkFactory.build_batch(3)

    remapped_citations = {
        "citation-1": Subsection(chunk=chunks[0], text=chunks[0].content, id="1"),
        "citation-44": Subsection(chunk=chunks[1], text=chunks[1].content, id="3"),
        "citation-3": Subsection(chunk=chunks[2], text=chunks[2].content, id="23"),
    }

    config = FormattingConfig()

    assert (
        _add_citation_links(
            "This is a citation (citation-1). This is another value citation (citation-44). And another not found(citation-5).",
            remapped_citations,
            config,
            {
                "1": "599299",
                "2": "599300",
                "3": "599300",
                "4": "599301",
                "5": "599302",
                "44": "599303",
            },
        )
        == "This is a citation <sup><a class='accordion_item' data-id='a-599299' style='cursor:pointer'>1</a>&nbsp;</sup>. This is another value citation <sup><a class='accordion_item' data-id='a-599300' style='cursor:pointer'>3</a>&nbsp;</sup>. And another not found."
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
