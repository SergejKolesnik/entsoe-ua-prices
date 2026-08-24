"""Read-only comparison of stored and currently published Operator rows."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from market_forecast.parsers import parse_operator_market_workbook
from market_forecast.persistence import SQLiteMarketRepository
from market_forecast.sources import OperatorMarketSource


KYIV = ZoneInfo("Europe/Kyiv")
SOURCE = "operator_market"
ZONE = "UA-IPS"


def diagnose_operator_conflict(
    delivery_date: date,
    repository: SQLiteMarketRepository,
    source: OperatorMarketSource,
) -> dict[str, Any]:
    """Compare official and stored fields without writing or returning price values."""

    observation = source.discover(delivery_date)
    if observation is None:
        return {"delivery_date": delivery_date.isoformat(), "status": "unpublished"}
    official = parse_operator_market_workbook(
        source.download(observation).content, delivery_date
    )
    start = datetime.combine(delivery_date, time.min, KYIV).astimezone(timezone.utc)
    end = datetime.combine(
        delivery_date + timedelta(days=1), time.min, KYIV
    ).astimezone(timezone.utc)
    stored_rows = repository.list_price_details(SOURCE, start, end, bidding_zone=ZONE)
    stored = {
        row[0]: {
            "delivery_end_utc": row[1],
            "settlement_period": row[2],
            "price": row[3],
            "currency": row[4],
        }
        for row in stored_rows
    }
    published = {row.delivery_start_utc: row for row in official}
    conflicts: list[dict[str, Any]] = []
    for timestamp in sorted(set(stored) & set(published)):
        fields = []
        current = published[timestamp]
        if stored[timestamp]["delivery_end_utc"] != current.delivery_end_utc:
            fields.append("delivery_end")
        if stored[timestamp]["settlement_period"] != current.settlement_period:
            fields.append("settlement_period")
        if stored[timestamp]["price"] != current.price:
            fields.append("price")
        if stored[timestamp]["currency"] != current.currency:
            fields.append("currency")
        if fields:
            conflicts.append(
                {
                    "hour_kyiv": timestamp.astimezone(KYIV).strftime("%H:%M"),
                    "fields": fields,
                }
            )
    missing = sorted(set(published) - set(stored))
    extra = sorted(set(stored) - set(published))
    return {
        "delivery_date": delivery_date.isoformat(),
        "status": "conflict" if conflicts or missing or extra else "identical",
        "stored_periods": len(stored),
        "official_periods": len(published),
        "conflicts": conflicts,
        "missing_hours_kyiv": [item.astimezone(KYIV).strftime("%H:%M") for item in missing],
        "extra_hours_kyiv": [item.astimezone(KYIV).strftime("%H:%M") for item in extra],
    }
