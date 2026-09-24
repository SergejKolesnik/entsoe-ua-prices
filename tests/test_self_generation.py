import csv
import unittest
from io import StringIO

from market_forecast.sources.self_generation import parse_gpu_month_csv, parse_solar_month_csv


class SelfGenerationTests(unittest.TestCase):
    @staticmethod
    def _csv(rows):
        output = StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerows(rows)
        return output.getvalue()

    def test_parses_factual_solar_block(self):
        rows = [[""] * 32 for _ in range(4)]
        rows[0][1] = "ГЕНЕРАЦІЯ СЕС (ФАКТ)"
        rows[2][2] = "Дата"
        rows[3][2] = "1"
        rows[3][3] = "1.5"
        rows[3][4] = "2.5"
        rows[3][27] = "4.0"
        frame = parse_solar_month_csv(
            self._csv(rows), 2026, 9, "Вересень 26"
        )

        self.assertEqual(frame.loc[0, "delivery_date"].isoformat(), "2026-09-01")
        self.assertEqual(frame.loc[0, "solar_hour_00"], 1.5)
        self.assertEqual(frame.loc[0, "solar_total_kwh"], 4.0)

    def test_parses_gpu_daily_blocks(self):
        rows = [[""] * 30 for _ in range(45)]
        rows[15][7] = "1 вересня 2026"
        rows[16][7:12] = ["Генерація, МВт", "Собівартість", "", "якщо купили", "Економ. ефект"]
        rows[17][7:12] = ["", "Спожито газу, м3", "1 МВт", "Ціна РДН", ""]
        for hour in range(1, 25):
            rows[17 + hour][1] = str(hour)
            rows[17 + hour][7:12] = ["1.5", "2", "3", "4", "5"]
        frame = parse_gpu_month_csv(
            self._csv(rows), 2026, 9, "Вересень 2026"
        )

        self.assertEqual(frame.loc[0, "delivery_date"].isoformat(), "2026-09-01")
        self.assertEqual(frame.loc[0, "gpu_hour_00"], 1.5)
        self.assertEqual(frame.loc[0, "gpu_cost_hour_00"], 3.0)
        self.assertEqual(frame.loc[0, "gpu_economic_effect_hour_00"], 5.0)


if __name__ == "__main__":
    unittest.main()
