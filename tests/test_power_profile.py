import tempfile
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from market_forecast.persistence import SQLiteMarketRepository
from market_forecast.sources.power_profile import monthly_sheet_name, parse_month_csv


CSV = """,01.10.2026,,,,,,,,,,,,02.10.2026\n,Замовлено ДЕЗ,Куплено ДЕЗ,ГПУ,СЕС,Віддали в мережу,Споживання технолог.,Споживання силової,сальдо небалансів,примітка,План продаж,Факт продаж,Небаланси продаж\n00:00 - 01:00,58,59,1,2,3,53,5,-1,0,0,0,0\n""" + "\n".join(
    f"{hour:02d}:00 - {hour + 1:02d}:00,58,59,1,2,3,53,5,-1,0,0,0,0"
    for hour in range(1, 24)
) + "\n" + "\n".join("," * 13 for _ in range(25))


class PowerProfileTests(unittest.TestCase):
    def test_parser_reads_hourly_daily_block(self):
        rows = parse_month_csv(CSV, date(2026, 10, 1), "жовтень 2026")
        self.assertEqual(len(rows), 24)
        self.assertEqual(rows[0].purchased_mwh, Decimal("59"))
        self.assertEqual(rows[-1].technology_consumption_mwh, Decimal("53"))

    def test_sheet_name(self):
        self.assertEqual(monthly_sheet_name(date(2026, 10, 1)), "жовтень 2026")

    def test_repository_upserts_profile(self):
        rows = parse_month_csv(CSV, date(2026, 10, 1), "жовтень 2026")
        with tempfile.TemporaryDirectory() as directory:
            repository = SQLiteMarketRepository(Path(directory) / "market.sqlite3")
            self.assertEqual(repository.store_power_profile(rows, datetime.now(timezone.utc)), 24)
            stored = repository.list_power_profile(date(2026, 10, 1), date(2026, 10, 1))
        self.assertEqual(len(stored), 24)
        self.assertEqual(stored[0][3], Decimal("59"))


if __name__ == "__main__":
    unittest.main()
