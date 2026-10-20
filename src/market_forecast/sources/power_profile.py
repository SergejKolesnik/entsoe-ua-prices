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


def sheets_values_url(spreadsheet_id: str, sheet_name: str) -> str:
    """Return the read-only Sheets API range covering all monthly blocks."""

    range_name = f"{sheet_name}!A1:NI27"
    return (f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchGet"
            f"?majorDimension=ROWS&ranges={quote(range_name, safe='')}")


def fetch_month_values(spreadsheet_id: str, sheet_name: str, access_token: str,
                       timeout_seconds: float = 30.0) -> list[list[object]]:
    """Fetch one private worksheet through an OAuth access token."""

    import requests

    response = requests.get(
        sheets_values_url(spreadsheet_id, sheet_name),
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json",
                 "User-Agent": "RDN-Market-Intelligence/1.0"},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    values = payload.get("values")
    if values is None:
        ranges = payload.get("valueRanges")
        values = ranges[0].get("values") if ranges else None
    if not isinstance(values, list):
        raise ValueError(f"{sheet_name}: Sheets API response has no values array")
    return values


def list_worksheet_names(spreadsheet_id: str, access_token: str,
                         timeout_seconds: float = 30.0) -> set[str]:
    """List worksheet titles visible to the authorized service account."""

    import requests

    response = requests.get(
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}",
        params={"fields": "sheets.properties.title"},
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json",
                 "User-Agent": "RDN-Market-Intelligence/1.0"},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    sheets = response.json().get("sheets", [])
    return {item["properties"]["title"] for item in sheets
            if item.get("properties", {}).get("title")}


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


def parse_month_values(values: list[list[object]], reporting_month: date,
                       sheet_name: str) -> list[PowerProfileObservation]:
    """Parse horizontal daily blocks returned by the Sheets API."""

    if len(values) < 27 or max((len(row) for row in values), default=0) < 13:
        raise ValueError(f"{sheet_name}: expected at least 27 rows and 13 columns")
    days = monthrange(reporting_month.year, reporting_month.month)[1]
    observations: list[PowerProfileObservation] = []
    for day in range(1, days + 1):
        start = 1 + 12 * (day - 1)
        date_label = str(values[0][start] if start < len(values[0]) else "").strip()
        if not date_label:
            continue
        block: list[PowerProfileObservation] = []
        for hour in range(24):
            row = values[2 + hour] if 2 + hour < len(values) else []
            numbers = [_number(row[start + offset] if start + offset < len(row) else "")
                       for offset in range(8)]
            if all(value is None for value in numbers):
                continue
            block.append(PowerProfileObservation(reporting_month.replace(day=day), hour,
                                                 *numbers, sheet_name))
        if block:
            if len(block) != 24:
                raise ValueError(f"{sheet_name}: day {day} has {len(block)} hourly rows")
            observations.extend(block)
    if not observations:
        raise ValueError(f"{sheet_name}: no hourly profile observations found")
    return observations


def parse_month_csv(csv_text: str, reporting_month: date, sheet_name: str) -> list[PowerProfileObservation]:
    """Parse available hourly blocks; blank future blocks remain absent."""

    raw = pd.read_csv(StringIO(csv_text), header=None, dtype=str, keep_default_na=False)
    if raw.shape[0] < 27 or raw.shape[1] < 13:
        raise ValueError(f"{sheet_name}: expected at least 27 rows and 13 columns")
    return parse_month_values(raw.astype(object).values.tolist(), reporting_month, sheet_name)
