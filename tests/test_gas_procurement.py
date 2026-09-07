import tempfile
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from market_forecast.parsers import parse_gas_procurement_csv
from market_forecast.persistence import SQLiteMarketRepository
from market_forecast.sources import GoogleSheetsGasSource


CSV = '''"Потребление природного газа по промплощадке завода в сентябре 2026г."

,,,,"Всего, в т.ч:","23053,83","грн. за 1 000 куб.м без НДС"
"Заявленный Лимит по заводу:",,,310000,"цена газа:","19041,66"
,,,,,"552,17"
"Среднесуточный Лимит:",,,"10333,33","цена мощности (бронирования) :","3460,00"

Дата,"Заявленный среднесуточный лимит, куб.м","Фактический расход, куб.м"

01.09.26,10333,"676,6"
02.09.26,10333,"2758,0"
03.09.26,10333,
'''.encode("utf-8")


class GasProcurementTests(unittest.TestCase):
    def test_parser_separates_commodity_and_delivery_components(self):
        month, days = parse_gas_procurement_csv(
            CSV, date(2026, 9, 1), "9 ціна газу у вересні 26"
        )

        self.assertEqual(month.commodity_price_uah_per_1000m3, Decimal("19041.66"))
        self.assertEqual(month.distribution_price_uah_per_1000m3, Decimal("552.17"))
        self.assertEqual(month.capacity_price_uah_per_1000m3, Decimal("3460.00"))
        self.assertEqual(month.total_price_uah_per_1000m3, Decimal("23053.83"))
        self.assertFalse(month.vat_included)
        self.assertEqual(len(days), 3)
        self.assertEqual(days[0].actual_volume_m3, Decimal("676.6"))
        self.assertIsNone(days[-1].actual_volume_m3)

    def test_parser_rejects_rows_from_another_month(self):
        content = CSV.replace(b"03.09.26", b"03.10.26")
        with self.assertRaisesRegex(ValueError, "outside reporting_month"):
            parse_gas_procurement_csv(content, date(2026, 9, 1), "sheet")

    def test_parser_handles_merged_labels_omitted_by_google_csv(self):
        text = CSV.decode("utf-8")
        for label in (
            '"Всего, в т.ч:"',
            '"Заявленный Лимит по заводу:"',
            '"цена газа:"',
            '"цена мощности (бронирования) :"',
        ):
            text = text.replace(label, "")
        content = text.encode("utf-8")

        month, days = parse_gas_procurement_csv(
            content, date(2026, 9, 1), "live-layout"
        )

        self.assertEqual(month.planned_volume_m3, Decimal("310000"))
        self.assertEqual(month.total_price_uah_per_1000m3, Decimal("23053.83"))
        self.assertEqual(len(days), 3)

    def test_source_is_read_only_and_rejects_non_csv_login_page(self):
        response = Mock(
            status_code=200,
            content=b"login",
            headers={"Content-Type": "text/html"},
        )
        response.raise_for_status.return_value = None
        with patch("market_forecast.sources.google_sheets_gas.requests.get", return_value=response) as get:
            with self.assertRaisesRegex(ValueError, "check read access"):
                GoogleSheetsGasSource("abc_123").fetch_worksheet("Газ вересень")
        self.assertEqual(get.call_args.args[0].split("?")[0], "https://docs.google.com/spreadsheets/d/abc_123/gviz/tq")

    def test_repository_upserts_mutable_month_and_preserves_null_actuals(self):
        month, days = parse_gas_procurement_csv(CSV, date(2026, 9, 1), "sheet")
        with tempfile.TemporaryDirectory() as directory:
            repository = SQLiteMarketRepository(Path(directory) / "market.sqlite3")
            repository.store_gas_procurement(month, days, datetime(2026, 9, 7, tzinfo=timezone.utc))
            repository.store_gas_procurement(month, days, datetime(2026, 9, 8, tzinfo=timezone.utc))

            stored = repository.list_gas_procurement_months()
            stored_days = repository.list_gas_consumption_days(
                date(2026, 9, 2), date(2026, 9, 3)
            )

        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0][0], date(2026, 9, 1))
        self.assertEqual(stored[0][1], Decimal("19041.66"))
        self.assertEqual(stored[0][-1], datetime(2026, 9, 8, tzinfo=timezone.utc))
        self.assertEqual([row[0] for row in stored_days], [date(2026, 9, 2), date(2026, 9, 3)])
        self.assertEqual(stored_days[0][2], Decimal("2758.0"))
        self.assertIsNone(stored_days[1][2])


if __name__ == "__main__":
    unittest.main()
