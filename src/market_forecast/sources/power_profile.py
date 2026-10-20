"""Read-only parser for the horizontal daily blocks in the power profile sheet."""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation
from io import StringIO
from urllib.parse import quote

import pandas as pd

from market_forecast.domain.power_profile import PowerProfileObservation


MONTHS_UK = ("січень", "лютий", "березень", "квітень", "травень", "червень",
             "липень", "серпень", "вересень", "жовтень", "листопад", "грудень")


def csv_export_url(spreadsheet_id: str, sheet_name: str) -> str:
    return (f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq"
            f"?tqx=out:csv&sheet={quote(sheet_name, safe='')}")


def monthly_sheet_name(reporting_month: date) -> str:
    if reporting_month.day != 1:
        raise ValueError("reporting_month must be the first day of a month")
    return f"{MONTHS_UK[reporting_month.month - 1]} {reporting_month.year}"


def _number(value: object) -> Decimal | None:
    text = str(value).replace("\u00a0", "").replace(" ", "").strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    try:
        return Decimal(text.replace(",", "."))
    except InvalidOperation:
        return None


def parse_month_csv(csv_text: str, reporting_month: date, sheet_name: str) -> list[PowerProfileObservation]:
    """Parse available hourly blocks; blank future blocks remain absent."""

    raw = pd.read_csv(StringIO(csv_text), header=None, dtype=str, keep_default_na=False)
    if raw.shape[0] < 27 or raw.shape[1] < 13:
        raise ValueError(f"{sheet_name}: expected at least 27 rows and 13 columns")
    days = monthrange(reporting_month.year, reporting_month.month)[1]
    observations: list[PowerProfileObservation] = []
    for day in range(1, days + 1):
        start = 1 + 12 * (day - 1)
        if start + 11 >= raw.shape[1]:
            break
        date_label = str(raw.iloc[0, start]).strip()
        if not date_label:
            continue
        block: list[PowerProfileObservation] = []
        for hour in range(24):
            row = raw.iloc[2 + hour]
            values = [_number(row.iloc[start + offset]) for offset in range(8)]
            if all(value is None for value in values):
                continue
            block.append(PowerProfileObservation(
                reporting_month.replace(day=day), hour, *values, sheet_name
            ))
        if block:
            if len(block) != 24:
                raise ValueError(f"{sheet_name}: day {day} has {len(block)} hourly rows")
            observations.extend(block)
    if not observations:
        raise ValueError(f"{sheet_name}: no hourly profile observations found")
    return observations
