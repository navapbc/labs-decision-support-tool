# Evaluation Module

This module provides tools for generating and evaluating question-answer pairs for our retrieval system.

## Structure

```
evaluation/
├── cli/              # Unified CLI for all evaluation tools
├── qa_generation/    # QA pair generation from documents
├── metrics/          # Evaluation metrics and analysis
├── models/          # Shared data models
└── utils/           # Shared utilities
```

## Components

### QA Generation
- Generates question-answer pairs from documents
- Configurable LLM models and generation parameters
- Outputs versioned QA pairs for evaluation

### Metrics
- Evaluates retrieval performance using recall and ranking metrics
- Computes precision@k and recall@k
- Generates structured evaluation logs and reports

## Usage

The module provides a unified CLI for both QA generation and evaluation:

```bash
# Generate QA pairs
make generate-qa dataset="imagine_la" llm="gpt-4o-mini" sampling=0.1

# Run evaluation
make evaluate dataset="imagine_la" k="5 10 25" sampling=0.1
```

See `make help` for all available commands and options.

## Data Storage

Generated QA pairs and evaluation results are stored in:
- `src/evaluation/data/qa_pairs/` - Generated QA pairs
- `src/evaluation/data/logs/` - Evaluation logs and results

## Development

When adding new features:
1. Add tests to `tests/src/evaluation/`
2. Update this README with new functionality
3. Keep imports consistent with the module structure 