"""Metadata returned by source discovery operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class SourceObservation:
    """A discovered source artifact without persistence side effects."""

    source: str
    delivery_date: date
    artifact_url: str
    discovered_at: datetime
    source_reference: str

    def __post_init__(self) -> None:
        if self.discovered_at.tzinfo is None:
            raise ValueError("discovered_at must be timezone-aware")
        if not self.artifact_url.startswith("https://"):
            raise ValueError("artifact_url must use HTTPS")
