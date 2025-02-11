"""Data models for metrics evaluation."""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
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
    batch_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
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
                "git_commit": self.git_commit
            }
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
    recall_at_k: float  # Whether the correct chunk was found in top k results
    sample_size: int
    avg_score_incorrect: float  # Average similarity score for incorrect retrievals in this dataset

@dataclass
class IncorrectRetrievalsAnalysis:
    """Analysis of incorrect retrievals (where no correct chunk was found in top k)."""
    incorrect_retrievals_count: int
    avg_score_incorrect: float
    datasets_with_incorrect_retrievals: List[str]

@dataclass
class MetricsSummary:
    """Summary metrics for an evaluation batch."""
    batch_id: str
    timestamp: str
    overall_metrics: Dict[str, float]
    dataset_metrics: Dict[str, DatasetMetrics]
    incorrect_analysis: IncorrectRetrievalsAnalysis

    def to_dict(self) -> Dict:
        return {
            "batch_id": self.batch_id,
            "timestamp": self.timestamp,
            "overall_metrics": {
                **self.overall_metrics,
                "incorrect_retrievals_analysis": {
                    "incorrect_retrievals_count": self.incorrect_analysis.incorrect_retrievals_count,
                    "avg_score_incorrect": self.incorrect_analysis.avg_score_incorrect,
                    "datasets_with_incorrect_retrievals": self.incorrect_analysis.datasets_with_incorrect_retrievals
                }
            },
            "dataset_metrics": {
                dataset: asdict(metrics)
                for dataset, metrics in self.dataset_metrics.items()
            }
        }
