# QA Evaluation Pipeline Technical Specification

## Current Need

Our primary need is to establish traceability of our retrieval system's performance over time. Specifically:

### Primary Need: Traceability
- Current limitation: Performance results tracked manually are difficult to trace changes and correlate with system updates to the DST retrieval application and latest dataset ingestions.
- Impact: Cannot reliably determine if system changes improve or degrade performance
- Core requirement: Systematic logging of evaluation runs with clear links to system configuration

### Secondary Needs
- Automated evaluation pipeline to reduce manual effort
- Performance comparison across system changes
- Historical dataset version tracking

## Solution Options

### MVP
- Structured log files for evaluation runs
- Simple CLI to run evaluations and view results
- Basic metadata tracking (timestamp, config, metrics)
- Manual triggering of evaluation runs

### Extended Effort
- Database storage of evaluation results
- Automated QA pairs generation and evaluation runs
- Dataset version tracking

### Full Feature Set
- Automated triggers on system changes, including software releases, new source ingestion and re-ingestion.
- Complete evaluation history in database
- Performance regression alerts
- Analytics/visualization

## Current State
- QA pairs are generated manually via `generate_q_a_pairs.py` and notebooks
- Results show precision@k and recall@k metrics
- No persistent storage of evaluation history outside of our shared Google sheet
- Database is setup for retrieval but options would be (a) new database instance is needed for evaluation or (b) a new schema is modeled for organization of evaluation logs.

## Approach

### Database Considerations
Use of database for persistent storage will allow us to:

- Run automated performance monitoring and perform trend analysis
- Set up alerts for performance regressions
- Track dataset versions and changes, and query when needed

#### Options

##### Use existing database:
- Already contains chunks and documents
- Simplified access patterns for reads and writes to main-db[dev] and main-db[prod]
- Using a separate evaluation schema will allow for flexibility for evaluation-specific optimizations

##### Dedicated evaluation database
- Additional infrastructure to maintain
- Extra authentication setup

### Proposed Data Model

#### Core Tables

##### qa_pairs
Primary storage for generated question-answer pairs

Fields:
```
id: UUID (primary key)
question: Text
answer: Text
document_name: Text
document_source: Text
dataset: Text (e.g., "LA Policy", "CA EDD")
document_id: UUID (foreign key to documents)
chunk_id: UUID (foreign key to chunks)
content_hash: Text (for verifying chunk matches)
created_at: Timestamp
generation_metadata: JSONB
    llm_model: Text
    embedding_model: Text
    temperature: Float
    system_prompt_version: Text
    max_tokens: Integer
dataset_version: Text  (track dataset iterations)
dataset_timestamp: Timestamp  (dataset was generated/updated at)
dataset_metadata: JSONB  (dataset-specific info)
    source_commit: Text
    generation_date: Timestamp
    preprocessing_config: JSONB
```

Indexes:
```
qa_pairs_dataset_idx: (dataset) - Dataset filtering
qa_pairs_created_at_idx: (created_at) - Time-based analysis
qa_pairs_document_id_idx: (document_id) - Document-based lookups
```

##### evaluation_batches
Tracks each evaluation run

Fields:
```
id: UUID (primary key)
timestamp: Timestamp
k_value: Integer
num_samples: Integer
dataset_filter: Text[]
package_release_version: Text
retriever_config: JSONB
    model_name: Text
    chunk_size: Integer
    overlap: Integer
```

Indexes:
```
eval_batches_timestamp_idx: (timestamp) - Time series analysis/monitoring
```

##### evaluation_results
Individual results for each QA pair in a batch

Fields:
```
id: UUID (primary key)
batch_id: UUID (foreign key to evaluation_batches)
qa_pair_id: UUID (foreign key to qa_pairs)
correct_chunk_retrieved: Boolean
rank_if_found: Integer
top_k_scores: Float[]
retrieval_time_ms: Float
```

Indexes:
```
eval_results_batch_idx: (batch_id) - Batch analysis
eval_results_qa_pair_idx: (qa_pair_id) - QA pair analysis
```

### MVP Implementation

#### 1. QA Pair Management
- Enhanced generation script that populates qa_pairs table
- Each generation run tagged with metadata about the LLM and prompt used
- Simple CLI to view/export QA pairs with filtering options

#### 2. Evaluation Pipeline
Evaluation Runner:
- Takes parameters: such as k_value or max_samples
- Creates evaluation_batch record
- Samples QA pairs based on criteria
- Runs evaluation via CLI storing individual results
- Outputs results to structured log file

Metrics Computation:
- Reads evaluation_results for a batch
- Computes:
  - Overall precision@k and recall@k
  - Performance by dataset
  - Retrieval time statistics
