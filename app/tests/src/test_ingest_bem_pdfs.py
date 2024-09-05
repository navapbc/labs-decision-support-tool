import json
import logging
import os
import tempfile

import pytest
from smart_open import open as smart_open
from sqlalchemy import delete, select
from unstructured.documents.elements import ElementMetadata, Text

from src.db.models.document import Document
from src.ingest_bem_pdfs import (
    _add_embeddings,
    _enrich_texts,
    _get_bem_title,
    _ingest_bem_pdfs,
    _match_heading,
    _next_heading,
    _save_json,
)
from src.ingestion.pdf_elements import EnrichedText
from src.util.pdf_utils import Heading
from tests.mock.mock_sentence_transformer import MockSentenceTransformer
from tests.src.db.models.factories import ChunkFactory
from tests.src.test_ingest_policy_pdfs import doc_attribs

_707_PDF_PATH = "/app/tests/src/util/707.pdf"


@pytest.fixture
def policy_s3_file(mock_s3_bucket_resource):
    data = smart_open(_707_PDF_PATH, "rb")
    mock_s3_bucket_resource.put_object(Body=data, Key="707.pdf")
    return "s3://test_bucket/"


@pytest.mark.parametrize("file_location", ["local", "s3"])
def test__get_bem_title(file_location, policy_s3_file):
    file_path = policy_s3_file + "707.pdf" if file_location == "s3" else _707_PDF_PATH
    with smart_open(file_path, "rb") as file:
        assert _get_bem_title(file, file_path) == "BEM 707: TIME AND ATTENDANCE REVIEWS"


