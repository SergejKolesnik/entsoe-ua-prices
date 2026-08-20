"""Tests for safe selection of local and cloud persistence."""

import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from market_forecast.config import Settings
from market_forecast.persistence import (
    PostgresMarketRepository,
    SQLiteMarketRepository,
    create_market_repository,
)
from market_forecast.persistence.postgres_repository import _normalize_row


class PostgresRepositoryTests(unittest.TestCase):
    """Verify configuration boundaries without requiring a live database."""

    def test_factory_keeps_sqlite_as_default(self):
        repository = create_market_repository(Path("data/local.sqlite3"))

        self.assertIsInstance(repository, SQLiteMarketRepository)
        self.assertNotIsInstance(repository, PostgresMarketRepository)

    def test_factory_selects_postgres_without_exposing_url(self):
        secret_url = "postgresql://owner:secret@example.invalid/neondb"

        repository = create_market_repository(Path("unused.sqlite3"), secret_url)

        self.assertIsInstance(repository, PostgresMarketRepository)
        self.assertEqual(str(repository.database_path), "Neon PostgreSQL")
        self.assertNotIn("secret", str(repository.database_path))

    def test_settings_read_database_url_only_from_environment(self):
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://example.invalid/neondb"},
            clear=True,
        ):
            settings = Settings.from_environment()

        self.assertEqual(settings.database_url, "postgresql://example.invalid/neondb")

    def test_postgres_values_are_normalized_to_existing_contract(self):
        timestamp = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)

        row = _normalize_row((date(2026, 8, 20), timestamp, Decimal("12.30"), 4))

        self.assertEqual(
            row,
            ("2026-08-20", "2026-08-20T12:00:00+00:00", "12.30", 4),
        )


if __name__ == "__main__":
    unittest.main()
