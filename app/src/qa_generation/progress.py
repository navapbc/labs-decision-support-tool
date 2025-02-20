from datetime import datetime
from typing import Iterator, TypeVar

from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn
from rich.console import Console

T = TypeVar("T")

class GenerationProgress:
    """Progress tracker for QA generation."""
    
    def __init__(self):
        self.console = Console()
        self.start_time = datetime.now()
        
    def process_items(self, items: list[T], description: str) -> Iterator[T]:
        """Process items with progress bar."""
        with Progress(
            SpinnerColumn(),
            *Progress.get_default_columns(),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            task = progress.add_task(description, total=len(items))
            for item in items:
                yield item
                progress.advance(task)
    
    def log_completion(self, output_path: str, total_pairs: int):
        """Log completion message."""
        duration = datetime.now() - self.start_time
        self.console.print(f"\n[green]Generation complete in {duration}[/green]")
        self.console.print(f"Generated {total_pairs} QA pairs")
        self.console.print(f"Output saved to: {output_path}") 