"""Utility functions for converting JSONL results to CSV format."""

import json
import csv
import os
from typing import List, Dict, Any, Optional, Iterator
from pathlib import Path


def flatten_dict(d: Dict[str, Any], parent_key: str = '', sep: str = '_') -> Dict[str, Any]:
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
        result: A single result dictionary containing evaluation_result with 
               top_k_scores (list[float]) and retrieved_chunks (list[dict])
               
    Yields:
        Dict containing flattened result with one row per retrieved chunk/score pair
    """
    # Get the base result without the arrays we'll explode
    base_result = result.copy()
    eval_result = base_result.pop('evaluation_result', {})
    
    # Extract arrays we want to explode
    top_k_scores = eval_result.pop('top_k_scores', [])
    retrieved_chunks = eval_result.pop('retrieved_chunks', [])
    
    # Add remaining eval_result fields back to base_result
    base_result['evaluation_result'] = eval_result
    base_result = flatten_dict(base_result)
    
    # If no chunks/scores, yield single flattened row
    if not retrieved_chunks or not top_k_scores:
        yield base_result
        return
        
    # Create a row for each chunk/score pair
    for idx, (chunk, score) in enumerate(zip(retrieved_chunks, top_k_scores)):
        row = base_result.copy()
        row.update({
            'rank': idx + 1,
            'similarity_score': float(score),  # Ensure score is float
            # Add chunk fields directly to row
            'retrieved_chunk_id': chunk.get('chunk_id', ''),
            'retrieved_document_id': chunk.get('document_id', ''),
            'retrieved_document_name': chunk.get('document_name', ''),
            'retrieved_content': chunk.get('content', ''),
            # Add a boolean flag for whether this chunk matches ground truth
            'is_correct_chunk': chunk.get('chunk_id', '') == result.get('expected_chunk_id', '')
        })
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
        csv_path = str(Path(jsonl_path).with_suffix('.csv'))
    
    # Read all results and get unique fields
    all_rows = []
    fieldnames = set()
    
    with open(jsonl_path, 'r') as f:
        for line in f:
            result = json.loads(line)
            # Explode each result into multiple rows
            for row in explode_result_to_rows(result):
                all_rows.append(row)
                fieldnames.update(row.keys())
    
    # Ensure important fields come first in the CSV
    priority_fields = [
        'qa_pair_id', 
        'question',
        'expected_chunk_id',
        'rank',
        'similarity_score',
        'is_correct_chunk',
        'retrieved_chunk_id',
        'retrieved_document_id',
        'retrieved_document_name',
        'retrieved_content'
    ]
    
    # Sort remaining fieldnames
    remaining_fields = sorted(field for field in fieldnames if field not in priority_fields)
    fieldnames = [f for f in priority_fields if f in fieldnames] + remaining_fields
    
    # Write to CSV
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({k: row.get(k, '') for k in fieldnames})
    
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
        if filename.startswith('results_') and filename.endswith('.jsonl'):
            jsonl_path = os.path.join(batch_dir, filename)
            csv_path = convert_results_to_csv(jsonl_path)
            created_files.append(csv_path)
    
    return created_files 