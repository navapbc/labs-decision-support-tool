# Metrics Module

This module provides tools for evaluating retrieval performance using recall and ranking metrics.

## Overview

The metrics module allows you to:
1. Run evaluations with configurable parameters
2. Compute recall@k as the retrieval effectiveness metric 
3. Generate structured evaluation logs and CSV reports
4. Track performance across different datasets

## Directory Structure

```
metrics/
├── __init__.py
├── README.md
├── cli.py
├── evaluation/
│   ├── __init__.py
│   ├── batch.py
│   ├── logging.py
│   ├── metrics.py
│   ├── results.py
│   └── runner.py
├── models/
│   ├── __init__.py
│   └── metrics.py
├── utils/
│   ├── __init__.py
│   ├── timer.py
│   └── jsonl_to_csv.py
├── data/           # Directory for evaluation datasets
└── logs/          # Directory for evaluation results
    └── YYYY-MM-DD/
        ├── batch_${UUID}.json
        ├── results_${UUID}.jsonl
        ├── results_${UUID}.csv
        └── metrics_${UUID}.json
```

## Usage

### Setup

Before running evaluations, you'll need the questions CSV file:
1. Download the questions file from [this Google Sheet](https://docs.google.com/spreadsheets/d/1KBFMyRUSohqA94ic6yAv3Ne22GwEBJHHYHM49rEKFsc/edit?usp=sharing)
2. Save it as `question_answer_pairs.csv` in `app/src/metrics/data/`

### Command Line Interface

The module provides a CLI for running evaluations:

```bash
make run-evaluation dataset=imagine_la k=5,10,25
```

Arguments:
- `dataset`: Filter questions from the CSV by matching this value against the 'dataset' column (e.g., "imagine_la", "la_policy", or "all" to use all datasets)
- `k`: Comma-separated list of k values (default: 5,10,25)
- `questions_file`: Path to questions CSV file (default: src/metrics/data/question_answer_pairs.csv)
- `min_score`: Minimum similarity score for retrieval (default: -1.0)
- `sampling`: Fraction of questions to sample (e.g., 0.1). Uses stratified sampling to maintain dataset proportions
- `random_seed`: Random seed for reproducible sampling (only used if sampling is specified)

### Log Storage

By default, evaluation logs and data are stored in:
- `app/src/metrics/data/` - Contains the generated QA files used for evaluation
- `app/src/metrics/logs/YYYY-MM-DD/` - Contains all evaluation run logs

### Log File Structure

Each evaluation run creates four files in the logs directory:

1. `batch_${UUID}.json` - Run metadata and configuration:
```json
{
  "batch_id": "uuid",
  "timestamp": "XXXZ",
  "evaluation_config": {
    "k_value": 5,
    "dataset_filter": ["imagine_la"],
    "num_samples": 100
  },
  "software_info": {
    "package_version": "0.1.0",
    "git_commit": "abc123"
  }
}
```

2. `results_${UUID}.jsonl` - Individual QA pair results:
```json
{
  "qa_pair_id": "uuid",
  "question": "What are the eligibility requirements?",
  "expected_answer": "...",
  "expected_chunk": {
    "name": "document.pdf",
    "source": "imagine_la",
    "chunk_id": "123",
    "content_hash": "abc..."
  },
  "evaluation_result": {
    "correct_chunk_retrieved": true,
    "rank_if_found": 1,
    "top_k_scores": [0.92, 0.85, 0.76],
    "retrieval_time_ms": 150
  },
  "retrieved_chunks": [
    {
      "chunk_id": "123",
      "score": 0.92,
      "content": "..."
    }
  ]
}
```

Note: The `qa_pair_id` is deterministic to question, answer, and dataset content. This ensures:
- Same QA pair gets same ID across different eval runs
- IDs change if question/answer content changes
- IDs are unique across different datasets
- Valid until:
  - QA pair generation module is implemented
  - We move to multiple ground truths per question (in which case we may remove dataset from UUID)

3. `results_${UUID}.csv` - Flattened results for analysis:
- One row per retrieved chunk
- Includes original result ID, chunk details, and retrieval metrics
- Easier to analyze in spreadsheet tools

4. `metrics_${UUID}.json` - Aggregated metrics:
```json
{
  "batch_id": "uuid",
  "timestamp": "XXXZ",
  "overall_metrics": {
    "recall_at_k": 0.90,
    "mean_retrieval_time_ms": 145,
    "total_questions": 100,
    "successful_retrievals": 90,
    "incorrect_retrievals_analysis": {
      "incorrect_retrievals_count": 10,
      "avg_score_incorrect": 0.45,
      "datasets_with_incorrect_retrievals": ["dataset1", "dataset2"]
    }
  },
  "dataset_metrics": {
    "imagine_la": {
      "recall_at_k": 0.90,
      "sample_size": 100,
      "avg_score_incorrect": 0.45
    }
  }
}
```

### CSV Format

The questions CSV file should have the following columns:
- question: The question text
- answer: Expected answer text
- document_name: Name of source document
- dataset: Dataset identifier (e.g., "Imagine LA")
- chunk_id: ID of chunk containing answer
- content_hash: Hash of chunk content for verification

### Metrics Explanation

The system computes several metrics to evaluate retrieval performance:

- **Recall@k**: Whether the correct chunk was found within the top k results
- **Mean Retrieval Time**: Average time in milliseconds to retrieve results
- **Incorrect Retrievals Analysis**:
  - Count of incorrect retrievals
  - Average similarity score of incorrect retrievals
  - Datasets where incorrect retrievals occurred (sorted by frequency)

Metrics are computed both overall and per dataset, providing:
- Total questions evaluated
- Successful retrievals count
- Sample size per dataset
- Average score for incorrect retrievals

## Example

```python
from src.metrics.evaluation.runner import run_evaluation
from src.retrieve import retrieve_with_scores

# Run evaluation
run_evaluation(
    questions_file="src/metrics/data/question_answer_pairs.csv",
    k_values=[5, 10, 25],
    retrieval_func=lambda q, k: retrieve_with_scores(q, k, min_score=-1.0),
    dataset_filter=["imagine_la"],
    sample_fraction=0.1
)
``` 