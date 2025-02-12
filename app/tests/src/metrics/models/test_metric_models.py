"""Tests for metrics models."""

from datetime import datetime

from src.metrics.models.metrics import (
    BatchConfig,
    DatasetMetrics,
    DocumentInfo,
    EvaluationResult,
    IncorrectRetrievalsAnalysis,
    MetricsSummary,
    RetrievedChunk,
)


def test_batch_config_creation():
    """Test BatchConfig creation and to_dict conversion."""
    config = BatchConfig(
        k_value=5,
        num_samples=100,
        dataset_filter=["dataset1", "dataset2"],
        package_version="1.0.0",
        git_commit="abc123",
    )

    # Test that required fields are set
    assert config.k_value == 5
    assert config.num_samples == 100
    assert config.dataset_filter == ["dataset1", "dataset2"]
    assert config.package_version == "1.0.0"
    assert config.git_commit == "abc123"

    # Test that auto-generated fields are present
    assert config.batch_id is not None
    assert config.timestamp is not None

    # Test to_dict conversion
    config_dict = config.to_dict()
    assert config_dict["batch_id"] == config.batch_id
    assert config_dict["timestamp"] == config.timestamp
    assert config_dict["evaluation_config"]["k_value"] == 5
    assert config_dict["evaluation_config"]["num_samples"] == 100
    assert config_dict["evaluation_config"]["dataset_filter"] == ["dataset1", "dataset2"]
    assert config_dict["software_info"]["package_version"] == "1.0.0"
    assert config_dict["software_info"]["git_commit"] == "abc123"


def test_document_info():
    """Test DocumentInfo creation."""
    doc_info = DocumentInfo(
        name="test_doc",
        source="test_dataset",
        chunk_id="chunk123",
        content_hash="hash456",
    )
    assert doc_info.name == "test_doc"
    assert doc_info.source == "test_dataset"
    assert doc_info.chunk_id == "chunk123"
    assert doc_info.content_hash == "hash456"


def test_retrieved_chunk():
    """Test RetrievedChunk creation."""
    chunk = RetrievedChunk(
        chunk_id="chunk123",
        score=0.85,
        content="test content",
    )
    assert chunk.chunk_id == "chunk123"
    assert chunk.score == 0.85
    assert chunk.content == "test content"


def test_evaluation_result():
    """Test EvaluationResult creation and to_dict conversion."""
    doc_info = DocumentInfo(
        name="test_doc",
        source="test_dataset",
        chunk_id="chunk123",
        content_hash="hash456",
    )
    retrieved_chunk = RetrievedChunk(
        chunk_id="chunk123",
        score=0.85,
        content="test content",
    )
    result = EvaluationResult(
        qa_pair_id="qa123",
        question="test question?",
        expected_answer="test answer",
        document_info=doc_info,
        correct_chunk_retrieved=True,
        rank_if_found=1,
        top_k_scores=[0.85, 0.75],
        retrieval_time_ms=100.5,
        retrieved_chunks=[retrieved_chunk],
    )

    # Test that fields are set correctly
    assert result.qa_pair_id == "qa123"
    assert result.question == "test question?"
    assert result.expected_answer == "test answer"
    assert result.document_info == doc_info
    assert result.correct_chunk_retrieved is True
    assert result.rank_if_found == 1
    assert result.top_k_scores == [0.85, 0.75]
    assert result.retrieval_time_ms == 100.5
    assert result.retrieved_chunks == [retrieved_chunk]

    # Test to_dict conversion
    result_dict = result.to_dict()
    assert result_dict["qa_pair_id"] == "qa123"
    assert result_dict["question"] == "test question?"
    assert result_dict["expected_answer"] == "test answer"
    assert result_dict["document_info"]["name"] == "test_doc"
    assert result_dict["evaluation_result"]["correct_chunk_retrieved"] is True
    assert result_dict["evaluation_result"]["rank_if_found"] == 1
    assert result_dict["evaluation_result"]["top_k_scores"] == [0.85, 0.75]
    assert result_dict["evaluation_result"]["retrieval_time_ms"] == 100.5
    assert len(result_dict["retrieved_chunks"]) == 1
    assert result_dict["retrieved_chunks"][0]["chunk_id"] == "chunk123"


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
    """Test MetricsSummary creation and to_dict conversion."""
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

    # Test to_dict conversion
    summary_dict = summary.to_dict()
    assert summary_dict["batch_id"] == "batch123"
    assert "timestamp" in summary_dict
    assert summary_dict["overall_metrics"]["recall_at_k"] == 0.775
    assert summary_dict["overall_metrics"]["mean_retrieval_time_ms"] == 100.5
    assert summary_dict["overall_metrics"]["total_questions"] == 100
    assert summary_dict["overall_metrics"]["successful_retrievals"] == 75
    assert "incorrect_retrievals_analysis" in summary_dict["overall_metrics"]
    assert len(summary_dict["dataset_metrics"]) == 2
