"""Data models for metrics evaluation."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class EvaluationConfig:
    """Configuration for evaluation parameters."""

    k_value: int
    num_samples: int
    dataset_filter: List[str]


@dataclass
class SoftwareInfo:
    """Software version and commit information."""

    package_version: str
    git_commit: str


@dataclass
class BatchConfig:
    """Configuration for an evaluation batch."""

    evaluation_config: EvaluationConfig
    software_info: SoftwareInfo
    batch_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ExpectedChunk:
    """Information about the expected/ground truth chunk containing the answer."""

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
    content_hash: str  # Hash of chunk content for verification


@dataclass
class EvaluationResult:
    """Result of evaluating a single QA pair."""

    qa_pair_id: str
    question: str
    expected_answer: str
    expected_chunk: ExpectedChunk
    correct_chunk_retrieved: bool
    rank_if_found: Optional[int]
    retrieval_time_ms: float
    retrieved_chunks: List[RetrievedChunk]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


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
