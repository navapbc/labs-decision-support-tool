"""Utilities for structured logging of evaluation results."""

import os
import json
from datetime import datetime
from typing import Dict, Any, Optional
from ..models.metrics import BatchConfig, EvaluationResult, MetricsSummary
from ..utils.jsonl_to_csv import convert_results_to_csv

class EvaluationLogger:
    """Handles structured logging for evaluation runs."""
    
    def __init__(self, base_dir: str = "logs/evaluations"):
        """Initialize logger with base directory."""
        self.base_dir = base_dir
        self.batch_id: Optional[str] = None
        self.log_dir: Optional[str] = None
        self.results_file = None
        print(f"Initializing logger with base_dir: {os.path.abspath(base_dir)}")
    
    def start_batch(self, config: BatchConfig) -> None:
        """Start a new evaluation batch."""
        self.batch_id = config.batch_id
        date_str = datetime.now().strftime("%Y-%m-%d")
        self.log_dir = os.path.join(self.base_dir, date_str)
        os.makedirs(self.log_dir, exist_ok=True)
        print(f"Created log directory: {os.path.abspath(self.log_dir)}")
        
        # Write batch config
        batch_file = os.path.join(self.log_dir, f"batch_{self.batch_id}.json")
        with open(batch_file, 'w') as f:
            json.dump(config.to_dict(), f, indent=2)
        print(f"Wrote batch config to: {os.path.abspath(batch_file)}")
        
        # Open results file for streaming
        results_file = os.path.join(self.log_dir, f"results_{self.batch_id}.jsonl")
        self.results_file = open(results_file, 'w')
        print(f"Opened results file for writing: {os.path.abspath(results_file)}")
    
    def log_result(self, result: EvaluationResult) -> None:
        """Log a single evaluation result."""
        if not self.results_file:
            raise RuntimeError("Must call start_batch before logging results")
        
        self.results_file.write(json.dumps(result.to_dict()) + '\n')
        self.results_file.flush()  # Ensure result is written immediately
    
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
        with open(metrics_file, 'w') as f:
            json.dump(metrics.to_dict(), f, indent=2)
        print(f"Wrote metrics summary to: {os.path.abspath(metrics_file)}")
        
        self.batch_id = None
        self.log_dir = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensure files are closed on exit."""
        if self.results_file:
            self.results_file.close()
            self.results_file = None
