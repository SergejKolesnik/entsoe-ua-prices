import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from market_forecast.domain import IntradayMarketResult
from market_forecast.persistence import RawArtifactStore, SQLiteMarketRepository


def make_result(price: str = "1500.25") -> IntradayMarketResult:
    start = datetime(2026, 8, 18, tzinfo=timezone.utc)
    return IntradayMarketResult(
        delivery_start_utc=start, delivery_end_utc=start + timedelta(hours=1),
        settlement_period=1, weighted_price_uah_per_mwh=Decimal(price),
        minimum_price_uah_per_mwh=Decimal("1000"), maximum_price_uah_per_mwh=Decimal("2000"),
        last_price_uah_per_mwh=Decimal("1600"), sale_volume_mwh=Decimal("10.5"),
        purchase_volume_mwh=Decimal("10.5"), declared_sale_volume_mwh=Decimal("20"),
        declared_purchase_volume_mwh=Decimal("21"),
    )


class IntradayPersistenceTests(unittest.TestCase):
    def test_stores_full_intraday_record_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = SQLiteMarketRepository(root / "market.sqlite3")
            artifact = RawArtifactStore(root / "raw").save(
                b"official vdr csv", "operator_intraday", make_result().delivery_start_utc.date(), "csv"
            )
            arguments = dict(
                artifact=artifact, source_url="https://example.test/idm.csv", content_type="text/csv",
                fetched_at_utc=datetime(2026, 8, 19, tzinfo=timezone.utc), results=[make_result()],
            )

            _, inserted = repository.store_intraday_collection(**arguments)
            _, retry_inserted = repository.store_intraday_collection(**arguments)
            rows = repository.list_intraday_results(make_result().delivery_start_utc.date(), make_result().delivery_start_utc.date())

            self.assertEqual((inserted, retry_inserted), (1, 0))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][3], Decimal("1500.25"))
            self.assertEqual(rows[0][7], Decimal("10.5"))

    def test_rejects_conflicting_intraday_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = SQLiteMarketRepository(root / "market.sqlite3")
            artifact = RawArtifactStore(root / "raw").save(
                b"official vdr csv", "operator_intraday", make_result().delivery_start_utc.date(), "csv"
            )
            common = dict(
                artifact=artifact, source_url="https://example.test/idm.csv", content_type="text/csv",
                fetched_at_utc=datetime(2026, 8, 19, tzinfo=timezone.utc),
            )
            repository.store_intraday_collection(results=[make_result()], **common)
            with self.assertRaisesRegex(ValueError, "Conflicting intraday"):
                repository.store_intraday_collection(results=[make_result("1600")], **common)

    def test_retry_accepts_equivalent_postgres_timestamp_spelling(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = SQLiteMarketRepository(root / "market.sqlite3")
            artifact = RawArtifactStore(root / "raw").save(
                b"official vdr csv", "operator_intraday", make_result().delivery_start_utc.date(), "csv"
            )
            arguments = dict(
                artifact=artifact, source_url="https://example.test/idm.csv", content_type="text/csv",
                fetched_at_utc=datetime(2026, 8, 19, tzinfo=timezone.utc), results=[make_result()],
            )
            repository.store_intraday_collection(**arguments)
            connection = sqlite3.connect(root / "market.sqlite3")
            try:
                connection.execute(
                    "UPDATE intraday_market_results SET delivery_end_utc = ?",
                    ("2026-08-18T01:00:00+00:00",),
                )
                connection.commit()
            finally:
                connection.close()

            _, inserted = repository.store_intraday_collection(**arguments)

            self.assertEqual(inserted, 0)
