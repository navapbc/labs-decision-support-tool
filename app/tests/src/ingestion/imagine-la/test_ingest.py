import logging

import pytest
from smart_open import open as smart_open
from sqlalchemy import delete, select

from src.db.models.document import Chunk, Document
from src.ingestion.imagine_la.ingest import _ingest_content_hub


@pytest.fixture
def s3_html(mock_s3_bucket_resource):
    doc_1 = smart_open("/app/tests/docs/imagine_la/doc_1.html", "rb")
    mock_s3_bucket_resource.put_object(Body=doc_1, Key="doc_1.html")
    doc_2 = smart_open("/app/tests/docs/imagine_la/doc_2.html", "rb")
    mock_s3_bucket_resource.put_object(Body=doc_2, Key="doc_2.html")
    return "s3://test_bucket/"


@pytest.mark.parametrize("file_location", ["local", "s3"])
def test__ingest_content_hub(caplog, app_config, db_session, s3_html, file_location):
    db_session.execute(delete(Document))

    doc_attribs = {
        "dataset": "test_dataset",
        "program": "test_benefit_program",
        "region": "test_region",
    }

    doc_1_content = """# Document 1

## Accordion 11 Heading

Accordion 11 Body

## Accordion 12 Heading

Accordion 12 Body"""

    doc_2_content = """# Document 2

## Accordion 21 Heading

Accordion 21 Body

## Accordion 22 Heading

Accordion 22 Body"""

    with caplog.at_level(logging.INFO):
        if file_location == "local":
            _ingest_content_hub(
                db_session, "/app/tests/docs/imagine_la/", doc_attribs, should_save_json=False
            )
        else:
            _ingest_content_hub(db_session, s3_html, doc_attribs, should_save_json=False)

        assert any(text.startswith("Processing file: ") for text in caplog.messages)

        documents = db_session.execute(select(Document).order_by(Document.name)).scalars().all()
        assert len(documents) == 2
        assert documents[0].name == "Document 1"
        assert documents[0].source == "https://socialbenefitsnavigator25.web.app/contenthub/doc_1"
        assert documents[0].content == doc_1_content + "\n\n"

        assert documents[1].name == "Document 2"
        assert documents[1].source == "https://socialbenefitsnavigator25.web.app/contenthub/doc_2"
        assert documents[1].content == doc_2_content + "\n\n"

        chunks = db_session.execute(select(Chunk).order_by(Chunk.content)).scalars().all()
        assert len(chunks) == 2
        assert chunks[0].content == doc_1_content
        assert chunks[0].document == documents[0]
        assert chunks[1].content == doc_2_content
        assert chunks[1].document == documents[1]
