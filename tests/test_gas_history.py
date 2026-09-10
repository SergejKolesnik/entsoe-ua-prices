"""Annual history parsing, atomic persistence, coverage and UI regressions."""

import csv
from contextlib import closing
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_forecast.cli import main
from market_forecast.parsers.gas_history_csv import HEADERS, MONTHS, parse_gas_history_csv
from market_forecast.persistence import SQLiteMarketRepository
from market_forecast.services.gas_consumption import monthly_consumption
from market_forecast.sources.base import RawResponse

URL = "https://docs.google.com/spreadsheets/d/synthetic/gviz/tq?sheet=2023"
NOW = datetime(2026, 9, 9, tzinfo=timezone.utc)


def fixture():
    """Create a wholly synthetic twelve-month source, including small real-scale volumes."""
    rows = [["", 'ПРИРОДНЫЙ ГАЗ 2023 год  (Поставщик TEST)'], [], ["", *HEADERS]]
    for name in MONTHS:
        rows.append(["", name, "100", "5", "15", "120", "1.2", "0.00055", "1.20055", "144.066"])
    rows.append(["", "ГОД", "", "", "", "", "14.4", "0.0066", "14.4066", "1728.792"])
    return rows


def encode(rows):
    stream = StringIO()
    csv.writer(stream).writerows(rows)
    return stream.getvalue().encode()


class GasHistoryTests(unittest.TestCase):
    def test_native_vat_and_small_volumes_preserved(self):
        rows = parse_gas_history_csv(encode(fixture()), 2023)
        self.assertEqual(len(rows), 12)
        self.assertEqual(rows[0].sanatorium_volume_m3, Decimal("0.55"))
        self.assertEqual(rows[0].total_volume_m3, Decimal("1200.55"))
        self.assertEqual(rows[0].total_price, Decimal("120"))

    def test_gviz_collapsed_header(self):
        rows = fixture()
        rows[2][1] = rows[0][1] + " Месяц"
        del rows[:2]
        self.assertEqual(len(parse_gas_history_csv(encode(rows), 2023)), 12)

    def test_reject_wrong_year_units_missing_duplicate_and_arithmetic(self):
        mutations = [(2, 3, 'тариф без НДС'), (3, 1, 'февраль'), (3, 2, 'NaN'),
                     (3, 2, '-1'), (3, 2, ''), (3, 5, '121'), (3, 8, '1.3'),
                     (3, 9, '150'), (15, 6, '99')]
        for row, col, value in mutations:
            with self.subTest(value=value):
                rows = fixture(); rows[row][col] = value
                with self.assertRaises(ValueError):
                    parse_gas_history_csv(encode(rows), 2023)
        for rows in (fixture()[:-1], fixture() + [fixture()[3]]):
            with self.assertRaises(ValueError):
                parse_gas_history_csv(encode(rows), 2023)
        with self.assertRaises(ValueError):
            parse_gas_history_csv(encode(fixture()), 2024)

    def test_idempotent_import_and_transaction_rollback(self):
        rows = parse_gas_history_csv(encode(fixture()), 2023)
        with tempfile.TemporaryDirectory() as temp:
            repo = SQLiteMarketRepository(Path(temp) / 'test.sqlite3')
            # A preexisting December conflict must roll back the preceding eleven inserts.
            repo.initialize()
            with closing(repo._connect()) as conn, conn:
                conn.execute("INSERT INTO gas_monthly_history VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             ('2023-12-01', '100', '5', '15', '120', '999', '1', '1000', '120', True, URL, '2023', 'a'*64, NOW.isoformat()))
            with self.assertRaisesRegex(ValueError, 'Conflicting'):
                repo.store_gas_history(rows, URL, '2023', 'b'*64, NOW)
            self.assertEqual(len(repo.list_gas_history()), 1)
            clean = SQLiteMarketRepository(Path(temp) / 'clean.sqlite3')
            self.assertEqual(clean.store_gas_history(rows, URL, '2023', 'b'*64, NOW), 12)
            self.assertEqual(clean.store_gas_history(rows, URL, '2023', 'c'*64, NOW), 0)
            self.assertEqual(clean.list_gas_history()[0][6], Decimal('0.55'))
            self.assertEqual(clean.list_gas_consumption_days(), [])
            self.assertEqual(clean.list_gas_procurement_months(), [])

    def test_monthly_aggregation_no_double_count_and_missing_is_not_zero(self):
        history = [(date(2023, 1, 1), None, None, None, None, Decimal('1200'), Decimal('.55'), Decimal('1200.55'))]
        days = [(date(2023, 1, 1), Decimal(100), Decimal(9999)),
                (date(2024, 1, 1), Decimal(100), None),
                (date(2024, 2, 1), Decimal(100), Decimal(0))]
        rows = monthly_consumption(history, days)
        self.assertEqual(rows[0]['plant_volume_m3'], Decimal('1200'))
        self.assertIsNone(rows[1]['plant_volume_m3'])
        self.assertEqual(rows[2]['plant_volume_m3'], Decimal(0))
        self.assertIsNone(rows[2]['sanatorium_volume_m3'])
        self.assertEqual(rows[2]['coverage'], 'Неповні добові дані')
        feb = [(date(2024, 2, d), None, Decimal(1)) for d in range(1, 30)]
        self.assertEqual(monthly_consumption([], feb)[0]['coverage'], 'Повний добовий факт')

    def test_dry_run_does_not_open_repository(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {
            'GAS_SPREADSHEET_ID': 'synthetic', 'RAW_DATA_DIRECTORY': temp,
        }), patch('market_forecast.sources.GoogleSheetsGasSource.fetch_worksheet',
                  return_value=RawResponse(encode(fixture()), 'text/csv', 200, URL)), \
                patch('market_forecast.persistence.create_market_repository') as create:
            self.assertEqual(main(['import-gas-year', '--year', '2023', '--sheet', '2023']), 0)
            create.assert_not_called()
            self.assertEqual(len(list(Path(temp).rglob('*.csv'))), 1)

    def test_history_only_ui_exposes_twelve_months_and_exact_small_volume(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'ui.sqlite3'
            repo = SQLiteMarketRepository(path)
            repo.store_gas_history(parse_gas_history_csv(encode(fixture()), 2023), URL, '2023', 'a'*64, NOW)
            script = (
                'from pathlib import Path\n'
                'from market_forecast.persistence import SQLiteMarketRepository\n'
                'from unittest.mock import patch\n'
                'import streamlit_app as app\n'
                f'with patch.object(app, "_repository", lambda _: SQLiteMarketRepository(Path({str(path)!r}))):\n'
                f'    app._draw_gas_market({str(path)!r})\n'
            )
            app = AppTest.from_string(script).run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.selectbox[0].options), 12)
            self.assertEqual(len(app.dataframe[0].value), 12)
            self.assertEqual(app.metric[1].value, '0.55 м³')
            app.selectbox[0].set_value(date(2023, 1, 1)).run()
            self.assertEqual(len(app.exception), 0)
