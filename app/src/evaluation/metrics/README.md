# Metrics Module

This module provides tools for evaluating retrieval performance using recall and ranking metrics.

## Overview

The metrics module allows you to:
1. Run evaluations with configurable parameters
2. Compute recall@k as the retrieval effectiveness metric 
3. Generate structured evaluation logs and CSV reports
4. Track performance across different datasets

## Usage

### Setup

The metrics module works in conjunction with the QA generation module. Before running evaluations:

1. Generate QA pairs using the QA generation module:
```bash
make generate-qa dataset="imagine_la" llm="gpt-4o-mini"
```

2. The generated QA pairs will be stored in:
   `app/src/evaluation/data/qa_pairs/YYYYMMDD_HHMMSS/qa_pairs.csv`

The generation process automatically maintains a `latest` symlink to the most recent QA pairs. This is what the evaluation module uses by default when no specific version is provided.

### Command Line Interface

The evaluation CLI provides commands for both generation and evaluation:

```bash
# Generate QA pairs for specific dataset
make generate-qa dataset="imagine_la" llm="gpt-4o-mini" sampling=0.1

# Evaluate using latest QA pairs
make evaluate dataset="imagine_la" k="5 10 25"

# Evaluate specific QA pairs version
make evaluate dataset="imagine_la" qa_pairs_version="20240220_123456"
```

Arguments:
- `dataset`: Optional. One or more datasets (e.g., "imagine_la la_policy"). Currently supports:
  - `imagine_la`: Imagine LA Benefits Information Hub dataset
  - `la_policy`: LA County Policy dataset
- `k`: One or more k values to evaluate (default: "5 10 25")
- `qa_pairs_version`: Optional version ID of QA pairs to evaluate (defaults to latest)
- `min_score`: Minimum similarity score for retrieval (default: -1.0)
- `sampling`: Fraction of questions to sample (e.g., 0.1) for each specified dataset (default: 1.0)
- `random_seed`: Random seed for reproducible sampling (only used if sampling is specified)
- `output_dir`: Base directory for storing results (default: src/evaluation/data)

### Log File Structure

Evaluation logs are stored in:
- `app/src/evaluation/data/logs/evaluations/YYYY-MM-DD/` - Evaluation logs

Each evaluation run creates four files in the logs directory:

1. `batch_${UUID}.json` - Run metadata and configuration:
```json
{
  "batch_id": "527703bd-97f1-4f51-959b-e0d8bed8cbab",
  "timestamp": "2024-02-15T09:32:47.123456",
  "evaluation_config": {
    "k_value": 5,
    "dataset_filter": ["imagine_la"],
    "num_samples": 100
  },
  "software_info": {
    "package_version": "0.1.0",
    "git_commit": "abc123"
  },
  "qa_generation_info": {
    "version_id": "20240220_123456",
    "timestamp": "2024-02-20T12:34:56",
    "llm_model": "gpt-4o-mini",
    "total_pairs": 1000,
    "datasets": ["..."],
    "git_commit": "def456"
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
    "content_hash": "abc...",
    "content": "..."
  },
  "evaluation_result": {
    "correct_chunk_retrieved": true,
    "rank_if_found": 1,
    "retrieval_time_ms": 150
  },
  "retrieved_chunks": [
    {
      "chunk_id": "123",
      "score": 0.92,
      "content": "...",
      "content_hash": "abc..."
    }
  ],
  "dataset": "imagine_la"
}
```

3. `results_${UUID}.csv` - Flattened version of `results_${UUID}.jsonl` for analysis:
- One row per retrieved chunk
- Includes original result ID, chunk details, retrieval metrics, and content hash
- Each row contains rank, similarity score, and whether it matches the expected chunk
- Easier to analyze in spreadsheet tools

The CSV contains the following columns:
- `qa_pair_id`: Unique identifier for the question-answer pair
- `question`: The original question text
- `rank`: Position of the chunk in retrieval results (1-based)
- `similarity_score`: Retrieval similarity score for this chunk
- `retrieved_chunk_id`: ID of the retrieved chunk
- `retrieved_content`: Content of the retrieved chunk
- `retrieved_content_hash`: Hash of the retrieved chunk content
- `expected_chunk_content_hash`: Hash of the expected (ground truth) chunk content
- `expected_chunk_content`: Content of expected chunk
- `expected_chunk_name`: Name of the expected source document
- `expected_chunk_source`: Source dataset of the expected chunk
- `expected_chunk_id`: ID of the expected chunk
- `is_correct_chunk`: Boolean indicating if this chunk matches the expected answer (based on content hash match)
- `evaluation_result_correct_chunk_retrieved`: Whether any correct chunk was found in the results
- `evaluation_result_rank_if_found`: Position of correct chunk if found (null if not found)
- `evaluation_result_retrieval_time_ms`: Time taken to retrieve results in milliseconds

4. `metrics_${UUID}.json` - Aggregated metrics computed from data in `results_${UUID}.jsonl`:
```json
{
  "batch_id": "527703bd-97f1-4f51-959b-e0d8bed8cbab",
  "timestamp": "2024-02-15T09:32:48.234567",
  "overall_metrics": {
    "recall_at_k": 0.90,                      // Fraction of questions where correct chunk found in top k results
    "mean_retrieval_time_ms": 145.0,          // Average retrieval time per question
    "total_questions": 100,                   // Total number of questions evaluated
    "successful_retrievals": 90,              // Questions where correct chunk was found
    "incorrect_retrievals_analysis": {
      "incorrect_retrievals_count": 10,       // Number of failed retrievals
      "avg_score_incorrect": 0.45,            // Mean similarity score of incorrect chunks
      "datasets_with_incorrect_retrievals": ["dataset1", "dataset2"]  // Datasets with failures, sorted by frequency
    }
  },
  "dataset_metrics": {
    "Imagine LA": {                           // Note: Actual dataset name from CSV
      "recall_at_k": 0.90,                    // Dataset-specific recall rate
      "sample_size": 100,                     // Questions from this dataset
      "avg_score_incorrect": 0.45             // Mean score of incorrect retrievals
    }
  }
}
```

### Metrics Explanation

Key formulas and additional details:

- **Recall@k**: Number of successful retrievals / total questions
- **Incorrect Retrievals Analysis**:
  - `avg_score_incorrect = sum(similarity_scores_of_incorrect_chunks) / count(incorrect_chunks)`
  - Helps identify if failures had misleadingly high confidence scores

Metrics are computed both overall and per dataset, providing:
- Total questions evaluated
- Successful retrievals count
- Sample size per dataset
- Average score for incorrect retrievals
``` 