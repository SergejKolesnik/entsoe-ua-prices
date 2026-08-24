import json
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from market_forecast.domain import HourlyMarketPrice, SourceObservation
from market_forecast.services import diagnose_operator_conflict
from market_forecast.sources.base import RawResponse


class StubSource:
    def discover(self, delivery_date):
        return SourceObservation(
            source="operator_market",
            delivery_date=delivery_date,
            artifact_url="https://example.test/result.xls",
            discovered_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
            source_reference="test",
        )

    def download(self, observation):
        return RawResponse(
            content=b"xls",
            source_url=observation.artifact_url,
            content_type="application/vnd.ms-excel",
            status_code=200,
        )


class StubRepository:
    def __init__(self, rows):
        self.rows = rows

    def list_price_details(self, *args, **kwargs):
        return self.rows


class OperatorDiagnosticTests(unittest.TestCase):
    def test_reports_fields_and_hours_without_returning_values(self):
        start = datetime(2026, 8, 24, 21, tzinfo=timezone.utc)
        official = HourlyMarketPrice(
            delivery_start_utc=start,
            delivery_end_utc=start + timedelta(hours=1),
            price=Decimal("5000"),
            currency="UAH",
            bidding_zone="UA-IPS",
            market="day_ahead",
            source="operator_market",
            settlement_period=1,
        )
        stored = [
            (
                start,
                start + timedelta(hours=1),
                1,
                Decimal("4000"),
                "UAH",
                "UA-IPS",
                "day_ahead",
                None,
                datetime(2026, 8, 24, tzinfo=timezone.utc),
            )
        ]
        source = StubSource()
        with patch(
            "market_forecast.services.operator_diagnostics.parse_operator_market_workbook",
            return_value=[official],
        ):
            result = diagnose_operator_conflict(
                date(2026, 8, 25), StubRepository(stored), source
            )

        self.assertEqual(result["conflicts"], [{"hour_kyiv": "00:00", "fields": ["price"]}])
        serialized = json.dumps(result)
        self.assertNotIn("4000", serialized)
        self.assertNotIn("5000", serialized)


if __name__ == "__main__":
    unittest.main()
