"""Parser for the monthly internal gas-price worksheets exported as CSV."""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from market_forecast.domain import GasConsumptionDay, GasProcurementMonth


def parse_gas_procurement_csv(
    content: bytes, reporting_month: date, source_sheet: str, *, include_days: bool = True,
) -> tuple[GasProcurementMonth, list[GasConsumptionDay]]:
    """Parse evaluated worksheet values without executing or trusting formulas."""

    if reporting_month.day != 1:
        raise ValueError("reporting_month must be the first day of a month")
    if not source_sheet.strip():
        raise ValueError("source_sheet must not be empty")
    text = _decode(content)
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 10:
        raise ValueError("Gas worksheet is too short")

    layout = _price_layout(rows)
    total = _value_beside(rows, "Всего, в т.ч", fallback=layout[0])
    commodity = _value_beside(rows, "цена газа", fallback=layout[1])
    distribution = layout[2]
    capacity = _value_beside(rows, "цена мощности", fallback=layout[3])
    calculated_total = commodity + distribution + capacity
    if abs(total - calculated_total) > Decimal("0.02"):
        raise ValueError("Gas price components do not match the total price")

    try:
        planned_month = _value_after_label(rows, "Заявленный Лимит по заводу")
    except ValueError:
        try:
            planned_month = _planned_month(rows)
        except ValueError:
            if include_days:
                raise
            # The price-only path never displays or persists daily consumption.
            # A legacy price tab can therefore be accepted without inventing a plan.
            planned_month = Decimal("0")
    month = GasProcurementMonth(
        reporting_month=reporting_month,
        commodity_price_uah_per_1000m3=commodity,
        distribution_price_uah_per_1000m3=distribution,
        capacity_price_uah_per_1000m3=capacity,
        total_price_uah_per_1000m3=total,
        planned_volume_m3=planned_month,
        vat_included=False,
        source_sheet=source_sheet,
    )
    if not include_days:
        return month, []
    daily: list[GasConsumptionDay] = []
    for row in rows:
        if not row:
            continue
        dated = _row_date(row)
        if dated is None:
            continue
        date_index, parsed_date = dated
        if parsed_date.year != reporting_month.year or parsed_date.month != reporting_month.month:
            raise ValueError("Daily row falls outside reporting_month")
        planned = _decimal(row[date_index + 1], "daily planned volume") if len(row) > date_index + 1 else None
        if planned is None:
            raise ValueError("Daily planned volume is missing")
        actual = _decimal(row[date_index + 2], "daily actual volume") if len(row) > date_index + 2 else None
        daily.append(GasConsumptionDay(parsed_date, planned, actual, source_sheet))
    if not daily:
        raise ValueError("Gas worksheet contains no daily rows")

    return month, daily


def _decode(content: bytes) -> str:
    if not content:
        raise ValueError("Gas worksheet export is empty")
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise ValueError("Gas worksheet export has unsupported encoding")


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _value_beside(
    rows: list[list[str]], label: str, fallback: Decimal | None = None
) -> Decimal:
    needle = _normalized(label)
    for row in rows[:12]:
        for index, cell in enumerate(row):
            if needle in _normalized(cell):
                for candidate in row[index + 1 :]:
                    value = _decimal(candidate, label)
                    if value is not None:
                        return value
    if fallback is not None:
        return fallback
    raise ValueError(f"Gas worksheet field is missing: {label}")


def _value_after_label(
    rows: list[list[str]], label: str, fallback: Decimal | None = None
) -> Decimal:
    return _value_beside(rows, label, fallback)


def _price_layout(rows: list[list[str]]) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Recover evaluated F-column values when merged labels vanish in CSV export."""

    header_rows: list[list[str]] = []
    for row in rows:
        if _row_date(row) is not None:
            break
        header_rows.append(row)
    width = max(map(len, header_rows), default=0)
    for column in range(width):
        values = [_decimal(row[column], "gas price component")
                  for row in header_rows if len(row) > column]
        numbers = [value for value in values if value is not None]
        if len(numbers) >= 4 and abs(numbers[0] - sum(numbers[1:4])) <= Decimal("0.02"):
            return numbers[0], numbers[1], numbers[2], numbers[3]
    raise ValueError("Gas worksheet price layout is incomplete")


def _planned_month(rows: list[list[str]]) -> Decimal:
    for row in rows:
        if _row_date(row) is not None:
            break
        if len(row) > 3:
            value = _decimal(row[3], "planned monthly volume")
            if value is not None:
                return value
    # Old gviz exports can omit labels and shift everything right. On the
    # commodity-price row the declared monthly limit is the numeric cell before
    # the commodity price; recover only that positional relationship.
    for row in rows:
        if _row_date(row) is not None:
            break
        values = [_decimal(cell, "planned monthly volume") for cell in row]
        numbers = [(index, value) for index, value in enumerate(values) if value is not None]
        if len(numbers) < 2:
            continue
        commodity_index, commodity = max(numbers, key=lambda item: item[1])
        if commodity < Decimal("1000"):
            continue
        preceding = [value for index, value in numbers if index < commodity_index]
        if preceding:
            return preceding[-1]
    raise ValueError("Gas worksheet planned monthly volume is missing")


def _decimal(value: object, field: str) -> Decimal | None:
    if value is None:
        return None
    cleaned = str(value).replace("\u00a0", "").replace(" ", "").replace(",", ".").strip()
    if not cleaned:
        return None
    try:
        result = Decimal(cleaned)
    except InvalidOperation:
        return None
    if not result.is_finite() or result < 0:
        raise ValueError(f"Invalid non-negative number for {field}")
    return result


def _date(value: str) -> date | None:
    value = value.strip()
    if not re.fullmatch(r"\d{2}\.\d{2}\.\d{2,4}", value):
        return None
    return datetime.strptime(value, "%d.%m.%y" if len(value) == 8 else "%d.%m.%Y").date()


def _row_date(row: list[str]) -> tuple[int, date] | None:
    """Locate the date column; some legacy CSV exports have a leading blank cell."""

    for index, value in enumerate(row):
        parsed = _date(value)
        if parsed is not None:
            return index, parsed
    return None
