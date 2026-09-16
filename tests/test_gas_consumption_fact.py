"""Commercial gas-consumption fact worksheet parsing and persistence."""

import csv
from datetime import date, datetime, timezone
from decimal import Decimal
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_forecast.cli import main
from market_forecast.parsers import parse_gas_consumption_fact_csv
from market_forecast.persistence import SQLiteMarketRepository
from market_forecast.sources.base import RawResponse

URL = "https://docs.google.com/spreadsheets/d/synthetic/gviz/tq?sheet=fact"
NOW = datetime(2026, 9, 16, tzinfo=timezone.utc)


def fixture():
    rows = [["Дата", "Затверджений ліміт", "Заявленный лимит цехами, м3", "Коммерческий учет, м3 (факт)"]]
    for day in range(1, 31):
        rows.append([f"{day:02d}.09.25", "1267", "1000", "1100"])
    rows.append(["", "", "30000", "33000"])
    stream = StringIO()
    csv.writer(stream).writerows(rows)
    return stream.getvalue().encode()


class GasConsumptionFactTests(unittest.TestCase):
    def test_parses_complete_month_and_reconciles_totals(self) -> None:
        days = parse_gas_consumption_fact_csv(fixture(), date(2025, 9, 1), "9 факт вересень 25")
        self.assertEqual(len(days), 30)
        self.assertEqual(days[0].planned_volume_m3, Decimal("1000"))
        self.assertEqual(days[-1].actual_volume_m3, Decimal("1100"))

    def test_rejects_missing_day_or_bad_monthly_total(self) -> None:
        rows = list(csv.reader(StringIO(fixture().decode())))
        for mutate in (
            lambda data: data.pop(10),
            lambda data: data[-1].__setitem__(3, "33001"),
        ):
            with self.subTest(mutate=mutate):
                copy = [row[:] for row in rows]
                mutate(copy)
                stream = StringIO(); csv.writer(stream).writerows(copy)
                with self.assertRaises(ValueError):
                    parse_gas_consumption_fact_csv(stream.getvalue().encode(), date(2025, 9, 1), "fact")

    def test_allows_only_explicit_small_commercial_total_difference(self) -> None:
        rows = list(csv.reader(StringIO(fixture().decode())))
        rows[-1][3] = "33003"
        stream = StringIO(); csv.writer(stream).writerows(rows)
        with self.assertRaisesRegex(ValueError, "commercial total"):
            parse_gas_consumption_fact_csv(stream.getvalue().encode(), date(2025, 9, 1), "fact")
        days = parse_gas_consumption_fact_csv(
            stream.getvalue().encode(), date(2025, 9, 1), "fact", total_tolerance_m3=Decimal("3"),
        )
        self.assertEqual(sum(item.actual_volume_m3 for item in days), Decimal("33000"))

    def test_price_free_persistence_upserts_daily_facts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = SQLiteMarketRepository(Path(temp) / "facts.sqlite3")
            days = parse_gas_consumption_fact_csv(fixture(), date(2025, 9, 1), "fact")
            self.assertEqual(repo.store_gas_consumption_days(days, NOW), 30)
            self.assertEqual(len(repo.list_gas_procurement_months()), 0)
            self.assertEqual(len(repo.list_gas_consumption_days(date(2025, 9, 1), date(2025, 9, 30))), 30)

    def test_dry_run_does_not_open_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {
            'GAS_SPREADSHEET_ID': 'synthetic', 'RAW_DATA_DIRECTORY': temp,
        }), patch('market_forecast.sources.GoogleSheetsGasSource.fetch_worksheet',
                  return_value=RawResponse(fixture(), 'text/csv', 200, URL)), \
                patch('market_forecast.persistence.create_market_repository') as create:
            self.assertEqual(main([
                'import-gas-fact-sheet', '--month', '2025-09-01', '--sheet', '9 факт вересень 25',
            ]), 0)
            create.assert_not_called()
