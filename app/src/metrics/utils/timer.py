"""Timer utility for measuring execution times."""

import time
from typing import Optional
from contextlib import contextmanager

class Timer:
    """Context manager for timing code execution."""
    
    def __init__(self):
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
    
    def start(self) -> None:
        """Start the timer."""
        self.start_time = time.perf_counter()
    
    def stop(self) -> float:
        """Stop the timer and return elapsed milliseconds."""
        if self.start_time is None:
            raise RuntimeError("Timer was not started")
        
        self.end_time = time.perf_counter()
        return self.elapsed_ms()
    
    def elapsed_ms(self) -> float:
        """Return elapsed milliseconds."""
        if self.start_time is None:
            raise RuntimeError("Timer was not started")
        
        end = self.end_time if self.end_time is not None else time.perf_counter()
        return (end - self.start_time) * 1000.0

@contextmanager
def measure_time():
    """Context manager for measuring execution time.
    
    Usage:
        with measure_time() as timer:
            # Code to measure
            elapsed_ms = timer.elapsed_ms()
    """
    timer = Timer()
    timer.start()
    try:
        yield timer
    finally:
        timer.stop()
