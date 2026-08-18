"""Environment-backed application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings containing no implicit credentials."""

    entsoe_token: str | None
    request_timeout_seconds: float = 30.0

    @classmethod
    def from_environment(cls) -> "Settings":
        """Load settings without logging or exposing secret values."""

        token = os.getenv("ENTSOE_TOKEN")
        timeout = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
        if timeout <= 0:
            raise ValueError("REQUEST_TIMEOUT_SECONDS must be positive")
        return cls(entsoe_token=token, request_timeout_seconds=timeout)

    def require_entsoe_token(self) -> str:
        """Return the ENTSO-E token or fail with an actionable error."""

        if not self.entsoe_token:
            raise RuntimeError("ENTSOE_TOKEN is required for ENTSO-E requests")
        return self.entsoe_token
