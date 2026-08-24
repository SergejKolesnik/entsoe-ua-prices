import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from market_forecast.domain import HourlyMarketPrice
from market_forecast.persistence import RawArtifactStore, SQLiteMarketRepository


def make_price(
    price: str = "5000.10", bidding_zone: str = "UA-IPS"
) -> HourlyMarketPrice:
    start = datetime(2026, 8, 18, tzinfo=timezone.utc)
    return HourlyMarketPrice(
        delivery_start_utc=start,
        delivery_end_utc=start + timedelta(hours=1),
        price=Decimal(price),
        currency="UAH",
        bidding_zone=bidding_zone,
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

    def test_repository_treats_decimal_scale_as_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = SQLiteMarketRepository(root / "market.sqlite3")
            repository.initialize()
            artifact = RawArtifactStore(root / "raw").save(
                b"document", "entsoe", date(2026, 8, 18), "xml"
            )
            price = replace(
                make_price("5000.10"), volume_mwh=Decimal("100.50")
            )
            arguments = dict(
                artifact=artifact,
                source="entsoe",
                delivery_date=date(2026, 8, 18),
                source_url="https://example.test/api",
                content_type="application/xml",
                fetched_at_utc=datetime(2026, 8, 17, 12, tzinfo=timezone.utc),
                prices=[price],
                validation_status="validated",
            )
            repository.store_collection(**arguments)
            with closing(sqlite3.connect(root / "market.sqlite3")) as connection:
                connection.execute(
                    "UPDATE market_prices SET price = ?, volume_mwh = ?",
                    ("5000.1000", "100.5000"),
                )

            _, inserted = repository.store_collection(**arguments)

            self.assertEqual(inserted, 0)
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

    def test_repository_accepts_same_prices_from_new_raw_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = SQLiteMarketRepository(root / "market.sqlite3")
            repository.initialize()
            store = RawArtifactStore(root / "raw")
            common = dict(
                source="entsoe",
                delivery_date=date(2026, 8, 18),
                source_url="https://example.test/api",
                content_type="application/xml",
                fetched_at_utc=datetime(2026, 8, 17, 12, tzinfo=timezone.utc),
                prices=[make_price()],
                validation_status="validated",
            )
            repository.store_collection(
                artifact=store.save(b"revision-one", "entsoe", date(2026, 8, 18), "xml"),
                **common,
            )

            _, inserted = repository.store_collection(
                artifact=store.save(b"revision-two", "entsoe", date(2026, 8, 18), "xml"),
                **common,
            )

            self.assertEqual(inserted, 0)
            self.assertEqual(repository.count_prices(), 1)

    def test_repository_distinguishes_volume_and_revision_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = SQLiteMarketRepository(root / "market.sqlite3")
            repository.initialize()
            artifact = RawArtifactStore(root / "raw").save(
                b"document", "entsoe", date(2026, 8, 18), "xml"
            )
            original = replace(make_price(), volume_mwh=Decimal("100"))
            common = dict(
                artifact=artifact,
                source="entsoe",
                delivery_date=date(2026, 8, 18),
                source_url="https://example.test/api",
                content_type="application/xml",
                fetched_at_utc=datetime(2026, 8, 17, 12, tzinfo=timezone.utc),
                validation_status="validated",
            )
            repository.store_collection(prices=[original], **common)

            with self.assertRaisesRegex(ValueError, "Conflicting market volume"):
                repository.store_collection(
                    prices=[replace(original, volume_mwh=Decimal("101"))], **common
                )
            with self.assertRaisesRegex(ValueError, "Conflicting source revision"):
                repository.store_collection(
                    prices=[replace(original, source_revision="revision-2")], **common
                )

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

    def test_available_period_returns_stored_delivery_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = SQLiteMarketRepository(root / "market.sqlite3")
            repository.initialize()
            artifact = RawArtifactStore(root / "raw").save(
                b"document", "entsoe", date(2026, 8, 18), "xml"
            )
            repository.store_collection(
                artifact=artifact,
                source="entsoe",
                delivery_date=date(2026, 8, 18),
                source_url="https://example.test/api",
                content_type="application/xml",
                fetched_at_utc=datetime(2026, 8, 17, 12, tzinfo=timezone.utc),
                prices=[make_price()],
                validation_status="validated",
            )

            bounds = repository.available_period("entsoe")

            self.assertEqual(bounds[0], make_price().delivery_start_utc)
            self.assertEqual(bounds[1], make_price().delivery_start_utc)
            self.assertIsNone(repository.available_period("operator_market"))

    def test_forecast_snapshots_are_idempotent_and_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = SQLiteMarketRepository(Path(directory) / "market.sqlite3")
            timestamp = datetime(2026, 8, 20, tzinfo=timezone.utc)
            common = dict(
                target_delivery_date=date(2026, 8, 20),
                issued_at_utc=datetime(2026, 8, 19, 12, tzinfo=timezone.utc),
                training_cutoff_date=date(2026, 8, 19),
                model_name="previous_day",
                model_version="baseline-v1",
                backtest_days=30,
                backtest_observations=720,
                mae=Decimal("1000"),
                rmse=Decimal("1500"),
                absolute_error_p80=Decimal("2000"),
            )
            points = [
                (
                    timestamp,
                    Decimal("5000"),
                    Decimal("3000"),
                    Decimal("7000"),
                    "previous_day",
                    1,
                )
            ]

            run_id, first_created = repository.store_forecast_snapshot(
                points=points, **common
            )
            repeated_id, second_created = repository.store_forecast_snapshot(
                points=points, **common
            )

            self.assertTrue(first_created)
            self.assertFalse(second_created)
            self.assertEqual(run_id, repeated_id)
            self.assertEqual(repository.list_forecast_runs()[0][0], run_id)
            self.assertEqual(repository.list_forecast_points(run_id)[0][1], Decimal("5000"))
            changed = [
                (
                    timestamp,
                    Decimal("6000"),
                    Decimal("4000"),
                    Decimal("8000"),
                    "previous_day",
                    1,
                )
            ]
            with self.assertRaisesRegex(ValueError, "Conflicting immutable forecast"):
                repository.store_forecast_snapshot(points=changed, **common)

    def test_price_queries_can_isolate_one_bidding_zone(self) -> None:
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
            repository.store_collection(
                prices=[make_price("50", "PL")], **common
            )
            repository.store_collection(
                prices=[make_price("60", "SK")], **common
            )

            start = datetime(2026, 8, 18, tzinfo=timezone.utc)
            end = start + timedelta(days=1)

            self.assertEqual(
                repository.list_prices("entsoe", start, end, "PL")[0][1],
                Decimal("50"),
            )
            self.assertEqual(repository.available_period("entsoe", "SK")[0], start)

    def test_latest_collection_attempts_returns_one_row_per_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = SQLiteMarketRepository(Path(directory) / "market.sqlite3")
            first = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)
            second = first + timedelta(hours=1)
            repository.record_collection_attempt(
                "source_a", date(2026, 8, 20), first, "failed", message="ValueError"
            )
            repository.record_collection_attempt(
                "source_a", date(2026, 8, 21), second, "collected", 24
            )
            repository.record_collection_attempt(
                "source_b", date(2026, 8, 20), first, "unpublished"
            )

            results = repository.latest_collection_attempts(
                ["source_a", "source_b", "missing", "source_a"]
            )

            self.assertEqual(set(results), {"source_a", "source_b"})
            self.assertEqual(
                results["source_a"],
                (date(2026, 8, 21), second, "collected", 24, None),
            )
            self.assertEqual(results["source_b"][2], "unpublished")
            self.assertEqual(repository.latest_collection_attempts([]), {})


if __name__ == "__main__":
    unittest.main()
