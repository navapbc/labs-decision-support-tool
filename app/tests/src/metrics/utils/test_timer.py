"""Tests for timer utility."""

import time

from src.metrics.utils.timer import Timer, measure_time


def test_timer_elapsed_ms():
    """Test Timer class measures elapsed time correctly."""
    timer = Timer()
    time.sleep(0.1)  # Sleep for 100ms
    elapsed = timer.elapsed_ms()

    # Allow for some timing variance but ensure reasonable bounds
    assert 90 <= elapsed <= 150, f"Expected ~100ms, got {elapsed}ms"


def test_measure_time_context_manager():
    """Test measure_time context manager."""
    with measure_time() as timer:
        time.sleep(0.1)  # Sleep for 100ms
        elapsed = timer.elapsed_ms()

        # Allow for some timing variance but ensure reasonable bounds
        assert 90 <= elapsed <= 150, f"Expected ~100ms, got {elapsed}ms"


def test_timer_multiple_measurements():
    """Test Timer can take multiple measurements."""
    timer = Timer()

    # First measurement
    time.sleep(0.1)  # Sleep for 100ms
    first_elapsed = timer.elapsed_ms()

    # Second measurement
    time.sleep(0.1)  # Sleep for another 100ms
    second_elapsed = timer.elapsed_ms()

    # Verify first measurement is in range
    assert 90 <= first_elapsed <= 150, f"Expected ~100ms, got {first_elapsed}ms"

    # Verify second measurement is about double the first
    assert 190 <= second_elapsed <= 250, f"Expected ~200ms, got {second_elapsed}ms"

    # Verify second measurement is greater than first
    assert second_elapsed > first_elapsed, "Second measurement should be greater than first"
