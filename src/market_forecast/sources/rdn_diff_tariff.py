"""Read-only loader for the NZF differential-tariff comparison source."""

from __future__ import annotations

from calendar import monthrange
from io import StringIO
from typing import Mapping
from urllib.parse import quote

import pandas as pd
import requests


DEFAULT_SPREADSHEET_ID = "1PXj2pH6VJd5O8QyWn-4qElAvHwJQiBRsZIHU93rAlC8"
UKRAINIAN_MONTHS: Mapping[int, str] = {
    1: "Січень", 2: "Лютий", 3: "Березень", 4: "Квітень", 5: "Травень",
    6: "Червень", 7: "Липень", 8: "Серпень", 9: "Вересень",
    10: "Жовтень", 11: "Листопад", 12: "Грудень",
}


def csv_export_url(spreadsheet_id: str, sheet_name: str) -> str:
    """Build a public, read-only Google Sheets export URL by tab name."""

    encoded_name = quote(sheet_name, safe="")
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq?tqx=out:csv&sheet={encoded_name}"


def _number(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).replace("\u00a0", "").replace(" ", "").strip()
    if not text:
        return None
    if text.endswith("%"):
        text = text[:-1]
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _has_numeric_hours(row: pd.Series) -> bool:
    return any(_number(row.iloc[column]) is not None for column in range(2, 26))


def _find_block_start(raw: pd.DataFrame, start_at: int) -> int | None:
    for index in range(start_at, len(raw)):
        row = raw.iloc[index]
        if str(row.iloc[0]).strip().isdigit() and _has_numeric_hours(row):
            return index
    return None


