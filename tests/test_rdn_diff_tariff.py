import unittest

from market_forecast.sources.rdn_diff_tariff import add_aggregates, parse_month_csv


class RdnDiffTariffTests(unittest.TestCase):
    def test_parses_hourly_rdn_and_daily_weighted_price(self):
        rows = ["" for _ in range(16)]
        rows.append(",".join(["01", "вт", *["100" for _ in range(24)], "100", "", "80", "20%" ]))
        frame = parse_month_csv("\n".join(rows), 2026, 9, "РДН-Вересень 2026")

        self.assertEqual(frame.loc[0, "delivery_date"].isoformat(), "2026-09-01")
        self.assertEqual(frame.loc[0, "rdn_hour_00"], 100)
        self.assertEqual(frame.loc[0, "rdn_daily"], 100)
        self.assertEqual(frame.loc[0, "weighted_nzf"], 80)
        self.assertAlmostEqual(frame.loc[0, "diff_tariff_pct_source"], 0.20)

    def test_aggregates_keep_missing_days_explicit(self):
        rows = ["" for _ in range(16)]
        rows.extend([
            ",".join(["01", "вт", *["100" for _ in range(24)], "100", "", "80", "20%"]),
            ",".join(["02", "ср", *["200" for _ in range(24)], "200", "", "", ""]),
        ])
        daily, monthly = add_aggregates(parse_month_csv("\n".join(rows), 2026, 9, "РДН-Вересень 2026"))

        self.assertAlmostEqual(float(daily.loc[0, "saving_pct"]), 0.20)
        self.assertTrue(daily.loc[1, "saving_pct"] != daily.loc[1, "saving_pct"])
        self.assertEqual(monthly.loc[0, "days"], 2)


if __name__ == "__main__":
    unittest.main()
