"""Read-only loader for the NZF differential-tariff comparison source."""

from __future__ import annotations

from io import StringIO
from calendar import monthrange
from typing import Mapping

import pandas as pd
import requests


DEFAULT_SPREADSHEET_ID = "1PXj2pH6VJd5O8QyWn-4qElAvHwJQiBRsZIHU93rAlC8"
DEFAULT_SHEETS: Mapping[str, int] = {
    "РДН-Січень 2026": 464169438,
    "РДН-Лютий 2026": 1376318205,
    "РДН-Березень 2026": 589018877,
    "РДН-Квітень 2026": 1985168973,
    "РДН-Травень 2026": 2079022703,
    "РДН-Червень 2026": 58739977,
    "РДН-Липень 2026": 265303,
    "РДН-Серпень 2026": 2041831457,
    "РДН-Вересень 2026": 2003677328,
}


def csv_export_url(spreadsheet_id: str, gid: int) -> str:
    """Build a public, read-only Google Sheets CSV export URL."""

    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={gid}"


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


def parse_month_csv(csv_text: str, year: int, month: int, sheet_name: str) -> pd.DataFrame:
    """Parse rows 17+ of a monthly workbook export.

    The source contract is C:Z hourly RDN, AA daily RDN average, AC factual
    weighted NZF price and AD the source-provided differential percentage.
    """

    raw = pd.read_csv(StringIO(csv_text), header=None, dtype=str, keep_default_na=False)
    if raw.shape[1] < 30:
        raise ValueError(f"{sheet_name}: expected at least 30 columns, got {raw.shape[1]}")

    rows: list[dict[str, object]] = []
    days_in_month = monthrange(year, month)[1]
    data_start = next(
        (
            index
            for index, row in raw.iterrows()
            if str(row.iloc[0]).strip().isdigit()
            and _number(row.iloc[2]) is not None
            and _number(row.iloc[26]) is not None
        ),
        None,
    )
    if data_start is None:
        raise ValueError(f"{sheet_name}: no dated RDN rows found")
    for _, row in raw.iloc[data_start : data_start + days_in_month].iterrows():
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
        rdn_daily = _number(row.iloc[26])
        weighted_nzf = _number(row.iloc[28])
        diff_pct = _number(row.iloc[29])
        if rdn_daily is None and not any(value is not None for value in hourly):
            continue
        item: dict[str, object] = {
            "delivery_date": delivery_date,
            "sheet_name": sheet_name,
            "rdn_daily": rdn_daily,
            "weighted_nzf": weighted_nzf,
            "diff_tariff_pct_source": diff_pct / 100 if diff_pct is not None else None,
        }
        item.update({f"rdn_hour_{hour:02d}": value for hour, value in enumerate(hourly)})
        rows.append(item)
    if not rows:
        raise ValueError(f"{sheet_name}: no dated RDN rows found")
    return pd.DataFrame(rows).sort_values("delivery_date").reset_index(drop=True)


def load_comparison_source(
    spreadsheet_id: str = DEFAULT_SPREADSHEET_ID,
    sheets: Mapping[str, int] = DEFAULT_SHEETS,
    timeout_seconds: int = 30,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Load all configured monthly tabs without writing to the source workbook."""

    http = session or requests.Session()
    frames: list[pd.DataFrame] = []
    for sheet_name, gid in sheets.items():
        response = http.get(csv_export_url(spreadsheet_id, gid), timeout=timeout_seconds)
        response.raise_for_status()
        month = next((number for number, label in {
            1: "Січень", 2: "Лютий", 3: "Березень", 4: "Квітень", 5: "Травень",
            6: "Червень", 7: "Липень", 8: "Серпень", 9: "Вересень", 10: "Жовтень",
            11: "Листопад", 12: "Грудень",
        }.items() if label in sheet_name), None)
        if month is None:
            raise ValueError(f"Cannot infer month from sheet name: {sheet_name}")
        # Google omits a reliable charset header; decode the UTF-8 bytes
        # explicitly to keep non-breaking spaces and Ukrainian text intact.
        frames.append(parse_month_csv(response.content.decode("utf-8-sig"), 2026, month, sheet_name))
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
