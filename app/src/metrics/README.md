# Metrics Module

This module provides tools for evaluating retrieval performance using precision and recall metrics.

## Overview

The metrics module allows you to:
1. Load QA pairs from a CSV file
2. Compute precision@k and recall@k metrics
3. Generate evaluation reports

## Directory Structure

```
metrics/
├── __init__.py
├── README.md
├── cli.py
├── evaluation.py
└── data/           # Directory for evaluation datasets
    └── README.md   # Documentation for dataset format and sources
```

## Usage

### Command Line Interface

The module provides a CLI for running evaluations:

```bash
python -m src.metrics.cli --qa-pairs-csv path/to/qa_pairs.csv --k 10 --output-json results.json
```

Arguments:
- `--qa-pairs-csv`: Path to CSV file containing QA pairs (required)
- `--k`: Number of top results to consider (default: 10)
- `--output-json`: Optional path to save results as JSON

### CSV Format

The QA pairs CSV should have the following columns:
- question
- answer
- document_name
- document_source
- dataset
- document_id
- chunk_id
- content_hash

### Metrics Explanation

- **Precision@k**: Out of k retrieved chunks, what fraction contained the correct answer
- **Recall@k**: Whether the correct chunk was found within the top k results

## Example

```python
from src.metrics.evaluation import load_qa_pairs, compute_precision_recall_at_k

# Load QA pairs from data directory
qa_pairs = load_qa_pairs("app/src/metrics/data/evaluation_dataset.csv")

# Compute metrics
precision, recall = compute_precision_recall_at_k(qa_pairs, k=10)

print(f"Precision@10: {precision:.3f}")
print(f"Recall@10: {recall:.3f}")
``` 