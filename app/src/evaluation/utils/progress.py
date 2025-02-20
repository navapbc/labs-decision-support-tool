"""Shared progress tracking utilities."""

from datetime import datetime
from typing import Iterator, TypeVar, Any, Sequence
from concurrent.futures import Future
from rich.progress import (
    Progress,
    SpinnerColumn,
    TimeElapsedColumn,
    BarColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.console import Console

T = TypeVar("T")

class ProgressTracker:
    """Generic progress tracker for long-running tasks."""
    
    def __init__(self, description: str = "Processing"):
        self.console = Console()
        self.start_time = datetime.now()
        self.description = description
        
    def track_items(self, items: Sequence[T], description: str | None = None) -> Iterator[T]:
        """Track progress through a sequence of items."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            task = progress.add_task(description or self.description, total=len(items))
            for item in items:
                yield item
                progress.advance(task)
                
    def track_futures(self, futures: dict[Future, Any], description: str | None = None) -> None:
        """Track progress of concurrent futures."""
        total = len(futures)
        completed = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            task = progress.add_task(description or self.description, total=total)
            
            while completed < total:
                # Update progress as futures complete
                done = sum(1 for f in futures if f.done())
                if done > completed:
                    progress.update(task, completed=done)
                    completed = done
    
    def log_completion(self, stats: dict[str, Any]):
        """Log completion message with stats."""
        duration = datetime.now() - self.start_time
        minutes = duration.total_seconds() / 60
        
        self.console.print(f"\n[bold green]{self.description} Complete![/bold green]")
        self.console.print(f"[yellow]Time taken:[/yellow] {duration}")
        
        # Log any additional stats
        for key, value in stats.items():
            if isinstance(value, float):
                self.console.print(f"[yellow]{key}:[/yellow] {value:.1f}")
            else:
                self.console.print(f"[yellow]{key}:[/yellow] {value}")
                
        # Calculate and log rate if items_processed is provided
        if "items_processed" in stats:
            rate = stats["items_processed"] / minutes if minutes > 0 else 0
            self.console.print(f"[yellow]Processing rate:[/yellow] {rate:.1f} items/minute") 