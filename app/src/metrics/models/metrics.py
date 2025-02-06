"""Data models for metrics evaluation."""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from datetime import datetime
import uuid
import json

@dataclass
class BatchConfig:
    """Configuration for an evaluation batch."""
    k_value: int
    num_samples: int
    dataset_filter: List[str]
    package_version: str
    git_commit: str
    environment: str
    retriever_config: Dict[str, any]
    batch_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict:
        return {
            "batch_id": self.batch_id,
            "timestamp": self.timestamp,
            "evaluation_config": {
                "k_value": self.k_value,
                "num_samples": self.num_samples,
                "dataset_filter": self.dataset_filter
            },
            "system_info": {
                "package_version": self.package_version,
                "git_commit": self.git_commit,
                "environment": self.environment
            },
            "retriever_config": self.retriever_config
        }

@dataclass
class DocumentInfo:
    """Information about a document containing a chunk."""
    name: str
    source: str
    chunk_id: str
    content_hash: str

@dataclass
class RetrievedChunk:
    """A chunk retrieved during evaluation."""
    chunk_id: str
    score: float
    content: str

@dataclass
class EvaluationResult:
    """Result of evaluating a single QA pair."""
    qa_pair_id: str
    question: str
    expected_answer: str
    document_info: DocumentInfo
    correct_chunk_retrieved: bool
    rank_if_found: Optional[int]
    top_k_scores: List[float]
    retrieval_time_ms: float
    retrieved_chunks: List[RetrievedChunk]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict:
        return {
            "qa_pair_id": self.qa_pair_id,
            "question": self.question,
            "expected_answer": self.expected_answer,
            "document_info": {
                "name": self.document_info.name,
                "source": self.document_info.source,
                "chunk_id": self.document_info.chunk_id,
                "content_hash": self.document_info.content_hash
            },
            "evaluation_result": {
                "correct_chunk_retrieved": self.correct_chunk_retrieved,
                "rank_if_found": self.rank_if_found,
                "top_k_scores": self.top_k_scores,
                "retrieval_time_ms": self.retrieval_time_ms
            },
            "retrieved_chunks": [
                {
                    "chunk_id": chunk.chunk_id,
                    "score": chunk.score,
                    "content": chunk.content
                }
                for chunk in self.retrieved_chunks
            ]
        }

@dataclass
class DatasetMetrics:
    """Metrics for a specific dataset."""
    precision_at_k: float
    recall_at_k: float
    relevance: float  # Average semantic relevance of retrieved chunks
    sample_size: int

@dataclass
class ErrorAnalysis:
    """Error analysis metrics."""
    failed_retrievals: int
    avg_score_failed: float
    common_failure_datasets: List[str]

@dataclass
class MetricsSummary:
    """Summary metrics for an evaluation batch."""
    batch_id: str
    timestamp: str
    overall_metrics: Dict[str, float]
    dataset_metrics: Dict[str, DatasetMetrics]
    error_analysis: ErrorAnalysis

    def to_dict(self) -> Dict:
        return {
            "batch_id": self.batch_id,
            "timestamp": self.timestamp,
            "overall_metrics": self.overall_metrics,
            "dataset_metrics": {
                dataset: asdict(metrics)
                for dataset, metrics in self.dataset_metrics.items()
            },
            "error_analysis": {
                "failed_retrievals": self.error_analysis.failed_retrievals,
                "avg_score_failed": self.error_analysis.avg_score_failed,
                "common_failure_datasets": self.error_analysis.common_failure_datasets
            }
        }
