"""Strict parser for quarterly CSV results of the Ukrainian intraday market."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO
from zoneinfo import ZoneInfo

from market_forecast.domain import IntradayMarketResult


EXPECTED_HEADERS = (
    "Дата", "Година", "Ціна, грн/МВт.год", "Мінімальна ціна, грн/МВт.год",
    "Максимальна ціна, грн/МВт.год", "Остання ціна, грн/МВт.год",
    "Обсяг продажу, МВт.год", "Обсяг купівлі, МВт.год",
    "Заявлений обсяг продажу, МВт.год", "Заявлений обсяг купівлі, МВт.год",
)


def parse_operator_intraday_csv(
    content: bytes, expected_year: int | None = None, expected_quarter: int | None = None,
) -> list[IntradayMarketResult]:
    """Parse an official quarterly VDR CSV without filling missing delivery hours."""

    if (expected_year is None) != (expected_quarter is None):
        raise ValueError("Expected intraday year and quarter must be supplied together")
    if expected_quarter is not None and expected_quarter not in (1, 2, 3, 4):
        raise ValueError("Expected intraday quarter must be between 1 and 4")
    if not content:
        raise ValueError("Operator intraday CSV is empty")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Operator intraday CSV must be UTF-8") from exc
    rows = list(csv.reader(StringIO(text), delimiter=";"))
    if len(rows) < 2:
        raise ValueError("Operator intraday CSV has no result rows")
    header = tuple(cell.strip() for cell in rows[0])
    if header != EXPECTED_HEADERS:
        raise ValueError("Operator intraday CSV headers do not match the official contract")

    by_date: dict[date, list[IntradayMarketResult]] = defaultdict(list)
    kyiv = ZoneInfo("Europe/Kyiv")
    for row_number, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) != len(EXPECTED_HEADERS):
            raise ValueError(f"Operator intraday CSV row {row_number} has an unexpected column count")
        try:
            delivery_date = datetime.strptime(row[0].strip(), "%d.%m.%Y").date()
        except ValueError as exc:
            raise ValueError(f"Operator intraday CSV row {row_number} has an invalid delivery date") from exc
        period = _period(row[1], row_number)
        start = datetime.combine(delivery_date, time.min, kyiv).astimezone(timezone.utc)
        delivery_start = start + timedelta(hours=period - 1)
        values = [_decimal(value, row_number) for value in row[2:]]
        by_date[delivery_date].append(IntradayMarketResult(
            delivery_start_utc=delivery_start,
            delivery_end_utc=delivery_start + timedelta(hours=1),
            settlement_period=period,
            weighted_price_uah_per_mwh=values[0],
            minimum_price_uah_per_mwh=values[1],
            maximum_price_uah_per_mwh=values[2],
            last_price_uah_per_mwh=values[3],
            sale_volume_mwh=values[4],
            purchase_volume_mwh=values[5],
            declared_sale_volume_mwh=values[6],
            declared_purchase_volume_mwh=values[7],
        ))

    if not by_date:
        raise ValueError("Operator intraday CSV has no result rows")
    records: list[IntradayMarketResult] = []
    for delivery_date, daily_rows in sorted(by_date.items()):
        daily_rows.sort(key=lambda result: result.settlement_period)
        expected_periods = _expected_periods(delivery_date)
        periods = [result.settlement_period for result in daily_rows]
        if periods != list(range(1, expected_periods + 1)):
            raise ValueError(
                f"Operator intraday results for {delivery_date} must contain "
                f"periods 1-{expected_periods} exactly once"
            )
        records.extend(daily_rows)
    if expected_year is not None and expected_quarter is not None:
        _validate_quarter_dates(by_date, expected_year, expected_quarter)
    return records


def _validate_quarter_dates(
    by_date: dict[date, list[IntradayMarketResult]], year: int, quarter: int
) -> None:
    quarter_start = date(year, (quarter - 1) * 3 + 1, 1)
    quarter_end = (
        date(year + 1, 1, 1) if quarter == 4
        else date(year, quarter * 3 + 1, 1)
    ) - timedelta(days=1)
    expected_dates = [quarter_start + timedelta(days=offset)
                      for offset in range((quarter_end - quarter_start).days + 1)]
    if sorted(by_date) != expected_dates:
        raise ValueError(
            f"Operator intraday CSV does not completely cover {year} quarter {quarter}"
        )


def _expected_periods(delivery_date: date) -> int:
    kyiv = ZoneInfo("Europe/Kyiv")
    start = datetime.combine(delivery_date, time.min, kyiv).astimezone(timezone.utc)
    end = datetime.combine(delivery_date + timedelta(days=1), time.min, kyiv).astimezone(timezone.utc)
    return int((end - start).total_seconds() // 3600)


def _period(value: str, row_number: int) -> int:
    try:
        period = int(value.strip())
    except ValueError as exc:
        raise ValueError(f"Operator intraday CSV row {row_number} has an invalid hour") from exc
    if period < 1:
        raise ValueError(f"Operator intraday CSV row {row_number} has an invalid hour")
    return period


def _decimal(value: str, row_number: int) -> Decimal:
    try:
        return Decimal(value.strip().replace("\u00a0", "").replace(" ", "").replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError(f"Operator intraday CSV row {row_number} has an invalid numeric value") from exc
