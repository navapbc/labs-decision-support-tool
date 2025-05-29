"""Tests for metrics models."""

from src.evaluation.data_models import (
    BatchConfig,
    DatasetMetrics,
    EvaluationConfig,
    EvaluationResult,
    ExpectedChunk,
    IncorrectRetrievalsAnalysis,
    MetricsSummary,
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
    config = BatchConfig(
        evaluation_config=eval_config,
        software_info=software_info,
    )

    # Test that required fields are set
    assert config.evaluation_config.k_value == 5
    assert config.evaluation_config.num_samples == 100
    assert config.evaluation_config.dataset_filter == ["dataset1", "dataset2"]
    assert config.software_info.package_version == "1.0.0"
    assert config.software_info.git_commit == "abc123"

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
        content="test content",
        document_id="doc456",
    )

    assert expected.name == "test_doc"
    assert expected.source == "test_dataset"
    assert expected.chunk_id == "chunk123"
    assert expected.content_hash == "hash456"
    assert expected.content == "test content"
    assert expected.document_id == "doc456"


def test_retrieved_chunk():
    """Test RetrievedChunk creation."""
    chunk = RetrievedChunk(
        chunk_id="chunk123",
        score=0.85,
        content="test content",
        content_hash="hash456",
        document_id="doc456",
    )

    assert chunk.chunk_id == "chunk123"
    assert chunk.score == 0.85
    assert chunk.content == "test content"
    assert chunk.content_hash == "hash456"
    assert chunk.document_id == "doc456"


def test_evaluation_result():
    """Test EvaluationResult creation with all fields."""
    expected = ExpectedChunk(
        name="test_doc",
        source="test_dataset",
        chunk_id="chunk123",
        content_hash="hash456",
        content="test content",
        document_id="doc456",
    )

    retrieved_chunks = [
        RetrievedChunk(
            chunk_id="chunk123",
            score=0.85,
            content="test content",
            content_hash="hash456",
            document_id="doc456",
        )
    ]

    result = EvaluationResult(
        qa_pair_id="qa123",
        question="test question?",
        expected_answer="test answer",
        expected_chunk=expected,
        retrieved_chunks=retrieved_chunks,
        correct_chunk_retrieved=True,
        rank_if_found=1,
        retrieval_time_ms=150.5,
        timestamp="2024-01-01T00:00:00Z",
        correct_document_retrieved=True,
        document_rank_if_found=1,
        dataset="test_dataset",
    )

    assert result.qa_pair_id == "qa123"
    assert result.question == "test question?"
    assert result.expected_answer == "test answer"
    assert result.expected_chunk == expected
    assert result.retrieved_chunks == retrieved_chunks
    assert result.correct_chunk_retrieved is True
    assert result.rank_if_found == 1
    assert result.retrieval_time_ms == 150.5
    assert result.timestamp == "2024-01-01T00:00:00Z"
    assert result.correct_document_retrieved is True
    assert result.document_rank_if_found == 1


def test_dataset_metrics():
    """Test DatasetMetrics creation."""
    metrics = DatasetMetrics(
        recall_at_k=0.75,
        sample_size=100,
        avg_score_incorrect=0.45,
        document_recall_at_k=0.85,
    )

    assert metrics.recall_at_k == 0.75
    assert metrics.sample_size == 100
    assert metrics.avg_score_incorrect == 0.45
    assert metrics.document_recall_at_k == 0.85


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
        "dataset1": DatasetMetrics(
            recall_at_k=0.75, sample_size=50, avg_score_incorrect=0.45, document_recall_at_k=0.85
        ),
        "dataset2": DatasetMetrics(
            recall_at_k=0.80, sample_size=50, avg_score_incorrect=0.40, document_recall_at_k=0.90
        ),
    }

    incorrect_analysis = IncorrectRetrievalsAnalysis(
        incorrect_retrievals_count=10,
        avg_score_incorrect=0.42,
        datasets_with_incorrect_retrievals=["dataset1", "dataset2"],
    )

    summary = MetricsSummary(
        batch_id="batch123",
        timestamp="2024-01-01T00:00:00Z",
        overall_metrics={
            "recall_at_k": 0.77,
            "document_recall_at_k": 0.87,
            "mean_retrieval_time_ms": 125.0,
            "total_questions": 100,
            "successful_retrievals": 77,
            "successful_document_retrievals": 87,
        },
        dataset_metrics=dataset_metrics,
        incorrect_analysis=incorrect_analysis,
    )

    assert summary.batch_id == "batch123"
    assert summary.timestamp == "2024-01-01T00:00:00Z"
    assert summary.overall_metrics["recall_at_k"] == 0.77
    assert summary.overall_metrics["document_recall_at_k"] == 0.87
    assert len(summary.dataset_metrics) == 2
    assert summary.dataset_metrics["dataset1"].recall_at_k == 0.75
