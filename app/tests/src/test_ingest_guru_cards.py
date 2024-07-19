import json
import logging

import pytest
from sqlalchemy import delete, select

from src.db.models.document import Document
from src.ingest_guru_cards import _ingest_cards
from tests.mock.mock_sentence_transformer import MockSentenceTransformer


@pytest.fixture
def sample_cards():
    return json.dumps(
        [
            {
                "preferredPhrase": "Test Card 1",
                "content": "<p>This is a test content for card 1.</p>",
            },
            {
                "preferredPhrase": "Test Card 2",
                "content": "<div>This is a test content for card 2.</div><div>With extra HTML.</div>",
            },
            {"preferredPhrase": "Long Card", "content": "<p>" + "word " * 600 + "</p>"},
        ]
    )


@pytest.fixture
def guru_local_file(tmp_path, sample_cards):
    file_path = tmp_path / "guru_cards.json"
    file_path.write_text(sample_cards)
    return str(file_path)


@pytest.fixture
def guru_s3_file(mock_s3_bucket_resource, sample_cards):
    mock_s3_bucket_resource.put_object(Body=sample_cards, Key="guru_cards.json")
    return "s3://test_bucket/guru_cards.json"


doc_attribs = {
    "dataset": "test_dataset",
    "program": "test_benefit_program",
    "region": "Michigan",
}


@pytest.mark.parametrize("file_location", ["local", "s3"])
def test__ingest_cards(db_session, guru_local_file, guru_s3_file, file_location):
    db_session.execute(delete(Document))
    mock_embedding = MockSentenceTransformer()

    if file_location == "local":
        _ingest_cards(db_session, mock_embedding, guru_local_file, doc_attribs)
    else:
        _ingest_cards(db_session, mock_embedding, guru_s3_file, doc_attribs)

    documents = db_session.execute(select(Document).order_by(Document.name)).scalars().all()
    assert len(documents) == 3
    assert set(d.dataset for d in documents) == {"test_dataset"}
    assert set(d.program for d in documents) == {"test_benefit_program"}
    assert set(d.region for d in documents) == {"Michigan"}

    assert documents[0].name == "Long Card"
    assert documents[0].content == "word " * 600
    assert len(documents[0].chunks) == 1
    assert documents[0].chunks[0].tokens == 600
    assert documents[0].chunks[0].content == "word " * 600

    assert documents[1].name == "Test Card 1"
    assert documents[1].content == "This is a test content for card 1."
    assert len(documents[1].chunks) == 1
    assert documents[1].chunks[0].tokens == 8
    assert documents[1].chunks[0].content == "This is a test content for card 1."

    assert documents[2].name == "Test Card 2"
    assert documents[2].content == "This is a test content for card 2.\nWith extra HTML."
    assert len(documents[2].chunks) == 1
    assert documents[2].chunks[0].tokens == 11
    assert documents[2].chunks[0].content == "This is a test content for card 2.\nWith extra HTML."


def test__ingest_cards_warns_on_max_seq_length(caplog, db_session, guru_local_file):
    mock_embedding = MockSentenceTransformer()

    with caplog.at_level(logging.WARNING):
        _ingest_cards(db_session, mock_embedding, guru_local_file, doc_attribs)
        assert "exceeds the embedding model's max sequence length" in caplog.messages[0]
