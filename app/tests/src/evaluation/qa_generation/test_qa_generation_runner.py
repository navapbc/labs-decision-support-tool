"""Tests for QA generation runner."""

import csv
import json
import uuid
from datetime import datetime
from unittest.mock import patch

import pytest
from litellm import completion

from src.db.models.document import Document
from src.evaluation.data_models import QAPair
from src.evaluation.qa_generation.runner import run_generation, save_qa_pairs
from tests.src.db.models.factories import ChunkFactory, DocumentFactory


@pytest.fixture
def qa_pairs():
    """Create QA pairs for testing."""
    qa_pair1 = QAPair(
        id=uuid.uuid4(),
        question="Question 1?",
        answer="Answer 1",
        document_name="Document 1",
        document_source="Source 1",
        document_id=uuid.uuid4(),
        chunk_id=None,
        content_hash="hash1",
        dataset="Dataset 1",
        llm_model="gpt-4o-mini",
        created_at=datetime.now(),
    )

    qa_pair2 = QAPair(
        id=uuid.uuid4(),
        question="Question 2?",
        answer="Answer 2",
        document_name="Document 2",
        document_source="Source 2",
        document_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        content_hash="hash2",
        dataset="Dataset 2",
        llm_model="gpt-4o-mini",
        created_at=datetime.now(),
    )

    return [qa_pair1, qa_pair2]


@pytest.fixture
def mock_completion_response():
    """Create a mock completion response."""

    def mock_completion(model, messages, **kwargs):
        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "question": "What is this document about?",
                                "answer": "This is a test document.",
                            }
                        )
                    }
                }
            ]
        }
        return completion(model, messages, mock_response=mock_response)

    return mock_completion


def test_save_qa_pairs(qa_pairs, tmp_path):
    """Test save_qa_pairs function with real file operations."""
    # Create a temporary directory for output
    output_dir = tmp_path / "qa_pairs"

    # Call the function with real QA pairs
    result_path = save_qa_pairs(output_dir, qa_pairs)

    # Verify the file was created
    assert result_path.exists()
    assert result_path == output_dir / "qa_pairs.csv"

    # Read the CSV file and verify its contents
    with open(result_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

        # Verify we have the correct number of rows
        assert len(rows) == len(qa_pairs)

        # Verify the content of each row
        for i, row in enumerate(rows):
            assert row["question"] == qa_pairs[i].question
            assert row["answer"] == qa_pairs[i].answer
            assert row["document_name"] == qa_pairs[i].document_name
            assert row["dataset"] == qa_pairs[i].dataset


def test_run_generation_basic(
    mock_completion_response, tmp_path, enable_factory_create, db_session
):
    """Test basic run_generation functionality."""
    output_dir = tmp_path / "qa_output"
    llm_model = "gpt-4o-mini"

    # Create test documents with chunks
    docs = []
    for i in range(2):
        doc = DocumentFactory.create(
            name=f"Test Document {i}",
            content=f"Test content {i}",
            dataset="Dataset 1",
            source=f"Source {i}",
        )
        # Create chunks with content
        for j in range(2):
            ChunkFactory.create(document=doc, content=f"Chunk {j} content for doc{i}")
        docs.append(doc)

    # Mock the completion function at the module where it's imported
    with patch(
        "src.evaluation.qa_generation.generator.completion", side_effect=mock_completion_response
    ):
        # Run the function
        result = run_generation(llm_model=llm_model, output_dir=output_dir)

        # Verify results
        assert result.exists()
        assert "qa_pairs" in str(result)

        # Read generated QA pairs
        with open(result, "r", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            # Should have one QA pair per chunk
            assert len(rows) == 4  # 2 documents * 2 chunks each
            for row in rows:
                assert row["question"] == "What is this document about?"
                assert row["answer"] == "This is a test document."


def test_run_generation_with_dataset_filter(
    mock_completion_response, tmp_path, enable_factory_create, db_session
):
    """Test run_generation with dataset filter."""
    output_dir = tmp_path / "qa_output"
    llm_model = "gpt-4o-mini"
    dataset_filter = ["Dataset 1"]

    # Clean up any existing documents
    db_session.query(Document).delete()
    db_session.commit()

    # Create test documents with different datasets and their chunks
    doc1 = DocumentFactory.create(
        dataset="Dataset 1", source="Source 1", content="Test content for doc1"
    )
    # Create chunks with content
    for i in range(2):
        ChunkFactory.create(document=doc1, content=f"Chunk {i} content for doc1")

    doc2 = DocumentFactory.create(
        dataset="Dataset 2", source="Source 2", content="Test content for doc2"
    )
    # Create chunks with content
    for i in range(2):
        ChunkFactory.create(document=doc2, content=f"Chunk {i} content for doc2")

    # Commit and close the session
    enable_factory_create.commit()

    # Print all documents in DB for debugging
    all_docs = db_session.query(Document).all()
    print("\nAll documents in DB:")
    for doc in all_docs:
        print(f"Document {doc.id}: dataset={doc.dataset}, chunks={len(doc.chunks)}")

    # Mock the completion function at the module where it's imported
    with patch(
        "src.evaluation.qa_generation.generator.completion", side_effect=mock_completion_response
    ):
        # Verify we only see the filtered documents
        filtered_docs = (
            db_session.query(Document).filter(Document.dataset.in_(dataset_filter)).all()
        )
        print("\nFiltered documents:")
        for doc in filtered_docs:
            print(f"Document {doc.id}: dataset={doc.dataset}, chunks={len(doc.chunks)}")
        assert len(filtered_docs) == 1
        assert filtered_docs[0].dataset == "Dataset 1"
        assert len(filtered_docs[0].chunks) == 2

        # Run the generation
        result = run_generation(
            llm_model=llm_model,
            output_dir=output_dir,
            dataset_filter=dataset_filter,
        )

        # Verify results
        assert result.exists()
        assert "qa_pairs" in str(result)

        # Read generated QA pairs
        with open(result, "r", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            # Should only have QA pairs from Dataset 1's document
            assert len(rows) == 2  # 1 document * 2 chunks
            assert all(row["dataset"] == "Dataset 1" for row in rows)


def test_run_generation_no_documents(tmp_path, enable_factory_create, app_config):
    """Test run_generation with no documents found."""
    output_dir = tmp_path / "qa_output"
    llm_model = "gpt-4o-mini"
    dataset_filter = ["NonexistentDataset"]  # Use a dataset filter that won't match any documents

    # Run the function and expect ValueError
    with pytest.raises(ValueError, match="No documents found matching filter criteria"):
        run_generation(llm_model=llm_model, output_dir=output_dir, dataset_filter=dataset_filter)
