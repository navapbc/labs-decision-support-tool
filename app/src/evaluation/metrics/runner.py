"""Main evaluation runner."""

import csv
import os
from typing import Any, Callable, Dict, List, Optional, Sequence

from src.retrieve import retrieve_with_scores
from src.util.sampling import get_stratified_sample

from .batch import create_batch_config, filter_questions
from .logging import EvaluationLogger
from .metric_computation import compute_metrics_summary
from .results import batch_process_results


def create_retrieval_function(
    min_score: Optional[float] = None,
) -> Callable[[str, int], Sequence[Any]]:
    """Create a function to retrieve chunks for a question.

    Args:
        min_score: Optional minimum similarity score for retrieval

    Returns:
        Function that takes a question and k value and returns retrieved chunks
    """

    def retrieval_func(query: str, k: int) -> Sequence[Any]:
        # Default to -1.0 if no min_score provided
        score_threshold = min_score if min_score is not None else -1.0
        return retrieve_with_scores(
            query=query, retrieval_k=k, retrieval_k_min_score=score_threshold
        )

    return retrieval_func


class EvaluationRunner:
    """Runs evaluation batches and logs results."""

    def __init__(self, retrieval_func: Any, log_dir: str = "logs/evaluations"):
        """Initialize the runner.

        Args:
            retrieval_func: Function to retrieve chunks for questions (uses model from app_config)
            log_dir: Directory for log files
        """
        self.retrieval_func = retrieval_func
        self.log_dir = log_dir

    def load_questions(self, file_path: str) -> List[Dict]:
        """Load questions from CSV file."""
        print(f"Loading questions from: {os.path.abspath(file_path)}")
        try:
            with open(file_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                questions = list(reader)
                print(f"Loaded {len(questions)} questions")
                return questions
        except Exception as e:
            raise RuntimeError(f"Error loading questions: {e}") from e

    def run_evaluation(
        self,
        questions_file: str,
        k_values: List[int],
        dataset_filter: Optional[List[str]] = None,
        min_score: Optional[float] = None,
        sample_fraction: Optional[float] = None,
        min_samples: Optional[int] = None,
        random_seed: Optional[int] = None,
        commit: Optional[str] = None,
    ) -> None:
        """Run evaluation for multiple k values.

        Args:
            questions_file: Path to questions CSV file
            k_values: List of k values to evaluate
            dataset_filter: Optional list of datasets to filter questions by
            min_score: Optional minimum similarity score for retrieval
            sample_fraction: Optional fraction of questions to sample
            min_samples: Optional minimum number of samples per dataset
            random_seed: Optional seed for reproducible sampling
            commit: Optional git commit hash
        """
        # Load and filter questions
        questions = self.load_questions(questions_file)
        if dataset_filter:
            print(f"Filtering questions for datasets: {dataset_filter}")
            questions = filter_questions(questions, dataset_filter)
            print(f"After filtering: {len(questions)} questions")

        # Sample questions if needed
        if sample_fraction or min_samples:
            if sample_fraction and not 0 < sample_fraction <= 1:
                raise ValueError("Sample fraction must be between 0 and 1")
            questions = get_stratified_sample(
                items=questions,
                sample_fraction=sample_fraction,
                min_samples=min_samples,
                random_seed=random_seed,
                key_func=lambda q: q["dataset"],
            )
            print(f"After sampling: {len(questions)} questions")

        if not questions:
            raise ValueError("No questions to evaluate after filtering/sampling")

        # Run evaluation for each k value
        for k in k_values:
            print(f"\nEvaluating k={k}")
            self.run_evaluation_batch(questions, k, dataset_filter, commit)

    def run_evaluation_batch(
        self,
        questions: List[Dict],
        k: int,
        dataset_filter: Optional[List[str]] = None,
        commit: Optional[str] = None,
    ) -> None:
        """Run evaluation for a single k value."""
        logger = None
        try:
            # Create batch config
            config = create_batch_config(
                k_value=k, dataset_filter=dataset_filter, git_commit=commit
            )
            config.evaluation_config.num_samples = len(questions)

            # Initialize logger
            logger = EvaluationLogger(self.log_dir)

            # Start batch
            logger.start_batch(config)

            # Process results
            results = batch_process_results(questions, self.retrieval_func, k)

            # Log individual results
            for result in results:
                logger.log_result(result)

            # Compute and log summary metrics
            metrics = compute_metrics_summary(results, config.batch_id)
            logger.finish_batch(metrics)

        except Exception as e:
            print(f"Error running evaluation batch: {e}")
            if logger:
                # Pass error information to logger.__exit__
                logger.__exit__(type(e), e, e.__traceback__)
            raise
        else:
            if logger:
                # No error occurred, clean up normally
                logger.__exit__(None, None, None)


def run_evaluation(
    questions_file: str,
    k_values: List[int],
    retrieval_func: Any,
    dataset_filter: Optional[List[str]] = None,
    min_score: Optional[float] = None,
    sample_fraction: Optional[float] = None,
    min_samples: Optional[int] = None,
    random_seed: Optional[int] = None,
    log_dir: str = "logs/evaluations",
    commit: Optional[str] = None,
) -> None:
    """Convenience function to run evaluation.

    Args:
        questions_file: Path to questions CSV file
        k_values: List of k values to evaluate
        retrieval_func: Function to retrieve chunks for questions
        dataset_filter: Optional list of datasets to filter questions by
        min_score: Optional minimum similarity score for retrieval
        sample_fraction: Optional fraction of questions to sample
        min_samples: Optional minimum number of samples per dataset
        random_seed: Optional seed for reproducible sampling
        log_dir: Directory for log files
        commit: Optional git commit hash
    """
    runner = EvaluationRunner(retrieval_func=retrieval_func, log_dir=log_dir)
    runner.run_evaluation(
        questions_file=questions_file,
        k_values=k_values,
        dataset_filter=dataset_filter,
        min_score=min_score,
        sample_fraction=sample_fraction,
        min_samples=min_samples,
        random_seed=random_seed,
        commit=commit,
    )
