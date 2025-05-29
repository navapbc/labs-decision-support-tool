"""Data models for metrics evaluation."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import md5
from typing import Dict, List, Optional
from uuid import UUID


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
    content: str  # The actual text content of the chunk
    document_id: str


@dataclass
class RetrievedChunk:
    """A chunk retrieved during evaluation."""

    chunk_id: str
    score: float
    content: str
    content_hash: str  # Hash of chunk content for verification
    document_id: str


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
    dataset: str  # Dataset name for this QA pair
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    correct_document_retrieved: bool = (
        False  # Whether the correct document was found in top k results
    )
    document_rank_if_found: Optional[int] = None


@dataclass
class DatasetMetrics:
    """Metrics for a specific dataset."""

    recall_at_k: float  # Whether the correct chunk was found in top k results
    sample_size: int
    avg_score_incorrect: float  # Average similarity score for incorrect retrievals in this dataset
    document_recall_at_k: float


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


# QA Generation Models
@dataclass
class QAPairVersion:
    """Version information for a QA pair set."""

    version_id: str
    llm_model: str  # Model used for generation
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class QAPair:
    """A question-answer pair with versioning."""

    question: str
    answer: str
    document_name: str
    document_source: str
    document_id: UUID
    chunk_id: Optional[UUID]
    content_hash: str
    dataset: str
    version: QAPairVersion
    expected_chunk_content: str = ""  # Content of the chunk that contains the answer
    id: Optional[UUID] = None  # Stable ID generated at creation time
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        """Generate a stable ID based on question and answer if not provided."""
        # Generate a stable UUID based on content if id is None
        if self.id is None:
            content = f"{self.question}||{self.answer}".encode("utf-8")
            content_hash = md5(content, usedforsecurity=False).digest()
            self.id = UUID(bytes=content_hash[:16])
