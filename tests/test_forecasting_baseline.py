from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from unittest import TestCase
from zoneinfo import ZoneInfo

from market_forecast.forecasting import build_day_forecast, walk_forward_backtest


KYIV = ZoneInfo("Europe/Kyiv")


def make_history(start: date, days: int):
    rows = []
    for offset in range(days):
        delivery_date = start + timedelta(days=offset)
        for hour in range(24):
            local = datetime.combine(delivery_date, time(hour), KYIV)
            price = Decimal(delivery_date.weekday() * 100 + hour)
            rows.append((local.astimezone(timezone.utc), price))
    return rows


class ForecastingBaselineTests(TestCase):
    def test_comparable_day_uses_only_prior_same_weekdays(self):
        start = date(2026, 7, 1)
        rows = make_history(start, 28)
        target = start + timedelta(days=28)

        forecast = build_day_forecast(rows, target)

        self.assertEqual(len(forecast), 24)
        self.assertTrue(all(item.method == "comparable_day" for item in forecast))
        self.assertEqual(forecast[8].predicted_price, Decimal(target.weekday() * 100 + 8))
        self.assertEqual(forecast[8].sample_count, 4)

    def test_future_outlier_cannot_change_an_earlier_forecast(self):
        start = date(2026, 7, 1)
        rows = make_history(start, 29)
        target = start + timedelta(days=28)
        baseline = build_day_forecast(rows, target)
        future_timestamp = datetime.combine(target + timedelta(days=1), time(8), KYIV).astimezone(
            timezone.utc
        )

        changed = build_day_forecast(rows + [(future_timestamp, Decimal("999999"))], target)

        self.assertEqual(baseline, changed)

    def test_walk_forward_compares_identical_out_of_sample_hours(self):
        rows = make_history(date(2026, 7, 1), 35)

        comparison = walk_forward_backtest(rows)

        self.assertGreaterEqual(comparison.comparable_day.evaluated_days, 14)
        self.assertEqual(
            comparison.comparable_day.observations,
            comparison.previous_day.observations,
        )
        self.assertEqual(comparison.comparable_day.mae, Decimal(0))
        self.assertLess(comparison.comparable_day.mae, comparison.previous_day.mae)
        self.assertEqual(comparison.champion_method, "comparable_day")

    def test_short_history_falls_back_to_previous_day(self):
        start = date(2026, 7, 1)
        rows = make_history(start, 2)

        forecast = build_day_forecast(rows, start + timedelta(days=2))

        self.assertEqual(len(forecast), 24)
        self.assertTrue(all(item.method == "previous_day" for item in forecast))

    def test_autumn_dst_day_contains_both_repeated_hours(self):
        target = date(2026, 10, 25)
        rows = make_history(target - timedelta(days=28), 28)

        forecast = build_day_forecast(rows, target)

        self.assertEqual(len(forecast), 25)
        repeated = [
            item.delivery_start_utc.astimezone(KYIV)
            for item in forecast
            if item.delivery_start_utc.astimezone(KYIV).hour == 3
        ]
        self.assertEqual(len(repeated), 2)
        self.assertEqual({item.fold for item in repeated}, {0, 1})

    def test_day_after_spring_dst_uses_latest_available_missing_hour(self):
        target = date(2026, 3, 30)
        rows = make_history(target - timedelta(days=14), 14)

        forecast = build_day_forecast(rows, target, method="previous_day")

        self.assertEqual(len(forecast), 24)
        hour_three = [
            item
            for item in forecast
            if item.delivery_start_utc.astimezone(KYIV).hour == 3
        ]
        self.assertEqual(len(hour_three), 1)
        self.assertEqual(hour_three[0].method, "recent_hour")
