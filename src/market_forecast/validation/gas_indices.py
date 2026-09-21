"""Fail-closed freshness checks for gas benchmark source snapshots."""

from datetime import date, datetime, timezone


def validate_snapshot_date(as_of: date, retrieved_at: datetime) -> None:
    """Reject future or over-seven-day-old source snapshots, including weekends."""
    if not isinstance(retrieved_at, datetime) or retrieved_at.utcoffset() is None:
        raise ValueError("Retrieval timestamp must be timezone-aware")
    age = (retrieved_at.astimezone(timezone.utc).date() - as_of).days
    if not 0 <= age <= 7:
        raise ValueError(f"Stale or future gas snapshot: {as_of}, age={age} days")
