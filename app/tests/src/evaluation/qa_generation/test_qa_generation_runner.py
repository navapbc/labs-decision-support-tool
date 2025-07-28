"""Tests for QA generation runner."""

import csv
import json
import uuid
from dataclasses import fields
from datetime import datetime
from unittest.mock import patch

import pytest
from litellm import completion

from src.db.models.document import Document
from src.evaluation.data_models import QAPair, QAPairVersion
from src.evaluation.qa_generation.runner import run_generation
from src.evaluation.utils.storage import QAPairStorage
from tests.src.db.models.factories import ChunkFactory, DocumentFactory


@pytest.fixture
def mock_completion_response():
    """Create a mock completion response using litellm.completion."""

    def mock_completion(model, messages, **kwargs):
        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "question": "What is the test content?",
                                "answer": "The test content is for QA generation.",
                            }
                        )
                    }
                }
            ]
        }
        return completion(model, messages, mock_response=mock_response)

    return mock_completion


@pytest.fixture
def qa_pairs():
    """Create QA pairs for testing."""
    version = QAPairVersion(
        version_id="test_v1",
        llm_model="test-model",
        timestamp=datetime.utcnow(),
    )

    qa_pair1 = QAPair(
        question="Question 1?",
        answer="Answer 1",
        document_name="Document 1",
        document_source="Source 1",
        document_id=uuid.uuid4(),
        chunk_id=None,
        content_hash="hash1",
        dataset="Dataset 1",
        version=version,
        expected_chunk_content="Test content 1",
    )

    qa_pair2 = QAPair(
        question="Question 2?",
        answer="Answer 2",
        document_name="Document 2",
        document_source="Source 2",
        document_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        content_hash="hash2",
        dataset="Dataset 2",
        version=version,
        expected_chunk_content="Test content 2",
    )

    return [qa_pair1, qa_pair2]


def test_qa_storage(qa_pairs, tmp_path):
    """Test QA pairs storage functionality."""
    # Create a storage instance with a temporary directory
    storage = QAPairStorage(tmp_path / "qa_pairs")
    version_id = "test_v1"

    # Save QA pairs
    qa_pairs_path = storage.save_qa_pairs(qa_pairs, version_id)

    # Verify the file was created
    assert qa_pairs_path.exists()
    assert qa_pairs_path.name == "qa_pairs.csv"

    # Read the CSV file and verify its contents
    with open(qa_pairs_path, "r", newline="") as f:
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
            assert row["expected_chunk_content"] == qa_pairs[i].expected_chunk_content


def test_run_generation_basic(
    mock_completion_response, tmp_path, enable_factory_create, db_session, app_config
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
        qa_pairs = run_generation(llm_model=llm_model, output_dir=output_dir)

        # Verify results
        assert len(qa_pairs) == 4  # 2 documents * 2 chunks each
        for pair in qa_pairs:
            assert isinstance(pair, QAPair)
            assert pair.question == "What is the test content?"
            assert pair.answer == "The test content is for QA generation."
            assert pair.version.llm_model == llm_model


def test_run_generation_with_dataset_filter(
    mock_completion_response, tmp_path, enable_factory_create, db_session, app_config
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
        qa_pairs = run_generation(
            llm_model=llm_model,
            output_dir=output_dir,
            dataset_filter=dataset_filter,
        )

        # Verify results
        assert len(qa_pairs) == 2  # 1 document * 2 chunks
        for pair in qa_pairs:
            assert isinstance(pair, QAPair)
            assert pair.dataset == "Dataset 1"
            assert pair.version.llm_model == llm_model


def test_run_generation_no_documents(tmp_path, enable_factory_create, app_config):
    """Test run_generation with no documents found."""
    output_dir = tmp_path / "qa_output"
    llm_model = "gpt-4o-mini"
    dataset_filter = ["NonexistentDataset"]  # Use a dataset filter that won't match any documents

    # Run the function and expect ValueError
    with pytest.raises(ValueError, match="No documents found matching filter criteria"):
        run_generation(llm_model=llm_model, output_dir=output_dir, dataset_filter=dataset_filter)


def test_save_qa_pairs(qa_pairs, tmp_path):
    """Test basic save_qa_pairs functionality with directory creation."""
    from src.evaluation.qa_generation.runner import save_qa_pairs

    # Use a nested directory that doesn't exist yet
    output_dir = tmp_path / "new_dir" / "nested_dir"

    # Save QA pairs
    csv_path = save_qa_pairs(output_dir, qa_pairs)

    # Verify directory was created
    assert output_dir.exists()
    assert output_dir.is_dir()

    # Verify file exists and has correct content
    assert csv_path.exists()
    assert csv_path.name == "qa_pairs.csv"

    # Read and verify CSV content
    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

        # Check headers are present
        expected_headers = [field.name for field in fields(QAPair)]
        assert reader.fieldnames == expected_headers

        # Verify we have the correct number of rows
        assert len(rows) == len(qa_pairs)

        # Verify content matches
        for i, row in enumerate(rows):
            assert row["question"] == qa_pairs[i].question
            assert row["answer"] == qa_pairs[i].answer
            assert row["document_name"] == qa_pairs[i].document_name


def test_run_generation_with_version(
    mock_completion_response, tmp_path, enable_factory_create, db_session, app_config
):
    """Test run_generation with version parameter."""
    output_dir = tmp_path / "qa_output"
    llm_model = "gpt-4o-mini"

    # Create a test document with chunks
    doc = DocumentFactory.create(
        name="Test Document",
        content="Test content",
        dataset="Dataset 1",
        source="Source 1",
    )
    ChunkFactory.create(document=doc, content="Chunk content")

    # Create a specific version
    version = QAPairVersion(
        version_id="test_version_1",
        llm_model=llm_model,
        timestamp=datetime.utcnow(),
    )

    # Run generation with version
    with patch(
        "src.evaluation.qa_generation.generator.completion",
        side_effect=mock_completion_response,
    ):
        qa_pairs = run_generation(
            llm_model=llm_model,
            output_dir=output_dir,
            version=version,
        )

        # Verify version information is preserved
        assert len(qa_pairs) > 0
        for pair in qa_pairs:
            assert pair.version.version_id == version.version_id
            assert pair.version.llm_model == version.llm_model


def test_run_generation_invalid_sample_fraction(
    tmp_path, enable_factory_create, db_session, app_config
):
    """Test run_generation with invalid sample fraction values."""
    output_dir = tmp_path / "qa_output"
    llm_model = "gpt-4o-mini"

    # Create a test document
    DocumentFactory.create(
        name="Test Document",
        content="Test content",
        dataset="Dataset 1",
    )

    # Test negative sample fraction
    with pytest.raises(ValueError, match="Sample fraction must be between 0 and 1"):
        run_generation(
            llm_model=llm_model,
            output_dir=output_dir,
            sample_fraction=-0.5,
        )

    # Test sample fraction > 1
    with pytest.raises(ValueError, match="Sample fraction must be between 0 and 1"):
        run_generation(
            llm_model=llm_model,
            output_dir=output_dir,
            sample_fraction=1.5,
        )
