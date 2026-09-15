import unittest
from datetime import date
from decimal import Decimal

from market_forecast.parsers import parse_operator_intraday_csv


HEADER = (
    "Дата;Година;Ціна, грн/МВт.год;Мінімальна ціна, грн/МВт.год;"
    "Максимальна ціна, грн/МВт.год;Остання ціна, грн/МВт.год;"
    "Обсяг продажу, МВт.год;Обсяг купівлі, МВт.год;"
    "Заявлений обсяг продажу, МВт.год;Заявлений обсяг купівлі, МВт.год"
)


def csv_for(day: str, count: int = 24) -> bytes:
    rows = [HEADER]
    for hour in range(1, count + 1):
        rows.append(f"{day};{hour};1500,25;1000;2000;1600;10,5;10,5;20;21")
    return ("\ufeff" + "\n".join(rows)).encode("utf-8")


def quarter_prefix_csv(year: int, quarter: int, days: int, skip_day: int | None = None) -> bytes:
    start = date(year, (quarter - 1) * 3 + 1, 1)
    documents = [HEADER]
    for offset in range(days):
        if offset == skip_day:
            continue
        delivery_day = start.fromordinal(start.toordinal() + offset).strftime("%d.%m.%Y")
        for hour in range(1, 25):
            documents.append(f"{delivery_day};{hour};1500,25;1000;2000;1600;10,5;10,5;20;21")
    return ("\ufeff" + "\n".join(documents)).encode("utf-8")


class OperatorIntradayCsvTests(unittest.TestCase):
    def test_parses_complete_official_day(self) -> None:
        results = parse_operator_intraday_csv(csv_for("18.08.2026"))

        self.assertEqual(len(results), 24)
        self.assertEqual(results[0].weighted_price_uah_per_mwh, Decimal("1500.25"))
        self.assertEqual(results[-1].settlement_period, 24)
        self.assertEqual(results[0].sale_volume_mwh, Decimal("10.5"))

    def test_accepts_spring_dst_day_with_23_periods(self) -> None:
        results = parse_operator_intraday_csv(csv_for("29.03.2026", 23))

        self.assertEqual(len(results), 23)

    def test_accepts_autumn_dst_day_with_25_periods(self) -> None:
        results = parse_operator_intraday_csv(csv_for("25.10.2026", 25))

        self.assertEqual(len(results), 25)
        self.assertEqual(results[-1].settlement_period, 25)

    def test_rejects_missing_or_duplicate_period(self) -> None:
        document = csv_for("18.08.2026").decode("utf-8").replace("18.08.2026;24;", "18.08.2026;23;")
        with self.assertRaisesRegex(ValueError, "periods 1-24"):
            parse_operator_intraday_csv(document.encode("utf-8"))

    def test_rejects_unexpected_header(self) -> None:
        document = csv_for("18.08.2026").replace(b"\xd0\x94\xd0\xb0\xd1\x82\xd0\xb0", b"Date", 1)
        with self.assertRaisesRegex(ValueError, "headers"):
            parse_operator_intraday_csv(document)

    def test_accepts_only_contiguous_partial_quarter_when_explicit(self) -> None:
        results = parse_operator_intraday_csv(quarter_prefix_csv(2026, 3, 2), 2026, 3, True)
        self.assertEqual(len(results), 48)
        with self.assertRaisesRegex(ValueError, "does not completely cover"):
            parse_operator_intraday_csv(quarter_prefix_csv(2026, 3, 2), 2026, 3)

    def test_rejects_partial_quarter_with_an_interior_gap(self) -> None:
        with self.assertRaisesRegex(ValueError, "contiguous prefix"):
            parse_operator_intraday_csv(quarter_prefix_csv(2026, 3, 3, skip_day=1), 2026, 3, True)

    def test_rejects_quarter_with_missing_delivery_dates(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not completely cover"):
            parse_operator_intraday_csv(csv_for("01.04.2026"), 2026, 2)
