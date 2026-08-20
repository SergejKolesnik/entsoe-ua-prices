"""Environment-backed application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings containing no implicit credentials."""

    entsoe_token: str | None
    database_url: str | None = None
    request_timeout_seconds: float = 30.0
    database_path: Path = Path("data/market_forecast.sqlite3")
    raw_data_directory: Path = Path("data/raw")

    @classmethod
    def from_environment(cls) -> "Settings":
        """Load settings without logging or exposing secret values."""

        token = os.getenv("ENTSOE_TOKEN")
        timeout = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
        if timeout <= 0:
            raise ValueError("REQUEST_TIMEOUT_SECONDS must be positive")
        return cls(
            entsoe_token=token,
            database_url=os.getenv("DATABASE_URL") or None,
            request_timeout_seconds=timeout,
            database_path=Path(os.getenv("DATABASE_PATH", "data/market_forecast.sqlite3")),
            raw_data_directory=Path(os.getenv("RAW_DATA_DIRECTORY", "data/raw")),
        )

    def require_entsoe_token(self) -> str:
        """Return the ENTSO-E token or fail with an actionable error."""

        if not self.entsoe_token:
            raise RuntimeError("ENTSOE_TOKEN is required for ENTSO-E requests")
        return self.entsoe_token
