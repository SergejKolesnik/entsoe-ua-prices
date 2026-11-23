"""Read-only parser for the horizontal daily blocks in the power profile sheet."""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation
from io import StringIO
import re
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

    # Monthly blocks are horizontal and some days contain extra ASU columns.
    # ZZ safely covers the current 414-column sheets without relying on a
    # fixed block width or silently truncating the end of a month.
    range_name = f"{sheet_name}!A1:ZZ27"
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


def _header_key(value: object) -> str:
    """Normalize a sheet header for tolerant matching across monthly layouts."""

    return re.sub(r"\s+", " ", str(value or "").strip().lower().replace("\u00a0", " "))


def _field_positions(headers: list[object]) -> dict[str, int]:
    """Map semantic profile fields to offsets inside one daily block."""

    positions: dict[str, int] = {}
    for offset, raw_header in enumerate(headers):
        header = _header_key(raw_header)
        if "план купівлі" in header or header == "замовлено дез":
            positions.setdefault("planned_purchase_mwh", offset)
        elif header == "купівля":
            # The expanded layout has both network withdrawal and the
            # settlement purchase; the latter is the requested fact value.
            positions["purchased_mwh"] = offset
        elif header == "куплено дез" or "відібраний із мережі" in header:
            positions.setdefault("purchased_mwh", offset)
        elif header == "гпу":
            positions.setdefault("gpu_mwh", offset)
        elif header == "сес":
            positions.setdefault("ses_mwh", offset)
        elif "віддали в мережу" in header:
            positions.setdefault("grid_export_mwh", offset)
        elif "споживання технолог" in header:
            positions.setdefault("technology_consumption_mwh", offset)
        elif "споживання силов" in header:
            positions.setdefault("power_consumption_mwh", offset)
        elif header in {"сальдо небалансів", "небаланси покупки"}:
            positions.setdefault("imbalance_mwh", offset)
        elif header == "план продаж":
            positions.setdefault("planned_sale_mwh", offset)
        elif header == "факт продаж":
            positions.setdefault("sold_mwh", offset)
        elif "небаланси продаж" in header:
            positions.setdefault("sale_imbalance_mwh", offset)
    return positions


def parse_month_values(values: list[list[object]], reporting_month: date,
                       sheet_name: str) -> list[PowerProfileObservation]:
    """Parse horizontal daily blocks returned by the Sheets API."""

    if len(values) < 27 or max((len(row) for row in values), default=0) < 13:
        raise ValueError(f"{sheet_name}: expected at least 27 rows and 13 columns")
    observations: list[PowerProfileObservation] = []
    expected_days = monthrange(reporting_month.year, reporting_month.month)[1]
    date_starts: list[tuple[int, int]] = []
    for column, raw_label in enumerate(values[0]):
        label = str(raw_label or "").strip()
        if not re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", label):
            continue
        try:
            parsed = date.fromisoformat(f"{label[6:]}-{label[3:5]}-{label[:2]}")
        except ValueError:
            continue
        if parsed.year == reporting_month.year and parsed.month == reporting_month.month:
            date_starts.append((column, parsed.day))

    if not date_starts:
        raise ValueError(f"{sheet_name}: no daily date headers found")
    seen_days: set[int] = set()
    for index, (start, day) in enumerate(date_starts):
        if day in seen_days or day < 1 or day > expected_days:
            raise ValueError(f"{sheet_name}: duplicate or invalid day header {day}")
        seen_days.add(day)
        end = date_starts[index + 1][0] if index + 1 < len(date_starts) else max(
            len(row) for row in values
        )
        positions = _field_positions(values[1][start:end] if len(values) > 1 else [])
        # Legacy monthly sheets have no usable header row; preserve their
        # established first-eight-column contract as a compatibility fallback.
        if not positions:
            positions = {
                field: offset for offset, field in enumerate((
                    "planned_purchase_mwh", "purchased_mwh", "gpu_mwh", "ses_mwh",
                    "grid_export_mwh", "technology_consumption_mwh",
                    "power_consumption_mwh", "imbalance_mwh",
                ))
            }
        block: list[PowerProfileObservation] = []
        for hour in range(24):
            row = values[2 + hour] if 2 + hour < len(values) else []
            def value(field: str) -> Decimal | None:
                offset = positions.get(field)
                return _number(row[start + offset]) if offset is not None and start + offset < len(row) else None

            numbers = [value(field) for field in (
                "planned_purchase_mwh", "purchased_mwh", "gpu_mwh", "ses_mwh",
                "grid_export_mwh", "technology_consumption_mwh", "power_consumption_mwh",
                "imbalance_mwh",
            )]
            if all(value is None for value in numbers):
                continue
            block.append(PowerProfileObservation(reporting_month.replace(day=day), hour,
                                                 *numbers, sheet_name,
                                                 value("planned_sale_mwh"), value("sold_mwh"),
                                                 value("sale_imbalance_mwh")))
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
