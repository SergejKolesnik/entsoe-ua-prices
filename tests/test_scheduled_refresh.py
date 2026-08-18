from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from market_forecast.persistence import SQLiteMarketRepository
from market_forecast.services import CollectionResult, next_delivery_date, refresh_operator_day


class StubService:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def collect_operator_artifact(self, delivery_date, source):
        if self.error:
            raise self.error
        return self.result


class ScheduledRefreshTests(TestCase):
    def test_next_delivery_date_uses_kyiv_calendar(self):
        late_utc = datetime(2026, 8, 18, 21, 30, tzinfo=timezone.utc)

        self.assertEqual(next_delivery_date(late_utc), date(2026, 8, 20))

    def test_records_unpublished_attempt(self):
        with TemporaryDirectory() as directory:
            repository = SQLiteMarketRepository(Path(directory) / "market.sqlite3")
            attempted = datetime(2026, 8, 18, 12, 15, tzinfo=timezone.utc)

            result = refresh_operator_day(
                date(2026, 8, 19), StubService(), object(), repository, attempted
            )

            self.assertEqual(result.status, "unpublished")
            latest = repository.latest_collection_attempt("operator_market")
            self.assertIsNotNone(latest)
            self.assertEqual(latest[:4], (date(2026, 8, 19), attempted, "unpublished", 0))

    def test_records_success_and_sanitized_failure(self):
        with TemporaryDirectory() as directory:
            repository = SQLiteMarketRepository(Path(directory) / "market.sqlite3")
            attempted = datetime(2026, 8, 18, 13, 0, tzinfo=timezone.utc)
            collected = CollectionResult("operator_market", date(2026, 8, 19), "abc", 24, 24)

            success = refresh_operator_day(
                date(2026, 8, 19), StubService(result=collected), object(), repository, attempted
            )
            failure = refresh_operator_day(
                date(2026, 8, 20),
                StubService(error=RuntimeError("secret URL should not be stored")),
                object(),
                repository,
                datetime(2026, 8, 18, 14, 0, tzinfo=timezone.utc),
            )

            self.assertEqual(success.inserted_records, 24)
            self.assertEqual(failure.message, "RuntimeError")
            latest = repository.latest_collection_attempt("operator_market")
            self.assertEqual(latest[2:], ("failed", 0, "RuntimeError"))
