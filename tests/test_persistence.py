import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from market_forecast.domain import HourlyMarketPrice
from market_forecast.persistence import RawArtifactStore, SQLiteMarketRepository


def make_price(price: str = "5000.10") -> HourlyMarketPrice:
    start = datetime(2026, 8, 18, tzinfo=timezone.utc)
    return HourlyMarketPrice(
        delivery_start_utc=start,
        delivery_end_utc=start + timedelta(hours=1),
        price=Decimal(price),
        currency="UAH",
        bidding_zone="UA-IPS",
        market="day_ahead",
        source="entsoe",
        settlement_period=1,
        source_revision="revision-1",
    )


class PersistenceTests(unittest.TestCase):
    def test_raw_artifact_store_is_content_addressed_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RawArtifactStore(Path(directory))
            first = store.save(b"document", "entsoe", date(2026, 8, 18), "xml")
            second = store.save(b"document", "entsoe", date(2026, 8, 18), ".XML")
            self.assertEqual(first, second)
            self.assertEqual(first.path.read_bytes(), b"document")
            self.assertEqual(len(first.sha256), 64)

    def test_repository_retries_do_not_duplicate_prices(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = SQLiteMarketRepository(root / "market.sqlite3")
            repository.initialize()
            artifact = RawArtifactStore(root / "raw").save(
                b"document", "entsoe", date(2026, 8, 18), "xml"
            )
            arguments = dict(
                artifact=artifact,
                source="entsoe",
                delivery_date=date(2026, 8, 18),
                source_url="https://example.test/api",
                content_type="application/xml",
                fetched_at_utc=datetime(2026, 8, 17, 12, tzinfo=timezone.utc),
                prices=[make_price()],
                validation_status="validated",
            )
            _, first_inserted = repository.store_collection(**arguments)
            _, second_inserted = repository.store_collection(**arguments)
            self.assertEqual(first_inserted, 1)
            self.assertEqual(second_inserted, 0)
            self.assertEqual(repository.count_prices(), 1)

    def test_repository_rejects_conflicting_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = SQLiteMarketRepository(root / "market.sqlite3")
            repository.initialize()
            artifact = RawArtifactStore(root / "raw").save(
                b"document", "entsoe", date(2026, 8, 18), "xml"
            )
            common = dict(
                artifact=artifact,
                source="entsoe",
                delivery_date=date(2026, 8, 18),
                source_url="https://example.test/api",
                content_type="application/xml",
                fetched_at_utc=datetime(2026, 8, 17, 12, tzinfo=timezone.utc),
                validation_status="validated",
            )
            repository.store_collection(prices=[make_price()], **common)
            with self.assertRaisesRegex(ValueError, "Conflicting market price"):
                repository.store_collection(prices=[make_price("6000.00")], **common)
            with closing(sqlite3.connect(root / "market.sqlite3")) as connection:
                stored = connection.execute("SELECT price FROM market_prices").fetchone()
            self.assertEqual(stored[0], "5000.10")

    def test_repository_rejects_naive_fetch_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = SQLiteMarketRepository(root / "market.sqlite3")
            repository.initialize()
            artifact = RawArtifactStore(root / "raw").save(
                b"document", "entsoe", date(2026, 8, 18), "xml"
            )
            with self.assertRaisesRegex(ValueError, "fetched_at_utc must use UTC"):
                repository.store_collection(
                    artifact=artifact,
                    source="entsoe",
                    delivery_date=date(2026, 8, 18),
                    source_url="https://example.test/api",
                    content_type="application/xml",
                    fetched_at_utc=datetime(2026, 8, 17, 12),
                    prices=[],
                    validation_status="raw_only",
                )


if __name__ == "__main__":
    unittest.main()
