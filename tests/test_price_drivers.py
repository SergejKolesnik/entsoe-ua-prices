import unittest
from datetime import date

import pandas as pd

from market_forecast.analysis import (
    analyze_flow_price_relationship,
    align_hourly_flow_prices,
    build_daily_explanation,
    build_daily_market_brief,
    build_hourly_price_flow_comparison,
    build_price_driver_comparison,
    daily_net_import_comparison,
    describe_flow_price_relationship,
    complete_flow_days,
    neighbor_daily_change,
)


class PriceDriverComparisonTests(unittest.TestCase):
    def test_daily_brief_card_renders_without_a_source_request(self):
        from streamlit.testing.v1 import AppTest

        selected = date(2026, 8, 21)
        previous = date(2026, 8, 20)
        prices = pd.DataFrame(
            [
                {"delivery_date": day, "hour": hour, "price": price}
                for day, price in ((previous, 5_000), (selected, 6_000))
                for hour in range(24)
            ]
        )
        volumes = pd.DataFrame(
            [
                {"delivery_date": previous, "volume_mwh": 100},
                {"delivery_date": selected, "volume_mwh": 120},
            ]
        )
        script = (
            "import datetime\n"
            "from datetime import date\n"
            "from pathlib import Path\n"
            "from unittest.mock import patch\n"
            "import pandas as pd\n"
            "import streamlit_app as app\n"
            f"prices = pd.DataFrame({prices.to_dict('records')!r})\n"
            f"volumes = pd.DataFrame({volumes.to_dict('records')!r})\n"
            "with patch.object(app, '_load_price_volumes', return_value=volumes), "
            "patch.object(app, '_load_weather_day_context', return_value={"
            "'forecast_vintage_utc': datetime.datetime(2026, 8, 20, 18, tzinfo=datetime.timezone.utc), "
            "'temperature_min_c': 12.0, 'temperature_max_c': 24.0, "
            "'daylight_cloud_cover_percent': 40.0, 'daylight_radiation_wm2': 200.0, "
            "'locations': 6}):\n"
            f"    app._draw_daily_market_brief(Path('unused'), prices, date(2026, 8, 20), date(2026, 8, 21), date(2026, 8, 21))\n"
        )

        rendered = AppTest.from_string(script).run(timeout=30)

        self.assertEqual(len(rendered.exception), 0)
        self.assertEqual(rendered.markdown[0].value, "### Щоденний огляд РДН")
        self.assertEqual(len(rendered.metric), 7)

    def test_daily_brief_uses_only_complete_price_days_and_labels_missing_context(self):
        selected = date(2026, 8, 21)
        previous = date(2026, 8, 20)
        prices = pd.DataFrame(
            [
                {"delivery_date": day, "hour": hour, "price": price}
                for day, price in ((previous, 5_000), (selected, 6_000))
                for hour in range(24)
            ]
        )
        volumes = pd.DataFrame(
            [
                {"delivery_date": previous, "volume_mwh": 100},
                {"delivery_date": selected, "volume_mwh": 120},
            ]
        )

        brief = build_daily_market_brief(prices, volumes, selected)

        self.assertIsNotNone(brief)
        self.assertIn("ціна РДН", brief.confirmed_signals)
        self.assertIn("обсяг РДН", brief.confirmed_signals)
        self.assertEqual(brief.unavailable_signals, ())
        self.assertIn("Середня ціна РДН", brief.summary)
        self.assertIn("Найбільша зміна", brief.summary)

        incomplete = prices.iloc[:-1]
        self.assertIsNone(
            build_daily_market_brief(incomplete, volumes, selected)
        )

    def test_complete_flow_days_requires_every_market_and_handles_spring_dst(self):
        delivery_date = date(2026, 3, 29)
        rows = [
            {
                "delivery_date": delivery_date,
                "market_name": market,
                "direction": direction,
                "interval_hours": 23.0,
            }
            for market in ("Польща", "Словаччина", "Угорщина", "Румунія")
            for direction in ("Імпорт", "Експорт")
        ]

        complete = complete_flow_days(pd.DataFrame(rows))

        self.assertEqual(len(complete), 8)
        self.assertTrue(complete_flow_days(pd.DataFrame(rows[:-1])).empty)

    def test_compares_latest_earlier_day_and_segments(self):
        prices = pd.DataFrame(
            [
                {"delivery_date": date(2026, 8, 19), "hour": hour, "price": 8_000}
                for hour in range(24)
            ]
            + [
                {
                    "delivery_date": date(2026, 8, 21),
                    "hour": hour,
                    "price": 1_000 if 10 <= hour <= 16 else 6_000,
                }
                for hour in range(24)
            ]
        )
        volumes = pd.DataFrame(
            [
                {"delivery_date": date(2026, 8, 19), "volume_mwh": 100},
                {"delivery_date": date(2026, 8, 21), "volume_mwh": 90},
            ]
        )

        result = build_price_driver_comparison(prices, volumes, date(2026, 8, 21))

        self.assertIsNotNone(result)
        self.assertEqual(result["previous_date"], date(2026, 8, 19))
        self.assertAlmostEqual(result["volume_change_percent"], -10)
        self.assertAlmostEqual(result["seven_day_average"], 8_000)
        self.assertEqual(result["seven_day_count"], 1)
        solar = result["segments"].set_index("Період").loc["Сонячні години"]
        self.assertEqual(solar["Поточна ціна"], 1_000)
        self.assertEqual(solar["Зміна, %"], -87.5)

    def test_returns_none_without_previous_day(self):
        prices = pd.DataFrame(
            [{"delivery_date": date(2026, 8, 21), "hour": 0, "price": 1_000}]
        )

        self.assertIsNone(
            build_price_driver_comparison(prices, pd.DataFrame(), date(2026, 8, 21))
        )

    def test_neighbor_change_uses_median_and_excludes_ukraine(self):
        rows = []
        for code, before, after in (
            ("UA", 100, 1_000),
            ("PL", 100, 110),
            ("SK", 200, 180),
        ):
            rows.extend(
                [
                    {"delivery_date": date(2026, 8, 20), "market_code": code, "price_eur": before},
                    {"delivery_date": date(2026, 8, 21), "market_code": code, "price_eur": after},
                ]
            )

        change = neighbor_daily_change(
            pd.DataFrame(rows), date(2026, 8, 21), date(2026, 8, 20)
        )

        self.assertAlmostEqual(change, 0.0)

    def test_aligns_hourly_prices_and_net_imports(self):
        prices = pd.DataFrame(
            [
                {"delivery_date": date(2026, 8, 20), "hour": 0, "price": 8_000},
                {"delivery_date": date(2026, 8, 21), "hour": 0, "price": 4_000},
            ]
        )
        flows = pd.DataFrame(
            [
                {
                    "delivery_date": date(2026, 8, 21),
                    "delivery_start": "2026-08-21T00:00:00+03:00",
                    "net_import_mwh": 100,
                },
                {
                    "delivery_date": date(2026, 8, 21),
                    "delivery_start": "2026-08-21T00:30:00+03:00",
                    "net_import_mwh": -25,
                },
            ]
        )

        result = build_hourly_price_flow_comparison(
            prices, flows, date(2026, 8, 21), date(2026, 8, 20)
        )

        self.assertEqual(result.iloc[0]["current_price"], 4_000)
        self.assertEqual(result.iloc[0]["previous_price"], 8_000)
        self.assertEqual(result.iloc[0]["net_import_mwh"], 75)

    def test_net_import_comparison_and_cautious_summary(self):
        flows = pd.DataFrame(
            [
                {"delivery_date": date(2026, 8, 20), "net_import_mwh": 100},
                {"delivery_date": date(2026, 8, 21), "net_import_mwh": 250},
            ]
        )
        flow_change = daily_net_import_comparison(
            flows, date(2026, 8, 21), date(2026, 8, 20)
        )
        comparison = {
            "absolute_change": -4_000,
            "percent_change": -50,
            "previous_date": date(2026, 8, 20),
            "seven_day_change_percent": -40,
            "seven_day_count": 7,
            "volume_change_percent": -10,
            "segments": pd.DataFrame(
                [{"Період": "Сонячні години", "Зміна, %": -70}]
            ),
        }

        summary = build_daily_explanation(comparison, -5, flow_change)

        self.assertEqual(flow_change["absolute_change_mwh"], 150)
        self.assertIn("Сонячні години", summary)
        self.assertIn("не доказ причинно-наслідкового", summary)

    def test_summary_handles_zero_comparison_base(self):
        summary = build_daily_explanation(
            {
                "absolute_change": 500,
                "percent_change": None,
                "previous_date": date(2026, 8, 20),
                "seven_day_change_percent": None,
                "seven_day_count": 1,
                "volume_change_percent": None,
                "segments": pd.DataFrame(
                    [{"Період": "Ніч", "Зміна, %": None}]
                ),
            }
        )

        self.assertIn("нульову базу", summary)

    def test_flow_price_relationship_finds_preceding_signal(self):
        hours = pd.date_range("2026-08-01", periods=72, freq="h", tz="Europe/Kyiv")
        imports = pd.Series(
            [((hour * 37) % 101) + ((hour % 7) * 3) for hour in range(72)],
            dtype=float,
        )
        aligned = pd.DataFrame(
            {
                "delivery_start": hours,
                "import_mwh": imports,
                "export_mwh": 10.0,
                "net_import_mwh": imports - 10.0,
                "price_eur": imports.shift(3),
            }
        )

        result = analyze_flow_price_relationship(aligned, max_lag_hours=6)

        net = result.set_index("factor").loc["Чистий імпорт"]
        self.assertEqual(net["strongest_lag_hours"], 3)
        self.assertAlmostEqual(net["strongest_correlation"], 1.0)
        summary = describe_flow_price_relationship(result)
        self.assertIn("через 3 год", summary)
        self.assertIn("не доказ", summary)

    def test_flow_price_relationship_rejects_short_or_constant_series(self):
        aligned = pd.DataFrame(
            {
                "price_eur": [100.0] * 10,
                "import_mwh": range(10),
                "export_mwh": range(10),
                "net_import_mwh": [0.0] * 10,
            }
        )

        result = analyze_flow_price_relationship(aligned)

        self.assertTrue(result.empty)
        self.assertIsNone(describe_flow_price_relationship(result))

    def test_dst_repeated_local_hour_aligns_as_two_utc_hours(self):
        repeated_hours = pd.to_datetime(
            ["2025-10-26T00:30:00Z", "2025-10-26T01:30:00Z"], utc=True
        ).tz_convert("Europe/Kyiv")
        prices = pd.DataFrame(
            {"delivery_start": repeated_hours, "price_eur": [100.0, 200.0]}
        )
        flows = pd.DataFrame(
            [
                {"delivery_start": timestamp, "direction": direction, "energy_mwh": value}
                for timestamp in repeated_hours
                for direction, value in (("Імпорт", 30.0), ("Експорт", 10.0))
            ]
        )

        result = align_hourly_flow_prices(prices, flows)

        self.assertEqual(len(result), 2)
        self.assertEqual(result["delivery_start"].nunique(), 2)
        self.assertEqual(result["net_import_mwh"].tolist(), [20.0, 20.0])


if __name__ == "__main__":
    unittest.main()
