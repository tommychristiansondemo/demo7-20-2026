"""Metrics computation utilities."""


def compute_average_latency(records: list) -> float:
    """Compute arithmetic mean of latency values from telemetry records.

    Returns 0.0 when the record list is empty (avoids division by zero).

    Args:
        records: List of objects with a total_latency_ms attribute.

    Returns:
        The arithmetic mean of total_latency_ms values, or 0.0 if empty.
    """
    if not records:
        return 0.0
    total = sum(r.total_latency_ms for r in records)
    return total / len(records)
