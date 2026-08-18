"""Shared source transport types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RawResponse:
    """Validated transport response before format-specific parsing."""

    content: bytes
    content_type: str
    status_code: int
    source_url: str

    def require_content(self) -> bytes:
        """Return non-empty content or fail visibly."""

        if not self.content:
            raise ValueError(f"Empty response from {self.source_url}")
        return self.content
