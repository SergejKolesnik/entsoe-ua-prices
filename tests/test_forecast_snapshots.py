from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from unittest import TestCase
from zoneinfo import ZoneInfo

from market_forecast.services import generate_baseline_snapshot


KYIV = ZoneInfo("Europe/Kyiv")


class StubRepository:
    def __init__(self, rows):
        self.rows = rows
        self.stored = None

    def available_period(self, source):
        return self.rows[0][0], self.rows[-1][0]

    def list_prices(self, source, start, end):
        return self.rows

    def store_forecast_snapshot(self, **arguments):
        self.stored = arguments
        return 7, True


def make_history(start: date, days: int):
    rows = []
    for offset in range(days):
        delivery_date = start + timedelta(days=offset)
        for hour in range(24):
            local = datetime.combine(delivery_date, time(hour), KYIV)
            rows.append(
                (
                    local.astimezone(timezone.utc),
                    Decimal(delivery_date.weekday() * 100 + hour),
                )
            )
    return rows


class ForecastSnapshotServiceTests(TestCase):
    def test_freezes_champion_for_first_unknown_delivery_day(self):
        repository = StubRepository(make_history(date(2026, 7, 1), 35))
        issued = datetime(2026, 8, 5, 12, tzinfo=timezone.utc)

        result = generate_baseline_snapshot(repository, issued)

        self.assertTrue(result.created)
        self.assertEqual(result.forecast_run_id, 7)
        self.assertEqual(result.model_name, "comparable_day")
        self.assertEqual(result.target_delivery_date, date(2026, 8, 5))
        self.assertEqual(result.points, 24)
        self.assertEqual(repository.stored["issued_at_utc"], issued)
        self.assertEqual(repository.stored["training_cutoff_date"], date(2026, 8, 4))
