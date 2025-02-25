"""Tests for JSONL to CSV conversion utility."""

import json
import os

import pytest

from src.evaluation.metrics.utils.jsonl_to_csv import (
    convert_batch_results_to_csv,
    convert_results_to_csv,
    explode_result_to_rows,
    flatten_dict,
)


def test_flatten_dict():
    """Test dictionary flattening."""
    # Test simple dictionary
    simple_dict = {"a": 1, "b": 2}
    assert flatten_dict(simple_dict) == simple_dict

    # Test nested dictionary
    nested_dict = {
        "a": {"b": 1, "c": 2},
        "d": 3,
    }
    expected = {
        "a_b": 1,
        "a_c": 2,
        "d": 3,
    }
    assert flatten_dict(nested_dict) == expected

    # Test deeply nested dictionary
    deep_dict = {
        "a": {
            "b": {"c": 1},
            "d": 2,
        },
        "e": 3,
    }
    expected = {
        "a_b_c": 1,
        "a_d": 2,
        "e": 3,
    }
    assert flatten_dict(deep_dict) == expected

    # Test with custom separator
    assert flatten_dict(nested_dict, sep=".") == {
        "a.b": 1,
        "a.c": 2,
        "d": 3,
    }


def test_explode_result_to_rows():
    """Test result explosion into multiple rows."""
    # Test result with no chunks/scores
    empty_result = {
        "qa_pair_id": "qa123",
        "question": "test?",
        "evaluation_result": {},
        "expected_chunk": {"content_hash": "empty_hash"},
    }
    rows = list(explode_result_to_rows(empty_result))
    assert len(rows) == 1
    assert rows[0]["qa_pair_id"] == "qa123"
    assert rows[0]["expected_content_hash"] == "empty_hash"

    # Test result with chunks and scores
    result = {
        "qa_pair_id": "qa123",
        "question": "test?",
        "expected_chunk_id": "chunk1",
        "expected_chunk": {
            "name": "test_doc",
            "source": "test_dataset",
            "chunk_id": "chunk1",
            "content_hash": "hash1",
        },
        "evaluation_result": {"correct_chunk_retrieved": True, "rank_if_found": 1},
        "retrieved_chunks": [
            {
                "chunk_id": "chunk1",
                "document_id": "doc1",
                "document_name": "test_doc",
                "content": "content1",
                "content_hash": "hash1",
                "score": 0.9,
            },
            {
                "chunk_id": "chunk2",
                "document_id": "doc2",
                "document_name": "test_doc",
                "content": "content2",
                "content_hash": "hash2",
                "score": 0.8,
            },
        ],
    }

    rows = list(explode_result_to_rows(result))
    assert len(rows) == 2

    # Check first row
    assert rows[0]["qa_pair_id"] == "qa123"
    assert rows[0]["rank"] == 1
    assert rows[0]["similarity_score"] == 0.9
    assert rows[0]["retrieved_chunk_id"] == "chunk1"
    assert rows[0]["retrieved_content_hash"] == "hash1"
    assert rows[0]["expected_content_hash"] == "hash1"
    assert rows[0]["is_correct_chunk"] is True
    assert rows[0]["evaluation_result_correct_chunk_retrieved"] is True
    assert rows[0]["evaluation_result_rank_if_found"] == 1

    # Check second row
    assert rows[1]["qa_pair_id"] == "qa123"
    assert rows[1]["rank"] == 2
    assert rows[1]["similarity_score"] == 0.8
    assert rows[1]["retrieved_chunk_id"] == "chunk2"
    assert rows[1]["retrieved_content_hash"] == "hash2"
    assert rows[1]["expected_content_hash"] == "hash1"
    assert rows[1]["is_correct_chunk"] is False
    assert rows[1]["evaluation_result_correct_chunk_retrieved"] is True
    assert rows[1]["evaluation_result_rank_if_found"] == 1


@pytest.fixture
def temp_jsonl_file(tmp_path):
    """Create a temporary JSONL file with test data."""
    file_path = tmp_path / "test_results.jsonl"
    results = [
        {
            "qa_pair_id": "qa123",
            "question": "test?",
            "expected_chunk_id": "chunk1",
            "evaluation_result": {
                "retrieved_chunks": [
                    {
                        "chunk_id": "chunk1",
                        "document_id": "doc1",
                        "document_name": "test_doc",
                        "content": "content1",
                        "content_hash": "hash1",
                        "score": 0.9,
                    }
                ],
            },
        }
    ]
    with open(file_path, "w") as f:
        for result in results:
            f.write(json.dumps(result) + "\n")
    return str(file_path)


def test_convert_results_to_csv(temp_jsonl_file, tmp_path):
    """Test conversion of JSONL results to CSV."""
    # Test with default output path
    csv_path = convert_results_to_csv(temp_jsonl_file)
    assert csv_path == str(tmp_path / "test_results.csv")
    assert os.path.exists(csv_path)

    # Test with custom output path
    custom_path = str(tmp_path / "custom.csv")
    csv_path = convert_results_to_csv(temp_jsonl_file, custom_path)
    assert csv_path == custom_path
    assert os.path.exists(custom_path)

    # Check CSV contents
    with open(csv_path) as f:
        header = f.readline().strip().split(",")
        data = f.readline().strip().split(",")

        # Check that priority fields come first
        priority_fields = [
            "qa_pair_id",
            "question",
            "expected_chunk_id",
            "rank",
            "similarity_score",
            "is_correct_chunk",
        ]
        for i, field in enumerate(priority_fields):
            if field in header:
                assert header[i] == field

        # Check data values
        assert "qa123" in data
        assert "test?" in data
        assert "chunk1" in data


@pytest.fixture
def temp_batch_dir(tmp_path):
    """Create a temporary batch directory with test JSONL files."""
    batch_dir = tmp_path / "batch"
    batch_dir.mkdir()

    # Create multiple JSONL files
    for i in range(2):
        file_path = batch_dir / f"results_batch{i}.jsonl"
        with open(file_path, "w") as f:
            result = {
                "qa_pair_id": f"qa{i}",
                "question": "test?",
                "expected_chunk": {
                    "name": "test_doc",
                    "source": "test_dataset",
                    "chunk_id": "chunk1",
                    "content_hash": f"hash{i}",
                },
                "evaluation_result": {
                    "retrieved_chunks": [
                        {
                            "chunk_id": "chunk1",
                            "content": "test content",
                            "content_hash": f"hash{i}",
                            "score": 0.9,
                        }
                    ],
                },
            }
            f.write(json.dumps(result) + "\n")

    return str(batch_dir)


def test_convert_batch_results_to_csv(temp_batch_dir):
    """Test conversion of multiple batch result files."""
    csv_files = convert_batch_results_to_csv(temp_batch_dir)
    assert len(csv_files) == 2

    for csv_file in csv_files:
        assert os.path.exists(csv_file)
        assert csv_file.endswith(".csv")

        # Check that each CSV file has content
        with open(csv_file) as f:
            assert len(f.readlines()) > 1  # Header + at least one data row