@pytest.fixture
def mock_outline():
    return [
        Heading(title="Overview", level=1, pageno=1),
        Heading(title="Family Independence Program (FIP)", level=2, pageno=1),
        Heading(title="Program Goal", level=2, pageno=1),
        Heading(title="Medical Assistance Program", level=2, pageno=2),
        Heading(title="Program Goal", level=2, pageno=2),
        Heading(title="Tertiary Program Goal", level=3, pageno=2),
        Heading(title="4th Program Goal", level=4, pageno=2),
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


@pytest.mark.parametrize("file_location", ["local", "s3"])
def test__ingest_bem_pdfs(caplog, app_config, db_session, policy_s3_file, file_location):
    db_session.execute(delete(Document))

    with caplog.at_level(logging.INFO):
        if file_location == "local":
            _ingest_bem_pdfs(db_session, "/app/tests/src/util/", doc_attribs, save_json=False)
        else:
            _ingest_bem_pdfs(db_session, policy_s3_file, doc_attribs, save_json=False)

        assert any(text.startswith("Processing file: ") for text in caplog.messages)
        document = db_session.execute(select(Document)).one()[0]
        assert document.dataset == "test_dataset"
        assert document.program == "test_benefit_program"
        assert document.region == "Michigan"

        assert document.name == "BEM 707: TIME AND ATTENDANCE REVIEWS"

        assert "In order to be eligible to bill and receive payments, child " in document.content

        first_chunk = document.chunks[0]
        assert first_chunk.content.startswith(
            "In order to be eligible to bill and receive payments, child"
        )
        assert first_chunk.headings == ["Overview"]
        assert first_chunk.page_number == 1

        second_chunk = document.chunks[1]
        assert second_chunk.content.startswith(
            "Rule violations include, but are not limited to:\n- "
        )
        assert second_chunk.headings == ["Rule Violations"]
        assert second_chunk.page_number == 1

        third_chunk = document.chunks[2]
        assert third_chunk.content.startswith("Failure to maintain time and attendance records.")
        assert third_chunk.headings == ["Rule Violations"]
        assert third_chunk.page_number == 1

        list_type_chunk = document.chunks[10]
        assert list_type_chunk.content == (
            "The following are examples of IPVs:\n"
            "- Billing for children while they are in school.\n"
            "- Two instances of failing to respond to requests for records.\n"
            "- Two instances of providing care in the wrong location.\n"
            "- Billing for children no longer in care.\n"
            "- Knowingly billing for children not in care or more hours than children were in care.\n"
            "- Maintaining records that do not accurately reflect the time children were in care."
        )
        assert list_type_chunk.headings == [
            "Time and Attendance Review  Process",
            "Intentional Program Violations",
        ]
        assert list_type_chunk.page_number == 2

        bold_styled_chunk = document.chunks[12]
        expected_text = (
            "Providers determined to have committed an IPV may serve the following penalties:\n"
            "- First occurrence - six month disqualification. The closure reason will be **CDC not eligible due to 6 month penalty period**.\n"
            "- Second occurrence - twelve month disqualification. The closure reason will be **CDC not eligible due to 12 month penalty period.**\n"
            "- Third occurrence - lifetime disqualification. The closure reason will be **CDC not eligible due to lifetime penalty.**"
        )
        assert bold_styled_chunk.content == expected_text

        title_chunk = document.chunks[22]
        assert title_chunk.content.startswith("**CDC**\n\nThe Child Care and Development Block")
        assert title_chunk.headings == ["legal base"]
        assert title_chunk.page_number == 4


def test__enrich_text():
    with smart_open(_707_PDF_PATH, "rb") as file:
        enriched_text_list = _enrich_texts(file)

        assert len(enriched_text_list) == 40
        first_enriched_text_item = enriched_text_list[0]
        assert isinstance(first_enriched_text_item, EnrichedText)
        assert first_enriched_text_item.headings == [Heading(title="Overview", level=1, pageno=1)]
        assert first_enriched_text_item.type == "NarrativeText"
        assert first_enriched_text_item.page_number == 1

        other_enriched_text_item = enriched_text_list[13]
        assert other_enriched_text_item.headings == [
            Heading(title="Time and Attendance Review  Process", level=1, pageno=1),
            Heading(title="Provider Errors", level=2, pageno=1),
        ]
        assert other_enriched_text_item.type == "ListItem"
        assert other_enriched_text_item.page_number == 2


def test__match_heading(mock_outline):
    heading_with_extra_space = _match_heading(mock_outline, "Family Independence  Program (FIP)", 1)
    assert heading_with_extra_space

    heading_on_wrong_page = _match_heading(mock_outline, "Family Independence  Program (FIP)", 5)
    assert heading_on_wrong_page is None


def test__next_heading(mock_outline, mock_elements):
    second_level_heading = _next_heading(
        mock_outline,
        mock_elements[1],
        mock_outline[:2],
    )
    assert second_level_heading == [
        Heading(title="Overview", level=1, pageno=1),
        Heading(title="Family Independence Program (FIP)", level=2, pageno=1),
    ]

    replaced_second_level = _next_heading(mock_outline, mock_elements[2], mock_outline[:2])
    assert replaced_second_level == [
        Heading(title="Overview", level=1, pageno=1),
        Heading(title="Program Goal", level=2, pageno=1),
    ]

    current_headings = [
        Heading(title="Overview", level=1, pageno=1),
        Heading(title="Program Goal", level=2, pageno=1),
        Heading(title="Tertiary Program Goal", level=3, pageno=2),
        Heading(title="4th Program Goal", level=4, pageno=2),
    ]
    element = Text(text="Test Level 2", metadata=ElementMetadata(page_number=2))
    dropped_level = _next_heading(mock_outline, element, current_headings)
    assert dropped_level == [
        Heading(title="Overview", level=1, pageno=1),
        Heading(title="Test Level 2", level=2, pageno=2),
    ]


def test__add_embeddings(app_config):
    embedding_model = MockSentenceTransformer()
    chunks = ChunkFactory.build_batch(3, tokens=None, mpnet_embedding=None)
    _add_embeddings(chunks)
    for chunk in chunks:
        assert chunk.tokens == len(embedding_model.tokenizer.tokenize(chunk.content))
        assert chunk.mpnet_embedding == embedding_model.encode(chunk.content)


@pytest.mark.parametrize("file_location", ["local", "s3"])
def test__save_json(file_location, mock_s3_bucket_resource):
    chunks = ChunkFactory.build_batch(2)
    file_path = (
        "s3://test_bucket/test.pdf"
        if file_location == "s3"
        else os.path.join(tempfile.mkdtemp(), "test.pdf")
    )
    _save_json(file_path, chunks)
    saved_json = json.loads(smart_open(file_path + ".json", "r").read())
    assert saved_json == [
        {
            "id": str(chunks[0].id),
            "content": chunks[0].content,
            "document_id": str(chunks[0].document_id),
            "headings": chunks[0].headings if chunks[0].headings else [],
            "num_splits": chunks[0].num_splits,
            "split_index": chunks[0].split_index,
        },
        {
            "id": str(chunks[1].id),
            "content": chunks[1].content,
            "document_id": str(chunks[1].document_id),
            "headings": chunks[1].headings if chunks[1].headings else [],
            "num_splits": chunks[1].num_splits,
            "split_index": chunks[1].split_index,
        },
    ]
