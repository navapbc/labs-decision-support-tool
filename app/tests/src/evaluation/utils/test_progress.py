"""Tests for progress tracking utilities."""

from concurrent.futures import Future
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console
from rich.progress import Progress

from src.evaluation.utils.progress import ProgressTracker


@pytest.fixture
def tracker():
    """Create a ProgressTracker instance for testing."""
    return ProgressTracker(description="Test Progress")


@pytest.fixture
def mock_console():
    """Create a mock console."""
    return MagicMock(spec=Console)


@pytest.fixture
def mock_progress():
    """Create a mock Progress instance."""
    mock = MagicMock(spec=Progress)
    mock.__enter__.return_value = mock
    mock.__exit__.return_value = None
    return mock


def test_progress_tracker_init():
    """Test ProgressTracker initialization."""
    description = "Test Progress"
    tracker = ProgressTracker(description=description)

    assert isinstance(tracker.console, Console)
    assert tracker.description == description
    assert isinstance(tracker.start_time, datetime)


def test_track_items(tracker, mock_progress):
    """Test tracking progress through a sequence of items."""
    items = ["item1", "item2", "item3"]

    with patch("src.evaluation.utils.progress.Progress", return_value=mock_progress):
        # Track items and collect results
        results = list(tracker.track_items(items))

        # Verify progress tracking
        mock_progress.add_task.assert_called_once_with(tracker.description, total=len(items))
        assert mock_progress.advance.call_count == len(items)

        # Verify items were yielded correctly
        assert results == items


def test_track_items_custom_description(tracker, mock_progress):
    """Test tracking items with custom description."""
    items = ["item1", "item2"]
    custom_desc = "Custom Progress"

    with patch("src.evaluation.utils.progress.Progress", return_value=mock_progress):
        list(tracker.track_items(items, description=custom_desc))
        mock_progress.add_task.assert_called_once_with(custom_desc, total=len(items))


def test_track_futures(tracker, mock_progress):
    """Test tracking progress of concurrent futures."""
    # Create mock futures
    futures = {
        MagicMock(spec=Future): "task1",
        MagicMock(spec=Future): "task2",
        MagicMock(spec=Future): "task3",
    }

    # Set up futures to complete in sequence
    future_list = list(futures.keys())
    future_list[0].done.side_effect = [True] * 10
    future_list[1].done.side_effect = [False] * 2 + [True] * 8
    future_list[2].done.side_effect = [False] * 4 + [True] * 6

    with patch("src.evaluation.utils.progress.Progress", return_value=mock_progress):
        tracker.track_futures(futures)

        # Verify progress tracking
        mock_progress.add_task.assert_called_once_with(tracker.description, total=len(futures))
        assert mock_progress.update.call_count > 0


def test_track_futures_custom_description(tracker, mock_progress):
    """Test tracking futures with custom description."""
    futures = {MagicMock(spec=Future): "task"}
    custom_desc = "Custom Progress"

    with patch("src.evaluation.utils.progress.Progress", return_value=mock_progress):
        tracker.track_futures(futures, description=custom_desc)
        mock_progress.add_task.assert_called_once_with(custom_desc, total=1)


def test_log_completion_basic(tracker):
    """Test basic completion logging."""
    with patch.object(tracker, "console") as mock_console:
        stats = {"Total": 10, "Processed": 8}
        tracker.log_completion(stats)

        # Verify console output
        assert mock_console.print.call_count >= 3  # Header + duration + stats

        # Verify completion message
        completion_call = mock_console.print.call_args_list[0]
        assert "Complete" in str(completion_call)


def test_log_completion_with_processing_rate(tracker):
    """Test completion logging with processing rate calculation."""
    # Set start time to calculate duration
    tracker.start_time = datetime.now() - timedelta(minutes=2)

    with patch.object(tracker, "console") as mock_console:
        stats = {
            "Total": 10,
            "Processed": 8,
            "items_processed": 100,  # Should trigger rate calculation
        }
        tracker.log_completion(stats)

        # Verify rate calculation was included
        calls = [str(call) for call in mock_console.print.call_args_list]
        rate_logged = any("Processing rate" in str(call) for call in calls)
        assert rate_logged


def test_log_completion_float_formatting(tracker):
    """Test float value formatting in completion logging."""
    with patch.object(tracker, "console") as mock_console:
        stats = {"Score": 0.12345, "Rate": 42.6789}
        tracker.log_completion(stats)

        # Verify float formatting
        calls = [str(call) for call in mock_console.print.call_args_list]
        float_calls = [call for call in calls if "0.1" in call or "42.7" in call]
        assert len(float_calls) == 2


def test_track_items_empty_sequence(tracker, mock_progress):
    """Test tracking progress with empty sequence."""
    with patch("src.evaluation.utils.progress.Progress", return_value=mock_progress):
        results = list(tracker.track_items([]))

        assert len(results) == 0
        mock_progress.add_task.assert_called_once_with(tracker.description, total=0)
        assert mock_progress.advance.call_count == 0


def test_track_futures_empty_dict(tracker, mock_progress):
    """Test tracking progress with empty futures dict."""
    with patch("src.evaluation.utils.progress.Progress", return_value=mock_progress):
        tracker.track_futures({})

        mock_progress.add_task.assert_called_once_with(tracker.description, total=0)
        assert mock_progress.update.call_count == 0


def test_log_completion_zero_duration(tracker):
    """Test completion logging when duration is zero."""
    # Set start time to now to simulate zero duration
    tracker.start_time = datetime.now()

    with patch.object(tracker, "console") as mock_console:
        stats = {"items_processed": 100}
        tracker.log_completion(stats)

        # Verify rate calculation handles zero duration
        calls = [str(call) for call in mock_console.print.call_args_list]
        rate_logged = any("Processing rate" in str(call) for call in calls)
        assert rate_logged
