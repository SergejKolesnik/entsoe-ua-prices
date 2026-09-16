"""Strict parser for daily commercial gas-consumption fact worksheets."""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import StringIO
import re

from market_forecast.domain import GasConsumptionDay


_REQUIRED_HEADERS = (
    "дата",
    "заявленный лимит цехами, м3",
    "коммерческий учет, м3 (факт)",
)


def parse_gas_consumption_fact_csv(
    content: bytes, reporting_month: date, source_sheet: str, *,
    total_tolerance_m3: Decimal = Decimal(0),
) -> list[GasConsumptionDay]:
    """Parse one complete month of verified commercial consumption facts.

    The worksheet's price fields are absent by design. Its approved daily limit
    is not used as a plan because the requested department limit is the direct
    comparable value beside the commercial-meter fact.
    """

    if reporting_month.day != 1:
        raise ValueError("reporting_month must be the first day of a month")
    if total_tolerance_m3 < 0:
        raise ValueError("total_tolerance_m3 must not be negative")
    if not source_sheet.strip():
        raise ValueError("source_sheet must not be empty")
    rows = list(csv.reader(StringIO(_decode(content)), strict=True))
    if len(rows) < 3:
        raise ValueError("Gas consumption fact worksheet is too short")
    header = rows[0]
    if len(header) < 4 or (
        _normalized(header[0]), _normalized(header[2]), _normalized(header[3])
    ) != _REQUIRED_HEADERS:
        raise ValueError("Gas consumption fact worksheet headers or units are unsupported")

    days: list[GasConsumptionDay] = []
    last_daily_row = 0
    for row_number, row in enumerate(rows[1:], start=2):
        if not row:
            continue
        delivery_date = _date(row[0])
        if delivery_date is None:
            continue
        if delivery_date.year != reporting_month.year or delivery_date.month != reporting_month.month:
            raise ValueError("Gas consumption fact row falls outside reporting_month")
        if len(row) < 4:
            raise ValueError(f"Gas consumption fact row {row_number} is incomplete")
        planned = _decimal(row[2], "requested daily volume")
        actual = _decimal(row[3], "commercial daily fact")
        days.append(GasConsumptionDay(delivery_date, planned, actual, source_sheet))
        last_daily_row = row_number - 1

    expected_days = _month_dates(reporting_month)
    if [item.delivery_date for item in days] != expected_days:
        raise ValueError("Gas consumption fact worksheet must contain every delivery date once in order")
    if last_daily_row + 1 >= len(rows):
        raise ValueError("Gas consumption fact monthly totals are missing")
    totals = rows[last_daily_row + 1]
    if len(totals) < 4:
        raise ValueError("Gas consumption fact monthly totals are incomplete")
    if _decimal(totals[2], "monthly requested total") != sum(item.planned_volume_m3 for item in days):
        raise ValueError("Gas consumption fact monthly requested total does not reconcile")
    commercial_difference = abs(
        _decimal(totals[3], "monthly commercial total")
        - sum(item.actual_volume_m3 for item in days)
    )
    if commercial_difference > total_tolerance_m3:
        raise ValueError("Gas consumption fact monthly commercial total does not reconcile")
    return days


def _decode(content: bytes) -> str:
    if not content:
        raise ValueError("Gas consumption fact worksheet is empty")
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise ValueError("Gas consumption fact worksheet has unsupported encoding")


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _decimal(value: str, field: str) -> Decimal:
    cleaned = value.replace("\xa0", "").replace(" ", "").replace(",", ".").strip()
    try:
        number = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Gas consumption fact has invalid {field}") from exc
    if not number.is_finite() or number < 0:
        raise ValueError(f"Gas consumption fact has invalid {field}")
    return number


def _date(value: str) -> date | None:
    candidate = value.strip()
    if not re.fullmatch(r"\d{2}\.\d{2}\.\d{2,4}", candidate):
        return None
    return datetime.strptime(candidate, "%d.%m.%y" if len(candidate) == 8 else "%d.%m.%Y").date()


def _month_dates(month: date) -> list[date]:
    next_month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    return [month + timedelta(days=offset) for offset in range((next_month - month).days)]
