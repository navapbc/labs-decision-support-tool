"""Main evaluation runner."""

import os
import csv
from typing import List, Dict, Optional, Any
from ..models.metrics import BatchConfig
from .batch import (
    create_batch_config,
    filter_questions,
    stratified_sample
)
from .results import batch_process_results
from .metrics import compute_metrics_summary
from .logging import EvaluationLogger

class EvaluationRunner:
    """Runs evaluation batches and logs results."""
    
    def __init__(
        self,
        retrieval_func: Any,
        log_dir: str = "logs/evaluations"
    ):
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
            raise RuntimeError(f"Error loading questions: {e}")
    
    def run_evaluation(
        self,
        questions_file: str,
        k_values: List[int],
        dataset_filter: Optional[List[str]] = None,
        sample_fraction: Optional[float] = None,
        commit: Optional[str] = None
    ) -> None:
        """Run evaluation for multiple k values.
        
        Args:
            questions_file: Path to questions CSV file
            k_values: List of k values to evaluate
            dataset_filter: Optional list of datasets to include
            sample_fraction: Optional fraction of questions to sample
            commit: Git commit hash of code being evaluated
        """
        # Load and filter questions
        questions = self.load_questions(questions_file)
        if dataset_filter:
            print(f"Filtering questions for datasets: {dataset_filter}")
            questions = filter_questions(questions, dataset_filter)
            print(f"After filtering: {len(questions)} questions")
        
        # Apply sampling if specified
        if sample_fraction:
            print(f"Sampling {sample_fraction * 100}% of questions")
            questions = stratified_sample(questions, sample_fraction)
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
        commit: Optional[str] = None
    ) -> None:
        """Run evaluation for a single k value."""
        # Create batch config
        config = create_batch_config(
            k_value=k,
            dataset_filter=dataset_filter,
            git_commit=commit
        )
        config.num_samples = len(questions)
        
        # Initialize logger
        logger = EvaluationLogger(self.log_dir)
        
        try:
            # Start batch
            logger.start_batch(config)
            
            # Process results
            results = batch_process_results(
                questions,
                self.retrieval_func,
                k
            )
            
            # Log individual results
            for result in results:
                logger.log_result(result)
            
            # Compute and log summary metrics
            metrics = compute_metrics_summary(results, config.batch_id)
            logger.finish_batch(metrics)
            
        except Exception as e:
            print(f"Error running evaluation batch: {e}")
            raise
        finally:
            # Ensure logger is cleaned up
            logger.__exit__(None, None, None)

def run_evaluation(
    questions_file: str,
    k_values: List[int],
    retrieval_func: Any,
    dataset_filter: Optional[List[str]] = None,
    sample_fraction: Optional[float] = None,
    log_dir: str = "logs/evaluations",
    commit: Optional[str] = None
) -> None:
    """Convenience function to run evaluation."""
    runner = EvaluationRunner(
        retrieval_func=retrieval_func,
        log_dir=log_dir
    )
    
    runner.run_evaluation(
        questions_file=questions_file,
        k_values=k_values,
        dataset_filter=dataset_filter,
        sample_fraction=sample_fraction,
        commit=commit
    )
