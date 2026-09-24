"""Read-only loaders for NZF solar and GPU generation workbooks."""

from __future__ import annotations

import re
from calendar import monthrange
from datetime import datetime
from io import StringIO
from typing import Mapping
from urllib.parse import quote
from zoneinfo import ZoneInfo

import pandas as pd
import requests


SOLAR_SPREADSHEET_ID = "1U8639UXFyZUNzMOg6BHcg_gDAX_JS9g7fpBkdXOpODw"
GPU_SPREADSHEET_ID = "18Lcm3QMXZy2v225BLpyd8lO-3Z-OoAtCC89VRHREjqk"
MONTHS = {
    1: "Січень", 2: "Лютий", 3: "Березень", 4: "Квітень",
    5: "Травень", 6: "Червень", 7: "Липень", 8: "Серпень",
    9: "Вересень", 10: "Жовтень", 11: "Листопад", 12: "Грудень",
}


def csv_export_url(spreadsheet_id: str, sheet_name: str) -> str:
    """Build a public, read-only Google Sheets CSV export URL."""

    return (
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq?"
        f"tqx=out:csv&sheet={quote(sheet_name, safe='')}"
    )


def _number(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).replace("\u00a0", "").replace(" ", "").strip()
    if not text or text.startswith("#"):
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _month_sheet_name(month: int, short_year: bool) -> str:
    return f"{MONTHS[month]} {'26' if short_year else '2026'}"


def parse_solar_month_csv(csv_text: str, year: int, month: int, sheet_name: str) -> pd.DataFrame:
    """Parse the factual F1-F24 solar block from a monthly worksheet."""

    raw = pd.read_csv(StringIO(csv_text), header=None, dtype=str, keep_default_na=False)
    marker = None
    for index in range(len(raw)):
        if any("ГЕНЕРАЦІЯ СЕС (ФАКТ)" in str(value).upper() for value in raw.iloc[index]):
            marker = index
            break
    candidate_rows: dict[int, list[tuple[int, float | None]]] = {}
    if marker is None:
        # Google CSV export omits the merged "ГЕНЕРАЦІЯ СЕС (ФАКТ)" label.
        # The factual block repeats each day after the plan block; keep the
        # last valid row for every day, which is the factual row.
        for index in range(len(raw)):
            day = _number(raw.iloc[index, 2]) if len(raw.columns) > 2 else None
            hourly = [
                _number(raw.iloc[index, 3 + hour]) if 3 + hour < len(raw.columns) else None
                for hour in range(24)
            ]
            if day is not None and day == int(day) and any(value is not None for value in hourly):
                total = _number(raw.iloc[index, 27]) if len(raw.columns) > 27 else None
                candidate_rows.setdefault(int(day), []).append((index, total))
        if not candidate_rows:
            raise ValueError(f"{sheet_name}: factual solar block not found")
        target_total = _number(raw.iloc[0, 4]) if len(raw.columns) > 4 else None
        occurrence_count = max(len(rows) for rows in candidate_rows.values())
        occurrence_totals = []
        for occurrence in range(occurrence_count):
            totals = [
                rows[occurrence][1]
                for rows in candidate_rows.values()
                if len(rows) > occurrence and rows[occurrence][1] is not None
            ]
            occurrence_totals.append(sum(totals) if totals else None)
        if target_total is not None:
            selected_occurrence = min(
                range(occurrence_count),
                key=lambda occurrence: abs((occurrence_totals[occurrence] or 0) - target_total),
            )
        else:
            selected_occurrence = 0
        row_indices = {
            rows[selected_occurrence][0]
            for rows in candidate_rows.values()
            if len(rows) > selected_occurrence
        }
    else:
        row_indices = set(range(marker + 1, len(raw)))

    rows: list[dict[str, object]] = []
    for index, row in raw.iterrows():
        if index not in row_indices:
            continue
        day = _number(row.iloc[2]) if len(row) > 2 else None
        if day is None or day != int(day) or not 1 <= int(day) <= monthrange(year, month)[1]:
            continue
        hourly = [
            _number(row.iloc[3 + hour]) if 3 + hour < len(row) else None
            for hour in range(24)
        ]
        if not any(value is not None for value in hourly):
            continue
        rows.append({
            "delivery_date": pd.Timestamp(year=year, month=month, day=int(day)).date(),
            **{f"solar_hour_{hour:02d}": value for hour, value in enumerate(hourly)},
            "solar_total_kwh": _number(row.iloc[27]) if len(row) > 27 else None,
        })
    if not rows:
        raise ValueError(f"{sheet_name}: no factual solar rows found")
    return pd.DataFrame(rows).drop_duplicates("delivery_date")


