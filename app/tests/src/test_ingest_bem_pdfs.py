import logging
from io import BytesIO
from pathlib import Path

import pytest
from smart_open import open as smart_open
from sqlalchemy import delete, select
from unstructured.documents.elements import ElementMetadata, Text

from src.app_config import app_config as global_app_config
from src.db.models.document import Chunk, Document
from src.ingest_bem_pdfs import (
    _extract_page_sections,
    _get_bem_title,
    _ingest_bem_pdfs,
    _match_heading,
    _next_heading,
)
from src.util.ingest_utils import IngestConfig
from src.util.pdf_utils import Heading

_707_PDF_PATH = Path(__file__).resolve().parent / "util" / "707.pdf"


@pytest.fixture
def bem_ingest_config():
    return IngestConfig(
        "bridges-eligibility-manual",
        "mixed",
        "Michigan",
        "http://127.0.0.1:8080",
        "bridges-eligibility-manual",
    )


def _chunk_matching(chunks: list[Chunk], content: str) -> Chunk:
    return next(chunk for chunk in chunks if content in chunk.content)


def test__get_bem_title():
    with smart_open(str(_707_PDF_PATH), "rb") as file:
        assert _get_bem_title(file, str(_707_PDF_PATH)) == "BEM 707 — Time And Attendance Reviews"


def test__extract_page_sections():
    pdf_bytes = BytesIO()
    with smart_open(str(_707_PDF_PATH), "rb") as file:
        pdf_bytes.write(file.read())

    sections = _extract_page_sections(pdf_bytes.getvalue())
    assert sections[1].bem_number == "707"
    assert sections[1].title == "TIME AND ATTENDANCE REVIEWS"
    assert sections[2].bem_number == "707"


def test__ingest_bem_pdfs(caplog, app_config, db_session, bem_ingest_config, monkeypatch, tmp_path):
    monkeypatch.setattr("src.ingest_bem_pdfs._public_sources_dir", lambda: tmp_path)
    monkeypatch.setattr(global_app_config, "public_source_base_url", "http://127.0.0.1:8080")
    db_session.execute(delete(Document))

    with caplog.at_level(logging.INFO):
        _ingest_bem_pdfs(db_session, str(_707_PDF_PATH), bem_ingest_config)
        assert any("Processing BEM PDF:" in message for message in caplog.messages)

    document = db_session.execute(select(Document)).scalar_one()
    assert document.dataset == "bridges-eligibility-manual"
    assert document.program == "mixed"
    assert document.region == "Michigan"
    assert document.name == "BEM 707 — Time And Attendance Reviews"
    assert document.source == "http://127.0.0.1:8080/sources/bem-mobile.pdf"
    assert "In order to be eligible to bill and receive payments" in document.content

    first_chunk = _chunk_matching(
        document.chunks, "In order to be eligible to bill and receive payments"
    )
    assert first_chunk.headings == ["Overview"]
    assert first_chunk.page_number == 1

    second_chunk = _chunk_matching(
        document.chunks, "Failure to maintain time and attendance records."
    )
    assert second_chunk.headings == ["Rule Violations"]
    assert second_chunk.page_number == 1

    later_chunk = _chunk_matching(
        document.chunks, "The following are examples of IPVs:"
    )
    assert later_chunk.headings == [
        "Time and Attendance Review  Process",
        "Intentional Program Violations",
    ]
    assert later_chunk.page_number == 2

    assert (tmp_path / "bem-mobile.pdf").exists()


@pytest.fixture
def mock_outline():
    return [
        Heading(title="Overview", level=1, pageno=1),
        Heading(title="Family Independence Program (FIP)", level=2, pageno=1),
        Heading(title="Program Goal", level=2, pageno=1),
        Heading(title="Tertiary Program Goal", level=3, pageno=2),
        Heading(title="Test Level 2", level=2, pageno=2),
    ]


@pytest.fixture
def mock_elements():
    return [
        Text(text="OVERVIEW", metadata=ElementMetadata(page_number=1)),
        Text(text="Family Independence Program (FIP)", metadata=ElementMetadata(page_number=1)),
        Text(text="Program Goal", metadata=ElementMetadata(page_number=1)),
        Text(text="Tertiary Program Goal", metadata=ElementMetadata(page_number=2)),
        Text(text="Test Level 1", metadata=ElementMetadata(page_number=2)),
    ]


def test__match_heading(mock_outline):
    heading = _match_heading(mock_outline, "Family Independence  Program (FIP)", 1)
    assert heading is not None
    assert _match_heading(mock_outline, "Family Independence  Program (FIP)", 5) is None


def test__next_heading(mock_outline, mock_elements):
    second_level_heading = _next_heading(mock_outline, mock_elements[1], mock_outline[:2])
    assert second_level_heading == [
        Heading(title="Overview", level=1, pageno=1),
        Heading(title="Family Independence Program (FIP)", level=2, pageno=1),
    ]

    replaced_second_level = _next_heading(mock_outline, mock_elements[2], mock_outline[:2])
    assert replaced_second_level == [
        Heading(title="Overview", level=1, pageno=1),
        Heading(title="Program Goal", level=2, pageno=1),
    ]
