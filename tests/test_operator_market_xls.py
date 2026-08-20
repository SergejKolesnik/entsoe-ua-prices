import unittest
from datetime import date
from decimal import Decimal

from market_forecast.parsers import parse_operator_market_rows


def make_rows(count: int = 24) -> list[list[str]]:
    rows = [["Period", "DAM price", "Buy volume", "Sell volume"]]
    for period in range(1, count + 1):
        rows.append([f"{period:02d}:00", f"{period} 500,25", "100,0", "100,0"])
    return rows


class OperatorMarketXlsParserTests(unittest.TestCase):
    def test_parses_localized_hourly_prices(self):
        records = parse_operator_market_rows(make_rows(), date(2026, 8, 18))

        self.assertEqual(len(records), 24)
        self.assertEqual(records[0].price, Decimal("1500.25"))
        self.assertEqual(records[-1].price, Decimal("24500.25"))
        self.assertEqual(records[0].currency, "UAH")
        self.assertEqual(records[0].source, "operator_market")
        self.assertEqual(records[-1].settlement_period, 24)
        self.assertEqual(records[0].volume_mwh, Decimal("100.0"))

    def test_rejects_different_purchase_and_sale_volumes(self):
        rows = make_rows()
        rows[1][3] = "99,9"

        with self.assertRaisesRegex(ValueError, "purchase and sale volumes differ"):
            parse_operator_market_rows(rows, date(2026, 8, 18))

    def test_rejects_missing_period(self):
        with self.assertRaisesRegex(ValueError, "Expected 24.*received 23"):
            parse_operator_market_rows(make_rows(23), date(2026, 8, 18))

    def test_rejects_invalid_price(self):
        rows = make_rows()
        rows[7][1] = "not-a-price"

        with self.assertRaisesRegex(ValueError, "period 7"):
            parse_operator_market_rows(rows, date(2026, 8, 18))

    def test_uses_23_periods_on_kyiv_spring_dst_day(self):
        records = parse_operator_market_rows(make_rows(23), date(2026, 3, 29))

        self.assertEqual(len(records), 23)


if __name__ == "__main__":
    unittest.main()
