# QA Generation Module

This module provides tools for generating high-quality question-answer pairs from documents using LLM models.

## Overview

The QA generation module provides:
1. Generation of QA pairs from documents or chunks
2. Configurable LLM models and parameters
3. Stratified sampling for targeted generation
4. Simple storage with metadata tracking

## Usage

### Command Line Interface

The evaluation CLI provides QA generation commands:

```bash
# Generate QA pairs from all documents
make generate-qa

# Generate from specific dataset with custom LLM
make generate-qa dataset="imagine_la" llm="gpt-4o-mini"

# Sample 10% of documents with fixed seed
make generate-qa sampling=0.1 random_seed=42
```

Arguments:
- `dataset`: Optional. One or more datasets (e.g., "imagine_la la_policy"). Currently supports:
  - `imagine_la`: Imagine LA Benefits Information Hub dataset
  - `la_policy`: LA County Policy dataset
- `llm`: LLM model to use (default: "gpt-4o-mini")
- `sampling`: Fraction of documents to sample (e.g., 0.1)
- `random_seed`: Random seed for reproducible sampling
- `output_dir`: Base directory for storing results (default: src/evaluation/data)

### Python API

```python
from src.evaluation.qa_generation.config import GenerationConfig
from src.evaluation.qa_generation.runner import run_generation

# Configure generation
config = GenerationConfig(
    llm_model="gpt-4o-mini",
    dataset_filter=["imagine_la"],
    sample_fraction=0.1,
    question_source="chunk",
    questions_per_unit=1
)

# Run generation
qa_pairs_path = run_generation(
    config=config,
    output_dir=Path("src/evaluation/data"),
    random_seed=42
)
```

## Data Storage

Generated QA pairs are stored in a simple directory structure:

```
src/evaluation/data/qa_pairs/
├── qa_pairs.csv        # Generated QA pairs
└── metadata.json       # Generation metadata
```

### QA Pairs CSV Format

The `qa_pairs.csv` file contains:
- `id`: Stable identifier for the QA pair
- `question`: Generated question text
- `answer`: Generated answer text
- `document_name`: Source document name
- `document_source`: Source system (e.g., "imagine_la")
- `dataset`: Dataset identifier
- `document_id`: Source document ID
- `chunk_id`: Source chunk ID (if from chunks)
- `content_hash`: Hash of source content
- `created_at`: Generation timestamp
- `llm_model`: LLM model used

### Generation Metadata

The `metadata.json` file tracks:
```json
{
  "timestamp": "2024-02-20T12:34:56",
  "llm_model": "gpt-4o-mini",
  "total_pairs": 1000,
  "datasets": ["..."],
  "git_commit": "abc123",
  "generation_config": {
    "question_source": "chunk",
    "questions_per_unit": 1,
    "sample_fraction": 0.1
  }
}
```