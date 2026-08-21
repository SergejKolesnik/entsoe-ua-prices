import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from market_forecast.domain import HourlyMarketPrice
from market_forecast.persistence import RawArtifactStore, SQLiteMarketRepository
from market_forecast.services.report_export import build_daily_report, write_daily_report


KYIV = ZoneInfo("Europe/Kyiv")


class FakeRepository:
    def __init__(self) -> None:
        self.details = []
        self.latest_delivery = None

    def add_day(self, delivery_date, *, missing=0, price="100", volume="5"):
        start = datetime.combine(delivery_date, datetime.min.time(), KYIV).astimezone(timezone.utc)
        end = datetime.combine(
            delivery_date + timedelta(days=1), datetime.min.time(), KYIV
        ).astimezone(timezone.utc)
        count = int((end - start).total_seconds() // 3600) - missing
        for index in range(count):
            timestamp = start + timedelta(hours=index)
            self.details.append(
                (
                    timestamp,
                    timestamp + timedelta(hours=1),
                    index + 1,
                    Decimal(price),
                    "UAH",
                    "UA-IPS",
                    "DAM",
                    Decimal(volume) if volume is not None else None,
                    datetime(2026, 8, 21, 12, tzinfo=timezone.utc),
                )
            )
        self.latest_delivery = max(delivery_date, self.latest_delivery or delivery_date)

    def list_price_details(self, source, start, end, bidding_zone=None):
        return [row for row in self.details if start <= row[0] < end]

    def available_period(self, source, bidding_zone=None):
        if not self.details:
            return None
        return min(row[0] for row in self.details), max(row[0] for row in self.details)

    def latest_collection_attempts(self, sources):
        return {}

    def list_exchange_rates(self, date_from, date_to):
        return {}

    def list_prices(self, source, start, end, bidding_zone=None):
        return []

    def list_flows(self, start, end):
        return []

    def list_weather_forecasts(self, start, end):
        return []

    def list_forecast_runs(self, limit=30):
        return []

    def list_forecast_points(self, forecast_run_id):
        return []


class HermesReportTests(unittest.TestCase):
    def test_complete_contract_has_numeric_values_and_explicit_missing_context(self):
        repository = FakeRepository()
        target = date(2026, 8, 21)
        for offset in range(7, -1, -1):
            repository.add_day(target - timedelta(days=offset))

        report = build_daily_report(
            repository,
            target,
            generated_at=datetime(2026, 8, 21, 14, tzinfo=timezone.utc),
        )

        self.assertEqual(report["schema_version"], "1.0")
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["quality"]["expected_period_count"], 24)
        self.assertEqual(report["quality"]["complete_period_count"], 24)
        self.assertIsInstance(report["summary"]["average_price"], int)
        self.assertEqual(report["summary"]["total_volume_mwh"], 120)
        self.assertEqual(report["summary"]["trailing_7_days"]["complete_days"], 7)
        self.assertEqual(report["context"]["fx"]["status"], "unavailable")
        self.assertEqual(report["context"]["weather"]["status"], "unavailable")
        self.assertNotIn("DATABASE_URL", json.dumps(report))

    def test_dst_days_accept_23_and_25_periods(self):
        for target, expected in (
            (date(2026, 3, 29), 23),
            (date(2026, 10, 25), 25),
        ):
            with self.subTest(target=target):
                repository = FakeRepository()
                repository.add_day(target)
                report = build_daily_report(repository, target)
                self.assertEqual(report["status"], "complete")
                self.assertEqual(report["quality"]["expected_period_count"], expected)
                self.assertEqual(len(report["hourly"]), expected)
        autumn = build_daily_report(repository, date(2026, 10, 25))
        repeated = [item for item in autumn["hourly"] if item["local_hour"] == 3]
        self.assertEqual([item["local_fold"] for item in repeated], [0, 1])

    def test_incomplete_day_is_explicit_and_never_filled_with_zero(self):
        repository = FakeRepository()
        target = date(2026, 8, 21)
        repository.add_day(target, missing=1)

        report = build_daily_report(repository, target)

        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["quality"]["actual_period_count"], 23)
        self.assertEqual(report["quality"]["complete_period_count"], 23)
        self.assertEqual(len(report["hourly"]), 23)

    def test_future_request_with_older_data_is_stale(self):
        repository = FakeRepository()
        repository.add_day(date(2026, 8, 20))

        report = build_daily_report(repository, date(2026, 8, 22))

        self.assertEqual(report["status"], "stale")
        self.assertEqual(report["quality"]["freshness_status"], "stale")
        self.assertIsNone(report["summary"]["average_price"])

    def test_json_writer_is_deterministic_and_valid(self):
        repository = FakeRepository()
        target = date(2026, 8, 21)
        repository.add_day(target)
        report = build_daily_report(
            repository,
            target,
            generated_at=datetime(2026, 8, 21, 14, tzinfo=timezone.utc),
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "latest.json"
            write_daily_report(report, output)
            first = output.read_bytes()
            write_daily_report(report, output)
            self.assertEqual(first, output.read_bytes())
            self.assertEqual(json.loads(first)["delivery_date"], target.isoformat())

    def test_sqlite_repository_integration_builds_complete_report(self):
        target = date(2026, 8, 21)
        start = datetime.combine(target, datetime.min.time(), KYIV).astimezone(timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = SQLiteMarketRepository(root / "market.sqlite3")
            repository.initialize()
            artifact = RawArtifactStore(root / "raw").save(
                b"validated operator workbook", "operator_market", target, "xls"
            )
            prices = [
                HourlyMarketPrice(
                    delivery_start_utc=start + timedelta(hours=index),
                    delivery_end_utc=start + timedelta(hours=index + 1),
                    settlement_period=index + 1,
                    price=Decimal("100") + index,
                    currency="UAH",
                    bidding_zone="UA-IPS",
                    market="day_ahead",
                    source="operator_market",
                    volume_mwh=Decimal("10"),
                )
                for index in range(24)
            ]
            repository.store_collection(
                artifact=artifact,
                source="operator_market",
                delivery_date=target,
                source_url="https://example.test/operator",
                content_type="application/vnd.ms-excel",
                fetched_at_utc=datetime(2026, 8, 20, 12, tzinfo=timezone.utc),
                prices=prices,
                validation_status="validated",
            )

            report = build_daily_report(repository, target)

            self.assertEqual(report["status"], "complete")
            self.assertEqual(report["quality"]["actual_period_count"], 24)
            self.assertEqual(report["hourly"][0]["price"], 100)
            self.assertEqual(report["hourly"][-1]["price"], 123)


if __name__ == "__main__":
    unittest.main()
