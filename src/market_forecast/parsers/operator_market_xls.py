"""Parser for legacy XLS workbooks published by the Ukrainian Market Operator."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Sequence
from zoneinfo import ZoneInfo

import xlrd

from market_forecast.domain import HourlyMarketPrice


def parse_operator_market_workbook(
    content: bytes,
    delivery_date: date,
) -> list[HourlyMarketPrice]:
    """Read the first worksheet and normalize its hourly DAM price column."""

    if not content:
        raise ValueError("Market Operator workbook is empty")
    try:
        workbook = xlrd.open_workbook(
            file_contents=content,
            ignore_workbook_corruption=True,
        )
    except (xlrd.XLRDError, xlrd.compdoc.CompDocError) as exc:
        raise ValueError("Market Operator workbook cannot be read") from exc
    if workbook.nsheets != 1:
        raise ValueError("Expected exactly one Market Operator worksheet")
    sheet = workbook.sheet_by_index(0)
    rows = [sheet.row_values(index) for index in range(sheet.nrows)]
    return parse_operator_market_rows(rows, delivery_date)


def parse_operator_market_rows(
    rows: Sequence[Sequence[object]],
    delivery_date: date,
) -> list[HourlyMarketPrice]:
    """Normalize extracted worksheet rows without relying on damaged header text."""

    if len(rows) < 2:
        raise ValueError("Market Operator worksheet has no hourly rows")
    header = rows[0]
    if len(header) < 2:
        raise ValueError("Market Operator worksheet has no price column")

    kyiv = ZoneInfo("Europe/Kyiv")
    delivery_start = datetime.combine(delivery_date, time.min, kyiv).astimezone(timezone.utc)
    delivery_end = datetime.combine(
        delivery_date + timedelta(days=1), time.min, kyiv
    ).astimezone(timezone.utc)
    expected_periods = int((delivery_end - delivery_start).total_seconds() // 3600)
    hourly_rows = [row for row in rows[1:] if row and str(row[0]).strip()]
    if len(hourly_rows) != expected_periods:
        raise ValueError(
            f"Expected {expected_periods} Market Operator periods, "
            f"received {len(hourly_rows)}"
        )

    records: list[HourlyMarketPrice] = []
    for index, row in enumerate(hourly_rows, start=1):
        if len(row) < 2:
            raise ValueError(f"Market Operator period {index} has no price value")
        label = str(row[0]).strip()
        if not label:
            raise ValueError(f"Market Operator period {index} has no period label")
        price = _localized_decimal(row[1], index)
        start = delivery_start + timedelta(hours=index - 1)
        records.append(
            HourlyMarketPrice(
                delivery_start_utc=start,
                delivery_end_utc=start + timedelta(hours=1),
                price=price,
                currency="UAH",
                bidding_zone="UA-IPS",
                market="day_ahead",
                source="operator_market",
                settlement_period=index,
            )
        )
    return records


def _localized_decimal(value: object, period: int) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"Market Operator period {period} has an invalid price")
    normalized = str(value).replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(
            f"Market Operator period {period} has an invalid price"
        ) from exc
