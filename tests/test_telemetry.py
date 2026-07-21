"""Tests for telemetry utility functions and data layer."""

import pytest
from dataclasses import dataclass

from backend.utils.truncate import truncate_message
from backend.utils.metrics import compute_average_latency


class TestTruncateMessage:
    """Tests for the message preview truncation utility."""

    def test_short_message_unchanged(self):
        """Messages <= max_length should return unchanged."""
        msg = "Hello world"
        assert truncate_message(msg) == msg

    def test_exact_max_length_unchanged(self):
        """Message exactly at max_length should return unchanged."""
        msg = "x" * 100
        assert truncate_message(msg) == msg

    def test_long_message_truncated(self):
        """Messages > max_length should be truncated with ellipsis."""
        msg = "y" * 200
        result = truncate_message(msg)
        assert result == "y" * 100 + "..."
        assert len(result) == 103

    def test_empty_message(self):
        """Empty string should return unchanged."""
        assert truncate_message("") == ""

    def test_custom_max_length(self):
        """Custom max_length parameter should be respected."""
        msg = "abcdefghij"  # 10 chars
        assert truncate_message(msg, max_length=5) == "abcde..."

    def test_one_over_max_length(self):
        """Message one char over max_length should be truncated."""
        msg = "a" * 101
        result = truncate_message(msg, max_length=100)
        assert result == "a" * 100 + "..."


class TestComputeAverageLatency:
    """Tests for the average latency computation function."""

    def test_empty_list(self):
        """Empty list should return 0.0."""
        assert compute_average_latency([]) == 0.0

    def test_single_record(self):
        """Single record should return its latency."""
        @dataclass
        class FakeRecord:
            total_latency_ms: float

        records = [FakeRecord(total_latency_ms=500.0)]
        assert compute_average_latency(records) == 500.0

    def test_multiple_records(self):
        """Multiple records should return arithmetic mean."""
        @dataclass
        class FakeRecord:
            total_latency_ms: float

        records = [
            FakeRecord(total_latency_ms=100.0),
            FakeRecord(total_latency_ms=200.0),
            FakeRecord(total_latency_ms=300.0),
        ]
        assert compute_average_latency(records) == 200.0

    def test_zero_latencies(self):
        """All-zero latencies should return 0.0."""
        @dataclass
        class FakeRecord:
            total_latency_ms: float

        records = [FakeRecord(total_latency_ms=0.0) for _ in range(5)]
        assert compute_average_latency(records) == 0.0