def parse_gpu_month_csv(csv_text: str, year: int, month: int, sheet_name: str) -> pd.DataFrame:
    """Parse the horizontally repeated daily GPU blocks."""

    raw = pd.read_csv(StringIO(csv_text), header=None, dtype=str, keep_default_na=False)
    date_pattern = re.compile(r"^(\d{1,2})\s+[^\s]+\s+(\d{4})$")
    date_blocks: list[tuple[int, int]] = []
    for row_index in range(min(35, len(raw))):
        for column_index, value in enumerate(raw.iloc[row_index]):
            match = date_pattern.match(str(value).strip())
            if match and int(match.group(2)) == year:
                day = int(match.group(1))
                if 1 <= day <= monthrange(year, month)[1]:
                    date_blocks.append((day, column_index))
    if not date_blocks:
        raise ValueError(f"{sheet_name}: no GPU date blocks found")

    hour_rows: dict[int, int] = {}
    for row_index in range(len(raw)):
        hour = _number(raw.iloc[row_index, 1]) if raw.shape[1] > 1 else None
        if hour is not None and hour == int(hour) and 1 <= int(hour) <= 24:
            hour_rows.setdefault(int(hour), row_index)
    if len(hour_rows) < 24:
        raise ValueError(f"{sheet_name}: no complete GPU hourly rows found")

    rows: list[dict[str, object]] = []
    for day, start_column in date_blocks:
        item: dict[str, object] = {
            "delivery_date": pd.Timestamp(year=year, month=month, day=day).date()
        }
        for hour in range(1, 25):
            row = raw.iloc[hour_rows[hour]]
            values = [
                _number(row.iloc[start_column + offset])
                if start_column + offset < len(row) else None
                for offset in range(5)
            ]
            item[f"gpu_hour_{hour - 1:02d}"] = values[0]
            item[f"gpu_cost_hour_{hour - 1:02d}"] = values[2]
            item[f"gpu_economic_effect_hour_{hour - 1:02d}"] = values[4]
        rows.append(item)
    return pd.DataFrame(rows).drop_duplicates("delivery_date")


def load_self_generation_source(
    solar_spreadsheet_id: str = SOLAR_SPREADSHEET_ID,
    gpu_spreadsheet_id: str = GPU_SPREADSHEET_ID,
    sheets: Mapping[int, tuple[str, str]] | None = None,
    year: int = 2026,
    timeout_seconds: int = 30,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Load factual hourly solar and GPU data without writing to either workbook."""

    current_month = datetime.now(ZoneInfo("Europe/Kyiv")).month
    first_month = 7 if current_month >= 7 else 1
    month_sheets = sheets or {
        month: (_month_sheet_name(month, True), _month_sheet_name(month, False))
        for month in range(first_month, current_month + 1)
    }
    http = session or requests.Session()
    frames: list[pd.DataFrame] = []
    for month, (solar_sheet, gpu_sheet) in month_sheets.items():
        try:
            solar_response = http.get(
                csv_export_url(solar_spreadsheet_id, solar_sheet), timeout=timeout_seconds
            )
            solar_response.raise_for_status()
            gpu_response = http.get(
                csv_export_url(gpu_spreadsheet_id, gpu_sheet), timeout=timeout_seconds
            )
            gpu_response.raise_for_status()
            solar = parse_solar_month_csv(
                solar_response.content.decode("utf-8-sig"), year, month, solar_sheet
            )
            gpu = parse_gpu_month_csv(
                gpu_response.content.decode("utf-8-sig"), year, month, gpu_sheet
            )
        except (requests.RequestException, ValueError, pd.errors.ParserError):
            continue
        merged = solar.merge(gpu, on="delivery_date", how="outer")
        for hour in range(24):
            solar_column = f"solar_hour_{hour:02d}"
            if solar_column in merged:
                merged[solar_column] = pd.to_numeric(merged[solar_column], errors="coerce") / 1000
        frames.append(merged)
    if not frames:
        raise ValueError("No factual solar/GPU monthly tabs were found")
    return pd.concat(frames, ignore_index=True).drop_duplicates("delivery_date").sort_values("delivery_date").reset_index(drop=True)
