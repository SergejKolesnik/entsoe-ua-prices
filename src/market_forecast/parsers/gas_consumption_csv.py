"""Strict parser for the restored daily gas-consumption worksheets."""

from __future__ import annotations

import calendar
import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import StringIO
import re

from market_forecast.domain import GasConsumptionDay


def parse_gas_consumption_csv(content: bytes, reporting_month: date, source_sheet: str) -> list[GasConsumptionDay]:
    """Parse daily requested limits and commercial actuals without inferring values."""
    if reporting_month.day != 1 or not source_sheet.strip():
        raise ValueError("reporting_month must be first-of-month and source_sheet must be non-empty")
    text = _decode(content)
    rows = list(csv.reader(StringIO(text)))
    header_index, date_column, planned_column, actual_column = _columns(rows)
    result: list[GasConsumptionDay] = []
    for row in rows[header_index + 1:]:
        parsed = _row_date(row)
        if parsed is None:
            continue
        if parsed.replace(day=1) != reporting_month:
            raise ValueError("Daily row falls outside reporting_month")
        planned = _decimal(_cell(row, planned_column), "daily requested limit")
        actual = _decimal(_cell(row, actual_column), "daily commercial actual")
        if planned is None or actual is None:
            raise ValueError("Daily requested limit and commercial actual are required")
        result.append(GasConsumptionDay(parsed, planned * 1000, actual * 1000, source_sheet))
    expected = {date(reporting_month.year, reporting_month.month, day)
                for day in range(1, calendar.monthrange(reporting_month.year, reporting_month.month)[1] + 1)}
    actual_dates = {item.delivery_date for item in result}
    if len(result) != len(actual_dates) or actual_dates != expected:
        raise ValueError("Daily gas consumption must contain each calendar day exactly once")
    return result


def _columns(rows: list[list[str]]) -> tuple[int, int, int, int]:
    for index, row in enumerate(rows):
        names = [_normal(cell) for cell in row]
        try:
            date_column = next(i for i, value in enumerate(names) if value == "дата")
            planned_column = next(i for i, value in enumerate(names)
                                  if "заявлен" in value and "лимит" in value)
            actual_column = next(i for i, value in enumerate(names)
                                 if "коммерческ" in value and "учет" in value)
        except StopIteration:
            continue
        return index, date_column, planned_column, actual_column
    # Some 2022 CSV exports collapse the header into a title row. Their verified
    # daily layout remains date, approved limit, requested limit, commercial actual.
    for index, row in enumerate(rows):
        for date_column, value in enumerate(row):
            if re.fullmatch(r"\d{2}\.\d{2}\.\d{2,4}", value.strip()):
                return index - 1, date_column, date_column + 2, date_column + 3
    raise ValueError("Gas consumption worksheet lacks date, requested-limit, or commercial-actual header")


def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise ValueError("Gas consumption worksheet has unsupported encoding")


def _normal(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _row_date(row: list[str]) -> date | None:
    for value in row:
        value = value.strip()
        if re.fullmatch(r"\d{2}\.\d{2}\.\d{2,4}", value):
            return datetime.strptime(value, "%d.%m.%y" if len(value) == 8 else "%d.%m.%Y").date()
    return None


def _cell(row: list[str], column: int) -> str:
    return row[column] if column < len(row) else ""


def _decimal(value: str, field: str) -> Decimal | None:
    cleaned = value.replace("\u00a0", "").replace(" ", "").replace(",", ".").strip()
    if not cleaned:
        return None
    try:
        number = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid {field}") from exc
    if not number.is_finite() or number < 0:
        raise ValueError(f"Invalid {field}")
    return number
