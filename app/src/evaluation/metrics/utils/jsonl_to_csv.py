"""Utility functions for converting JSONL results to CSV format."""

import csv
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set


def flatten_dict(d: Dict[str, Any], parent_key: str = "", sep: str = "_") -> Dict[str, Any]:
    """Flatten a nested dictionary into a single level dictionary."""
    items: List[tuple] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def explode_result_to_rows(result: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    """Explode a single result into multiple rows based on retrieved chunks and scores.

    This creates a row for each retrieved chunk, making it easier to analyze the
    1:1 relationship between ground truth and retrieved chunks.

    Args:
        result: A single result dictionary containing retrieved_chunks (list[dict])

    Yields:
        Dict containing flattened result with one row per retrieved chunk/score pair
    """
    # Get the base result without the arrays we'll explode
    base_result = result.copy()
    retrieved_chunks = base_result.pop("retrieved_chunks", [])

    # Add evaluation result fields
    eval_result = base_result.pop("evaluation_result", {})
    base_result.update(flatten_dict({"evaluation_result": eval_result}))

    # Get expected content hash and add to base result
    expected_chunk = base_result.pop("expected_chunk", {})
    expected_content_hash = expected_chunk.get("content_hash", "")
    base_result["expected_content_hash"] = expected_content_hash
    base_result.update(flatten_dict({"expected_chunk": expected_chunk}))

    # If no chunks, yield single flattened row
    if not retrieved_chunks:
        yield base_result
        return

    # Create a row for each chunk
    for idx, chunk in enumerate(retrieved_chunks, start=1):
        row = base_result.copy()
        row.update(
            {
                "rank": idx,
                "similarity_score": float(chunk["score"]),
                "retrieved_chunk_id": chunk["chunk_id"],
                "retrieved_content": chunk["content"],
                "retrieved_content_hash": chunk["content_hash"],
                # Match on content hash like we do in evaluation
                "is_correct_chunk": chunk["content_hash"] == expected_content_hash,
            }
        )
        yield row


def convert_results_to_csv(jsonl_path: str, csv_path: Optional[str] = None) -> str:
    """Convert a results JSONL file to CSV format.

    Args:
        jsonl_path: Path to the input JSONL file
        csv_path: Optional path for output CSV file. If not provided,
                 will use same name/location as JSONL but with .csv extension

    Returns:
        Path to the created CSV file
    """
    if not csv_path:
        csv_path = str(Path(jsonl_path).with_suffix(".csv"))

    # Read all results and get unique fields
    all_rows = []
    fieldnames: Set[str] = set()

    with open(jsonl_path, "r") as f:
        for line in f:
            result = json.loads(line)
            # Explode each result into multiple rows
            for row in explode_result_to_rows(result):
                all_rows.append(row)
                fieldnames.update(row.keys())

    # Ensure important fields come first in the CSV
    priority_fields = [
        "qa_pair_id",
        "question",
        "expected_chunk_id",
        "rank",
        "similarity_score",
        "is_correct_chunk",
        "retrieved_chunk_id",
        "retrieved_document_id",
        "retrieved_document_name",
        "retrieved_content",
    ]

    # Sort remaining fieldnames
    remaining_fields = sorted(field for field in fieldnames if field not in priority_fields)
    ordered_fields = [f for f in priority_fields if f in fieldnames] + remaining_fields

    # Write to CSV
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ordered_fields)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({k: row.get(k, "") for k in ordered_fields})

    return csv_path


def convert_batch_results_to_csv(batch_dir: str) -> List[str]:
    """Convert all results JSONL files in a batch directory to CSV.

    Args:
        batch_dir: Directory containing batch results

    Returns:
        List of paths to created CSV files
    """
    created_files = []

    for filename in os.listdir(batch_dir):
        if filename.startswith("results_") and filename.endswith(".jsonl"):
            jsonl_path = os.path.join(batch_dir, filename)
            csv_path = convert_results_to_csv(jsonl_path)
            created_files.append(csv_path)

    return created_files
