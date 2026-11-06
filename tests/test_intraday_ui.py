"""Selection rules for the VDR hourly comparison."""

from datetime import date
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

import streamlit_app as app


class IntradayUiTests(unittest.TestCase):
    def test_completed_day_quick_choices_are_bounded_by_available_dates(self) -> None:
        available = [date(2026, 9, 13), date(2026, 9, 14), date(2026, 9, 15)]
        self.assertEqual(available[-1], date(2026, 9, 15))
        self.assertIn(date(2026, 9, 14), available)

    def test_uses_requested_date_when_available(self) -> None:
        self.assertEqual(
            app._nearest_intraday_date([date(2026, 9, 13), date(2026, 9, 14)], date(2026, 9, 14)),
            date(2026, 9, 14),
        )

    def test_uses_nearest_available_date_and_prefers_earlier_on_a_tie(self) -> None:
        self.assertEqual(
            app._nearest_intraday_date([date(2026, 9, 13), date(2026, 9, 15)], date(2026, 9, 14)),
            date(2026, 9, 13),
        )

    def test_rejects_empty_coverage(self) -> None:
        with self.assertRaisesRegex(ValueError, "At least one"):
            app._nearest_intraday_date([], date(2026, 9, 14))

    def test_power_profile_ignores_rows_for_unfilled_future_day(self) -> None:
        rows = []
        for delivery_date in (date(2026, 10, 19), date(2026, 10, 20)):
            for hour in range(24):
                complete = delivery_date == date(2026, 10, 19)
                rows.append({
                    "delivery_date": delivery_date,
                    "hour": hour,
                    "planned_purchase_mwh": 12 if complete else None,
                    "purchased_mwh": 10 if complete else None,
                    "technology_consumption_mwh": 6 if complete else None,
                    "power_consumption_mwh": 8 if complete else None,
                    "grid_export_mwh": 1 if complete else None,
                    "imbalance_mwh": 0 if complete else None,
                })

        dates = app._complete_power_profile_dates(pd.DataFrame(rows), date(2026, 10, 20))

        self.assertEqual(dates, [date(2026, 10, 19)])

    def test_power_profile_requires_complete_requested_balance_fields(self) -> None:
        rows = [{
            "delivery_date": date(2026, 10, 19),
            "hour": hour,
            "planned_purchase_mwh": 12,
            "purchased_mwh": 10,
            "technology_consumption_mwh": 6 if hour != 7 else None,
            "power_consumption_mwh": 8,
            "grid_export_mwh": 1,
            "imbalance_mwh": 0,
        } for hour in range(24)]

        dates = app._complete_power_profile_dates(pd.DataFrame(rows), date(2026, 10, 20))

        self.assertEqual(dates, [])

    def test_power_profile_draws_physical_balance_and_procurement_charts(self) -> None:
        profile_date = date(2026, 11, 2)
        rows = [{
            "delivery_date": profile_date,
            "hour": hour,
            "planned_purchase_mwh": 9.0,
            "purchased_mwh": 8.0,
            "gpu_mwh": 2.0,
            "ses_mwh": 1.0,
            "grid_export_mwh": 1.0,
            "technology_consumption_mwh": 6.0,
            "power_consumption_mwh": 4.0,
            "imbalance_mwh": 0.1 if hour % 2 else -0.1,
            "source_sheet": "листопад 2026",
            "imported_at_utc": None,
        } for hour in range(24)]
        fake_streamlit = Mock()
        fake_streamlit.session_state = {}
        column_batches = []

        def make_columns(spec):
            columns = [Mock(button=Mock(return_value=False))
                       for _ in range(spec if isinstance(spec, int) else len(spec))]
            if isinstance(spec, list):
                columns[2].selectbox.return_value = profile_date
            column_batches.append(columns)
            return columns

        fake_streamlit.columns.side_effect = make_columns

        with patch.object(app, "st", fake_streamlit), patch.object(
            app, "_load_power_profile", return_value=pd.DataFrame(rows)
        ):
            app._draw_power_profile(
                Path("unused.sqlite"), date(2026, 11, 1), date(2026, 11, 5), profile_date
            )

        charts = [call.args[0] for call in fake_streamlit.plotly_chart.call_args_list]
        self.assertEqual(len(charts), 2)
        self.assertEqual(
            [trace.name for trace in charts[0].data],
            ["Споживання технологічне", "Споживання силове", "Куплено з мережі",
             "Генерація ГПУ", "Генерація СЕС", "Віддали в мережу"],
        )
        self.assertTrue(all(value == -1.0 for value in charts[0].data[-1].y))
        self.assertEqual(
            [trace.name for trace in charts[1].data],
            ["Сальдо небалансів", "Замовлено ДЕЗ", "Куплено ДЕЗ"],
        )
        self.assertEqual(column_batches[1][0].metric.call_args.args, ("Повне споживання · МВт·год", "240,0"))
        self.assertEqual(column_batches[1][3].metric.call_args.args, ("Сальдо небалансів · МВт·год", "+0,00"))
