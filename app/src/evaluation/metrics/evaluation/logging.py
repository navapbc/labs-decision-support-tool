"""Logging utilities for evaluation runs."""

import json
import os
from dataclasses import asdict
from datetime import datetime
from typing import Any, Optional, TextIO

from ..models.metrics import BatchConfig, EvaluationResult, MetricsSummary
from ..utils.jsonl_to_csv import convert_results_to_csv


class EvaluationLogger:
    """Handles structured logging for evaluation runs."""

    def __init__(self, log_dir: str):
        """Initialize the logger.

        Args:
            log_dir: Directory for log files. Results will be stored in:
                    {log_dir}/YYYY-MM-DD/
                    See README.md for details.
        """
        # Create date-based subdirectory
        self.date_dir = os.path.join(log_dir, datetime.now().strftime("%Y-%m-%d"))
        os.makedirs(self.date_dir, exist_ok=True)

        self.log_dir = self.date_dir
        self.batch_id: Optional[str] = None
        self.results_file: Optional[TextIO] = None

    def start_batch(self, config: BatchConfig) -> None:
        """Start a new evaluation batch."""
        self.batch_id = config.batch_id

        # Write batch config
        config_file = os.path.join(self.log_dir, f"batch_{self.batch_id}.json")
        with open(config_file, "w") as f:
            json.dump(asdict(config), f, indent=2)

        # Open results file
        results_file = os.path.join(self.log_dir, f"results_{self.batch_id}.jsonl")
        self.results_file = open(results_file, "w")

    def log_result(self, result: EvaluationResult) -> None:
        """Log an individual evaluation result."""
        if self.results_file:
            json.dump(asdict(result), self.results_file)
            self.results_file.write("\n")
            self.results_file.flush()

    def finish_batch(self, metrics: MetricsSummary) -> None:
        """Finish the batch and write summary metrics."""
        if self.results_file:
            results_path = self.results_file.name
            self.results_file.close()
            self.results_file = None

            # Convert results to CSV
            csv_path = convert_results_to_csv(results_path)
            print(f"Converted results to CSV: {os.path.abspath(csv_path)}")

        metrics_file = os.path.join(self.log_dir, f"metrics_{self.batch_id}.json")
        with open(metrics_file, "w") as f:
            json.dump(asdict(metrics), f, indent=2)

    def __enter__(self) -> "EvaluationLogger":
        """Enter context manager."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager."""
        if self.results_file:
            self.results_file.close()
            self.results_file = None