def _block_frame(
    raw: pd.DataFrame,
    start: int,
    year: int,
    month: int,
    sheet_name: str,
    value_prefix: str,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for _, row in raw.iloc[start : start + monthrange(year, month)[1]].iterrows():
        day_text = str(row.iloc[0]).strip()
        if not day_text.isdigit():
            continue
        day = int(day_text)
        if not 1 <= day <= 31:
            continue
        try:
            delivery_date = pd.Timestamp(year=year, month=month, day=day).date()
        except ValueError:
            continue
        hourly = [_number(row.iloc[column]) for column in range(2, 26)]
        if not any(value is not None for value in hourly):
            continue
        item: dict[str, object] = {
            "delivery_date": delivery_date,
            "sheet_name": sheet_name,
        }
        item.update({f"{value_prefix}_hour_{hour:02d}": value for hour, value in enumerate(hourly)})
        if value_prefix == "rdn":
            item["rdn_daily"] = _number(row.iloc[26])
            item["weighted_nzf"] = _number(row.iloc[28])
            diff_pct = _number(row.iloc[29])
            item["diff_tariff_pct_source"] = diff_pct / 100 if diff_pct is not None else None
            if all(value in (None, 0) for value in hourly) and item["rdn_daily"] in (None, 0) and item["weighted_nzf"] in (None, 0):
                continue
        elif value_prefix == "cost":
            item["cost_total"] = _number(row.iloc[27])
            item["weighted_nzf_calculated"] = _number(row.iloc[28])
        rows.append(item)
    return pd.DataFrame(rows)


def parse_month_csv(csv_text: str, year: int, month: int, sheet_name: str) -> pd.DataFrame:
    """Parse RDN, actual-volume and hourly-cost blocks from one monthly tab."""

    raw = pd.read_csv(StringIO(csv_text), header=None, dtype=str, keep_default_na=False)
    if raw.shape[1] < 30:
        raise ValueError(f"{sheet_name}: expected at least 30 columns, got {raw.shape[1]}")

    rdn_start = _find_block_start(raw, 0)
    if rdn_start is None:
        raise ValueError(f"{sheet_name}: no dated RDN rows found")
    days = monthrange(year, month)[1]
    volume_start = _find_block_start(raw, rdn_start + days)
    cost_start = _find_block_start(raw, (volume_start + days) if volume_start is not None else rdn_start + days)
    rdn = _block_frame(raw, rdn_start, year, month, sheet_name, "rdn")
    if rdn.empty:
        raise ValueError(f"{sheet_name}: no dated RDN rows found")
    result = rdn
    if volume_start is not None:
        volume = _block_frame(raw, volume_start, year, month, sheet_name, "actual_volume")
        result = result.merge(volume, on=["delivery_date", "sheet_name"], how="left")
    if cost_start is not None:
        cost = _block_frame(raw, cost_start, year, month, sheet_name, "cost")
        result = result.merge(cost, on=["delivery_date", "sheet_name"], how="left")
        calculated_weighted = result["weighted_nzf_calculated"].where(result["cost_total"].fillna(0) > 0)
        result["weighted_nzf"] = calculated_weighted.combine_first(result["weighted_nzf"])
    for hour in range(24):
        volume_column = f"actual_volume_hour_{hour:02d}"
        cost_column = f"cost_hour_{hour:02d}"
        rdn_column = f"rdn_hour_{hour:02d}"
        if volume_column not in result:
            result[volume_column] = pd.NA
        if cost_column not in result:
            result[cost_column] = result[volume_column] * result[rdn_column] / 1000
        elif "cost_total" in result:
            calculated_cost = result[volume_column] * result[rdn_column] / 1000
            result[cost_column] = result[cost_column].where(result["cost_total"].fillna(0) > 0, calculated_cost)
    return result.sort_values("delivery_date").reset_index(drop=True)


def load_comparison_source(
    spreadsheet_id: str = DEFAULT_SPREADSHEET_ID,
    sheets: Mapping[str, int] | None = None,
    timeout_seconds: int = 30,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Load available 2026 monthly tabs by name without writing to the workbook."""

    names = list(sheets) if sheets is not None else [
        f"РДН-{month_name} 2026" for month_name in UKRAINIAN_MONTHS.values()
    ]
    http = session or requests.Session()
    frames: list[pd.DataFrame] = []
    for sheet_name in names:
        month = next((number for number, label in UKRAINIAN_MONTHS.items() if label in sheet_name), None)
        if month is None:
            continue
        response = http.get(csv_export_url(spreadsheet_id, sheet_name), timeout=timeout_seconds)
        response.raise_for_status()
        csv_text = response.content.decode("utf-8-sig")
        # An unknown tab name makes Google fall back to the first sheet with
        # HTTP 200. Parsing the expected day/hour blocks is the validation.
        try:
            parsed = parse_month_csv(csv_text, 2026, month, sheet_name)
        except ValueError:
            continue
        frames.append(parsed)
    if not frames:
        raise ValueError("No monthly RDN differential-tariff tabs were found")
    return pd.concat(frames, ignore_index=True).sort_values("delivery_date").reset_index(drop=True)


def add_aggregates(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return daily and monthly comparison frames with explicit missing values."""

    daily = frame.copy()
    daily["saving_pct"] = (daily["rdn_daily"] - daily["weighted_nzf"]) / daily["rdn_daily"]
    daily.loc[daily["rdn_daily"].isna() | daily["weighted_nzf"].isna() | (daily["rdn_daily"] == 0), "saving_pct"] = pd.NA
    daily["month"] = pd.to_datetime(daily["delivery_date"]).dt.to_period("M").dt.to_timestamp()
    monthly = (
        daily.groupby("month", as_index=False)
        .agg(rdn_daily=("rdn_daily", "mean"), weighted_nzf=("weighted_nzf", "mean"), days=("delivery_date", "count"))
    )
    monthly["saving_pct"] = (monthly["rdn_daily"] - monthly["weighted_nzf"]) / monthly["rdn_daily"]
    monthly.loc[monthly["rdn_daily"].isna() | monthly["weighted_nzf"].isna() | (monthly["rdn_daily"] == 0), "saving_pct"] = pd.NA
    return daily, monthly