- Outputs metrics to log file in JSON format

#### 3. Automation
- Weekly Evaluation Runs (eg run every Monday at 2 AM PST)
- Generate new QA pairs from latest content
- Triggers to consider if we would like to use webhooks:
  - On new ingested data batches
  - On new production-level changes to system prompt, embedding model
- Run evaluation against all QA pairs
- Store results and metrics

#### 4. Analysis Tools
Simple Python scripts to:
- Compare metrics between batches
- Generate time series of metrics
- Export results for external analysis
- Basic error analysis (which types of questions fail)

### Log File Structure and Usage

#### Directory Structure
```
logs/
  evaluations/
    YYYY-MM-DD/
      batch_${UUID}.json       # Batch metadata and config
      results_${UUID}.jsonl    # Individual results
      metrics_${UUID}.json     # Computed metrics
```

#### File Contents

##### batch_${UUID}.json
```json
{
  "batch_id": "uuid",
  "timestamp": "XXXZ",
  "evaluation_config": {
    "k_value": X,
    "num_samples": XXX,
    "dataset_filter": ["LA County Policy", "CA EDD"]
  },
  "system_info": {
    "package_version": "X.X.X",
    "git_commit": "XXXXX",
    "environment": "development"
  },
  "retriever_config": {
    "model_name": "text-embedding-3-small",
    "chunk_size": XXX,
    "overlap": XX,
    "similarity_top_k": X
  }
}
```

##### results_${UUID}.jsonl
Each line is a JSON object representing one evaluation:
```json
{
  "qa_pair_id": "uuid",
  "question": "What are the eligibility requirements for CalFresh?",
  "expected_answer": "...",
  "document_info": {
    "name": "CalFresh_Policy_2024.pdf",
    "source": "CA EDD",
    "chunk_id": "uuid",
    "content_hash": "sha256:XXXXX"
  },
  "evaluation_result": {
    "correct_chunk_retrieved": true,
    "rank_if_found": X,
    "top_k_scores": [0.XX, 0.XX, 0.XX],
    "retrieval_time_ms": XXX
  },
  "retrieved_chunks": [
    {
      "chunk_id": "uuid",
      "score": 0.XX,
      "content": "..."
    }
  ]
}
```

##### metrics_${UUID}.json
```json
{
  "batch_id": "uuid",
  "timestamp": "XXXZ",
  "overall_metrics": {
    "precision_at_k": 0.XX,
    "recall_at_k": 0.XX,
    "mean_retrieval_time_ms": XXX,
    "total_questions": XXX,
    "successful_retrievals": XX
  },
  "dataset_metrics": {
    "LA County Policy": {
      "precision_at_k": 0.XX,
      "recall_at_k": 0.XX,
      "sample_size": XX
    },
    "CA EDD": {
      "precision_at_k": 0.XX,
      "recall_at_k": 0.XX,
      "sample_size": XX
    }
  },
  "error_analysis": {
    "failed_retrievals": XX,
    "avg_score_failed": 0.XX,
    "common_failure_datasets": ["CA EDD"]
  }
}
```

#### MVP Log File Usage

The log files serve several key purposes in th evaluation runs:

- Each evaluation run creates a new dated directory
- Batch metadata captures system state and configuration
- Results file stores individual QA pair outcomes
- Metrics file provides run summary and analysis


## Implementation Phases

### MVP (Sprint 1-2): Basic Traceability
- Implement structured logging of evaluation runs:
  - Directories with batch metadata, results, and metrics
  - Content hashes to track document/chunk changes
- Simple CLI tool to:
  - Run evals with specified parameters
  - Output results in consistent JSON format
- Basic process documentation for running and logging evaluations

### Iteration 2 (Sprint 3-4): Automation & Storage
- Database schema for evaluation results
- Migration of existing evaluation data
- Weekly automated evaluation runs
- Filter and analyze results by date, dataset, or metrics
- Basic trend analysis scripts

### Iteration 3 (Sprint 5+): Advanced Features
- Automated triggers for evaluation runs
- Performance monitoring dashboards
- Regression detection and alerts
- Advanced analytics tools

## Success Metrics
- Complete history of evaluation runs
- Ability to track performance changes over time
- Quick identification of performance regressions
- Clear attribution of performance changes to system updates

## Technical Considerations

### Performance
- Efficient storage of evaluation results
- Batch inserts for large evaluation runs
- Appropriate indexing for common queries

### Data Retention
- Keep QA pairs and evaluation artifacts in persistent storage for durability and accessibility (e.g. S3)

### Monitoring
- Log file management
- Basic error alerting