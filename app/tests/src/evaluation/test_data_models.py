"""Tests for metrics models."""

from datetime import datetime
from uuid import UUID

from src.evaluation.data_models import (
    BatchConfig,
    DatasetMetrics,
    EvaluationConfig,
    EvaluationResult,
    ExpectedChunk,
    IncorrectRetrievalsAnalysis,
    MetricsSummary,
    QAGenerationInfo,
    QAPair,
    QAPairVersion,
    RetrievedChunk,
    SoftwareInfo,
)


def test_batch_config_creation():
    """Test BatchConfig creation with nested config objects."""
    eval_config = EvaluationConfig(
        k_value=5,
        num_samples=100,
        dataset_filter=["dataset1", "dataset2"],
    )
    software_info = SoftwareInfo(
        package_version="1.0.0",
        git_commit="abc123",
    )
    qa_generation_info = QAGenerationInfo(
        version_id="v1",
        timestamp=datetime.now().isoformat(),
        llm_model="gpt-4o-mini",
        total_pairs=100,
        datasets=["dataset1", "dataset2"],
    )
    config = BatchConfig(
        evaluation_config=eval_config,
        software_info=software_info,
        qa_generation_info=qa_generation_info,
    )

    # Test that required fields are set
    assert config.evaluation_config.k_value == 5
    assert config.evaluation_config.num_samples == 100
    assert config.evaluation_config.dataset_filter == ["dataset1", "dataset2"]
    assert config.software_info.package_version == "1.0.0"
    assert config.software_info.git_commit == "abc123"
    assert config.qa_generation_info.version_id == "v1"
    assert config.qa_generation_info.llm_model == "gpt-4o-mini"

    # Test that auto-generated fields are present
    assert config.batch_id is not None
    assert config.timestamp is not None


def test_expected_chunk():
    """Test ExpectedChunk creation."""
    expected = ExpectedChunk(
        name="test_doc",
        source="test_dataset",
        chunk_id="chunk123",
        content_hash="hash456",
        content="This is the test content",
    )
    assert expected.name == "test_doc"
    assert expected.source == "test_dataset"
    assert expected.chunk_id == "chunk123"
    assert expected.content_hash == "hash456"
    assert expected.content == "This is the test content"


def test_retrieved_chunk():
    """Test RetrievedChunk creation."""
    chunk = RetrievedChunk(
        chunk_id="chunk123",
        score=0.85,
        content="test content",
        content_hash="hash456",
    )
    assert chunk.chunk_id == "chunk123"
    assert chunk.score == 0.85
    assert chunk.content == "test content"
    assert chunk.content_hash == "hash456"


def test_evaluation_result():
    """Test EvaluationResult creation with all fields."""
    expected = ExpectedChunk(
        name="test_doc",
        source="test_dataset",
        chunk_id="chunk123",
        content_hash="hash456",
        content="This is the test content",
    )
    retrieved_chunk = RetrievedChunk(
        chunk_id="chunk123",
        score=0.85,
        content="test content",
        content_hash="hash456",
    )
    result = EvaluationResult(
        qa_pair_id="qa123",
        question="test question?",
        expected_answer="test answer",
        expected_chunk=expected,
        correct_chunk_retrieved=True,
        rank_if_found=1,
        retrieval_time_ms=100.5,
        retrieved_chunks=[retrieved_chunk],
        dataset="test_dataset",
    )

    # Test that fields are set correctly
    assert result.qa_pair_id == "qa123"
    assert result.question == "test question?"
    assert result.expected_answer == "test answer"
    assert result.expected_chunk == expected
    assert result.correct_chunk_retrieved is True
    assert result.rank_if_found == 1
    assert result.retrieval_time_ms == 100.5
    assert result.retrieved_chunks == [retrieved_chunk]
    assert result.dataset == "test_dataset"
    assert result.timestamp is not None


def test_dataset_metrics():
    """Test DatasetMetrics creation."""
    metrics = DatasetMetrics(
        recall_at_k=0.75,
        sample_size=100,
        avg_score_incorrect=0.45,
    )
    assert metrics.recall_at_k == 0.75
    assert metrics.sample_size == 100
    assert metrics.avg_score_incorrect == 0.45


