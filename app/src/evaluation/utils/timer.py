"""Timer utility for measuring execution time."""

import time
from contextlib import contextmanager
from typing import Generator


class Timer:
    """Simple timer class for measuring execution time."""

    def __init__(self) -> None:
        """Initialize timer."""
        self.start_time = time.perf_counter()

    def elapsed_ms(self) -> float:
        """Get elapsed time in milliseconds."""
        return (time.perf_counter() - self.start_time) * 1000


@contextmanager
def measure_time() -> Generator[Timer, None, None]:
    """Context manager for measuring execution time.

    Example:
        with measure_time() as timer:
            do_something()
            print(f"Took {timer.elapsed_ms()}ms")
    """
    timer = Timer()
    yield timer
