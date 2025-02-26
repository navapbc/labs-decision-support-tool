# Evaluation Module

This module provides a comprehensive evaluation pipeline for our retrieval system, consisting of QA pair generation and retrieval performance metrics.

## Overview

The evaluation module provides:
1. QA pair generation from source documents using LLM models
2. Versioned storage of QA pairs with metadata
3. Retrieval performance evaluation using recall metrics and structured logging

## Components

### QA Generation
The QA generation module creates high-quality question-answer pairs:
- Configurable LLM models and parameters
- Support for document or chunk-level generation
- Stratified sampling for targeted generation
- Versioned storage of QA pairs

See [QA Generation README](qa_generation/README.md) for details.

### Metrics
The metrics module evaluates retrieval performance:
- Configurable evaluation parameters
- Recall@k computation
- Structured evaluation logs
- Performance tracking across datasets

See [Metrics README](metrics/README.md) for details.

## Usage

The module provides a CLI for both generation and evaluation:

```bash
# Generate QA pairs
make generate-qa dataset="imagine_la" llm="gpt-4o-mini" sampling=0.1

# Run evaluation using latest QA pairs
make evaluate dataset="imagine_la" k="5 10 25"

# Run evaluation with specific QA pairs version
make evaluate dataset="imagine_la" qa_pairs_version="20240220_123456"
```

See `make help` for all available commands and options.

## Data Flow

1. **Document Input**
   - Source documents from various datasets
   - Document chunks for granular processing

2. **QA Generation**
   - LLM generates questions from documents/chunks
   - QA pairs stored with metadata and versioning
   - Output: CSV files with QA pairs

3. **Evaluation**
   - QA pairs used to test retrieval system
   - Metrics computed and logged
   - Output: Evaluation reports and logs

## Data Storage

The module uses a structured data storage approach:

```
src/evaluation/data/
├── qa_pairs/                   # Generated QA pairs
│   ├── YYYYMMDD_HHMMSS/        # Version-specific directory
│   │   ├── qa_pairs.csv        # Generated QA pairs
│   │   └── metadata.json       # Generation metadata
│   └── latest -> YYYYMMDD.../  # Symlink to latest version
└── logs/                       # Evaluation logs
    └── evaluations/            # Evaluation results
        └── YYYY-MM-DD/         # Date-stamped structured logs
```

### QA Pairs Storage
Each QA generation run creates:
- `qa_pairs.csv`: Generated QA pairs
- `metadata.json`: Generation configuration and stats

### Evaluation Logs
Each evaluation run creates:
- `batch_${UUID}.json`: Run configuration and metadata
- `results_${UUID}.jsonl`: Individual QA pair results
- `results_${UUID}.csv`: Flattened results for analysis
- `metrics_${UUID}.json`: Aggregated metrics and analysis