def test_incorrect_retrievals_analysis():
    """Test IncorrectRetrievalsAnalysis creation."""
    analysis = IncorrectRetrievalsAnalysis(
        incorrect_retrievals_count=25,
        avg_score_incorrect=0.45,
        datasets_with_incorrect_retrievals=["dataset1", "dataset2"],
    )
    assert analysis.incorrect_retrievals_count == 25
    assert analysis.avg_score_incorrect == 0.45
    assert analysis.datasets_with_incorrect_retrievals == ["dataset1", "dataset2"]


def test_metrics_summary():
    """Test MetricsSummary creation with all components."""
    dataset_metrics = {
        "dataset1": DatasetMetrics(recall_at_k=0.75, sample_size=50, avg_score_incorrect=0.45),
        "dataset2": DatasetMetrics(recall_at_k=0.80, sample_size=50, avg_score_incorrect=0.40),
    }
    incorrect_analysis = IncorrectRetrievalsAnalysis(
        incorrect_retrievals_count=25,
        avg_score_incorrect=0.45,
        datasets_with_incorrect_retrievals=["dataset1", "dataset2"],
    )
    summary = MetricsSummary(
        batch_id="batch123",
        timestamp=datetime.now().isoformat(),
        overall_metrics={
            "recall_at_k": 0.775,
            "mean_retrieval_time_ms": 100.5,
            "total_questions": 100,
            "successful_retrievals": 75,
        },
        dataset_metrics=dataset_metrics,
        incorrect_analysis=incorrect_analysis,
    )

    # Test that all components are set correctly
    assert summary.batch_id == "batch123"
    assert summary.timestamp is not None
    assert summary.overall_metrics["recall_at_k"] == 0.775
    assert summary.overall_metrics["mean_retrieval_time_ms"] == 100.5
    assert summary.overall_metrics["total_questions"] == 100
    assert summary.overall_metrics["successful_retrievals"] == 75
    assert len(summary.dataset_metrics) == 2
    assert isinstance(summary.dataset_metrics["dataset1"], DatasetMetrics)
    assert isinstance(summary.dataset_metrics["dataset2"], DatasetMetrics)
    assert isinstance(summary.incorrect_analysis, IncorrectRetrievalsAnalysis)


def test_qa_pair_version():
    """Test QAPairVersion creation."""
    version = QAPairVersion(
        version_id="v1",
        llm_model="gpt-4o-mini",
    )
    assert version.version_id == "v1"
    assert version.llm_model == "gpt-4o-mini"
    assert isinstance(version.timestamp, datetime)


def test_qa_pair():
    """Test QAPair creation with all fields."""
    version = QAPairVersion(
        version_id="v1",
        llm_model="gpt-4o-mini",
    )
    qa_pair = QAPair(
        id=UUID("123e4567-e89b-12d3-a456-426614174000"),
        question="Test question?",
        answer="Test answer",
        document_name="test_doc",
        document_source="test_source",
        document_id=UUID("123e4567-e89b-12d3-a456-426614174001"),
        chunk_id=UUID("123e4567-e89b-12d3-a456-426614174002"),
        content_hash="test_hash",
        dataset="test_dataset",
        version=version,
    )

    # Test that fields are set correctly
    assert qa_pair.id == UUID("123e4567-e89b-12d3-a456-426614174000")
    assert qa_pair.question == "Test question?"
    assert qa_pair.answer == "Test answer"
    assert qa_pair.document_name == "test_doc"
    assert qa_pair.document_source == "test_source"
    assert qa_pair.document_id == UUID("123e4567-e89b-12d3-a456-426614174001")
    assert qa_pair.chunk_id == UUID("123e4567-e89b-12d3-a456-426614174002")
    assert qa_pair.content_hash == "test_hash"
    assert qa_pair.dataset == "test_dataset"
    assert qa_pair.version == version
    assert isinstance(qa_pair.created_at, datetime)
