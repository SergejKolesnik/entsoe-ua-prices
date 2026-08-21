"""Deterministic, sanitized daily JSON contract for read-only consumers."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from zoneinfo import ZoneInfo

from market_forecast.neighbor_markets import NEIGHBOR_MARKETS
from market_forecast.services.neighbor_prices import aggregate_price_rows_hourly
from market_forecast.weather_locations import WEATHER_LOCATIONS

KYIV = ZoneInfo("Europe/Kyiv")
OPERATOR_SOURCE = "operator_market"
UA_ZONE = "UA-IPS"
ENTSOE_UA_ZONE = "10Y1001C--00003F"
SCHEMA_VERSION = "1.0"


def build_daily_report(
    repository: Any,
    delivery_date: date,
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build one JSON-safe report without network calls or database mutations."""

    generated = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if generated_at is not None and (
        generated_at.tzinfo is None
        or generated_at.utcoffset() != timezone.utc.utcoffset(None)
    ):
        raise ValueError("generated_at must use UTC")
    day_start, day_end = _day_bounds(delivery_date)
    expected = int((day_end - day_start).total_seconds() // 3600)
    details = repository.list_price_details(
        OPERATOR_SOURCE, day_start, day_end, bidding_zone=UA_ZONE
    )
    hourly = [_hourly_item(row) for row in details]
    prices = [row[3] for row in details]
    complete = len(details) == expected and _continuous(details, day_start, day_end)
    quality_status = "complete" if complete else ("unavailable" if not details else "incomplete")
    available = repository.available_period(OPERATOR_SOURCE, bidding_zone=UA_ZONE)
    latest_delivery = available[1].astimezone(KYIV).date() if available else None
    freshness_status = (
        "unavailable" if latest_delivery is None else
        "stale" if latest_delivery < delivery_date else
        "current" if latest_delivery == delivery_date else
        "historical"
    )
    report_status = "stale" if freshness_status == "stale" else quality_status

    prior = _comparison_day(repository, delivery_date - timedelta(days=1))
    trailing = [
        _comparison_day(repository, delivery_date - timedelta(days=offset))
        for offset in range(1, 8)
    ]
    trailing_complete = [item for item in trailing if item["status"] == "complete"]
    trailing_average = (
        sum((Decimal(str(item["average_price"])) for item in trailing_complete), Decimal(0))
        / len(trailing_complete)
        if trailing_complete
        else None
    )
    current_average = sum(prices, Decimal(0)) / len(prices) if prices else None
    latest_ingested = max((row[8] for row in details), default=None)
    attempts = repository.latest_collection_attempts([OPERATOR_SOURCE])
    attempt = attempts.get(OPERATOR_SOURCE)

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _iso(generated),
        "delivery_date": delivery_date.isoformat(),
        "timezone": "Europe/Kyiv",
        "status": report_status,
        "source_provenance": {
            "ukrainian_dam": {
                "source": "Market Operator of Ukraine",
                "source_id": OPERATOR_SOURCE,
                "bidding_zone": UA_ZONE,
                "latest_ingested_at": _iso(latest_ingested),
                "latest_collection_attempt": _attempt(attempt),
            },
            "neighbor_prices_and_flows": {"source": "ENTSO-E Transparency Platform"},
            "fx": {"source": "National Bank of Ukraine"},
            "weather": {"source": "Open-Meteo", "interpretation": "regional_points_unweighted"},
            "forecast": {"source": "RDN Market Intelligence", "kind": "frozen_baseline"},
        },
        "semantics": {
            "price_currency": "UAH",
            "price_unit": "UAH/MWh",
            "volume_unit": "MWh",
            "vat": "not_asserted_by_source_contract",
            "null_policy": "missing_values_are_null_and_never_imputed_as_zero",
        },
        "quality": {
            "status": quality_status,
            "freshness_status": freshness_status,
            "latest_available_delivery_date": (
                latest_delivery.isoformat() if latest_delivery is not None else None
            ),
            "expected_period_count": expected,
            "actual_period_count": len(details),
            "complete_period_count": len(details),
        },
        "summary": {
            "average_price": _number(current_average),
            "minimum_price": _number(min(prices)) if prices else None,
            "maximum_price": _number(max(prices)) if prices else None,
            "total_volume_mwh": _number(_sum_optional(row[7] for row in details)),
            "prior_day": _comparison(current_average, prior),
            "trailing_7_days": {
                "status": "complete" if len(trailing_complete) == 7 else (
                    "unavailable" if not trailing_complete else "partial"
                ),
                "complete_days": len(trailing_complete),
                "average_price": _number(trailing_average),
                "absolute_change": _number(
                    current_average - trailing_average
                    if current_average is not None and trailing_average is not None
                    else None
                ),
                "percent_change": _percent_change(current_average, trailing_average),
            },
        },
        "hourly": hourly,
        "context": {
            "fx": _fx_context(repository, delivery_date),
            "neighbor_markets": _neighbor_context(repository, day_start, day_end, expected),
            "cross_border_flows": _flow_context(repository, day_start, day_end),
            "weather": _weather_context(repository, day_start, day_end, expected),
            "forecast": _forecast_context(repository, delivery_date, expected),
        },
    }
    return report


def write_daily_report(report: dict[str, Any], output_path: Path) -> None:
    """Atomically write canonical UTF-8 JSON for a completed report build."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    with NamedTemporaryFile(
        "w", encoding="utf-8", dir=output_path.parent, delete=False, newline="\n"
    ) as temporary:
        temporary.write(payload)
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, output_path)


def latest_operator_delivery_date(repository: Any) -> date:
    """Return the latest stored Ukrainian delivery date or fail visibly."""

    available = repository.available_period(OPERATOR_SOURCE, bidding_zone=UA_ZONE)
    if available is None:
        raise ValueError("No Ukrainian DAM prices are available")
    return available[1].astimezone(KYIV).date()


def _day_bounds(value: date) -> tuple[datetime, datetime]:
    start = datetime.combine(value, time.min, KYIV).astimezone(timezone.utc)
    end = datetime.combine(value + timedelta(days=1), time.min, KYIV).astimezone(timezone.utc)
    return start, end


def _hourly_item(row: tuple[Any, ...]) -> dict[str, Any]:
    start, end, period, price, currency, zone, market, volume, _ = row
    local = start.astimezone(KYIV)
    return {
        "settlement_period": period,
        "delivery_start_utc": _iso(start),
        "delivery_end_utc": _iso(end),
        "delivery_start_local": local.isoformat(),
        "local_hour": local.hour,
        "local_fold": local.fold,
        "price": _number(price),
        "currency": currency,
        "market": market,
        "bidding_zone": zone,
        "volume_mwh": _number(volume),
    }


def _comparison_day(repository: Any, value: date) -> dict[str, Any]:
    start, end = _day_bounds(value)
    expected = int((end - start).total_seconds() // 3600)
    rows = repository.list_price_details(OPERATOR_SOURCE, start, end, bidding_zone=UA_ZONE)
    values = [row[3] for row in rows]
    complete = len(rows) == expected and _continuous(rows, start, end)
    return {
        "delivery_date": value.isoformat(),
        "status": "complete" if complete else ("unavailable" if not rows else "incomplete"),
        "expected_period_count": expected,
        "actual_period_count": len(rows),
        "average_price": _number(sum(values, Decimal(0)) / len(values)) if values else None,
    }


def _comparison(current: Decimal | None, previous: dict[str, Any]) -> dict[str, Any]:
    previous_average = (
        Decimal(str(previous["average_price"]))
        if previous["status"] == "complete" and previous["average_price"] is not None
        else None
    )
    return {
        **previous,
        "absolute_change": _number(
            current - previous_average
            if current is not None and previous_average is not None
            else None
        ),
        "percent_change": _percent_change(current, previous_average),
    }


def _fx_context(repository: Any, delivery_date: date) -> dict[str, Any]:
    rates = repository.list_exchange_rates(delivery_date, delivery_date)
    rate = rates.get(delivery_date)
    return {
        "status": "available" if rate is not None else "unavailable",
        "effective_date": delivery_date.isoformat() if rate is not None else None,
        "currency": "EUR",
        "rate_uah_per_eur": _number(rate),
    }


def _neighbor_context(
    repository: Any, start: datetime, end: datetime, expected: int
) -> list[dict[str, Any]]:
    result = []
    for market in NEIGHBOR_MARKETS:
        raw = repository.list_prices("entsoe", start, end, market.bidding_zone_eic)
        try:
            rows = aggregate_price_rows_hourly(raw)
            status = "complete" if len(rows) == expected else (
                "unavailable" if not rows else "incomplete"
            )
        except ValueError:
            rows = []
            status = "invalid"
        result.append(
            {
                "market": market.code,
                "name": market.name_uk,
                "bidding_zone": market.bidding_zone_eic,
                "status": status,
                "currency": "EUR",
                "unit": "EUR/MWh",
                "period_count": len(rows),
                "average_price": _number(
                    sum((value for _, value in rows), Decimal(0)) / len(rows)
                    if rows else None
                ),
                "hourly": [
                    {"delivery_start_utc": _iso(timestamp), "price": _number(value)}
                    for timestamp, value in rows
                ],
            }
        )
    return result


def _flow_context(repository: Any, start: datetime, end: datetime) -> list[dict[str, Any]]:
    rows = repository.list_flows(start, end)
    result = []
    for market in NEIGHBOR_MARKETS:
        imports = [
            row
            for row in rows
            if row[2] == market.bidding_zone_eic and row[3] == ENTSOE_UA_ZONE
        ]
        exports = [
            row
            for row in rows
            if row[2] == ENTSOE_UA_ZONE and row[3] == market.bidding_zone_eic
        ]
        import_mwh, import_hours = _flow_energy(imports)
        export_mwh, export_hours = _flow_energy(exports)
        expected_hours = Decimal(str((end - start).total_seconds() / 3600))
        if not imports and not exports:
            status = "unavailable"
        elif import_hours == expected_hours and export_hours == expected_hours:
            status = "complete"
        else:
            status = "incomplete"
        result.append(
            {
                "market": market.code,
                "status": status,
                "unit": "MWh",
                "import_mwh": _number(import_mwh),
                "export_mwh": _number(export_mwh),
                "net_import_mwh": _number(import_mwh - export_mwh),
                "covered_import_hours": _number(import_hours),
                "covered_export_hours": _number(export_hours),
                "expected_hours": _number(expected_hours),
            }
        )
    return result


def _weather_context(
    repository: Any, start: datetime, end: datetime, expected: int
) -> dict[str, Any]:
    points = repository.list_weather_forecasts(start, end)
    grouped: dict[str, list[Any]] = {}
    for point in points:
        grouped.setdefault(point.location_id, []).append(point)
    locations = []
    for configured in WEATHER_LOCATIONS:
        location_id = configured.code
        items = grouped.get(location_id, [])
        if not items:
            locations.append(
                {
                    "location_id": location_id,
                    "status": "unavailable",
                    "period_count": 0,
                    "forecast_vintage_utc": None,
                    "average_temperature_c": None,
                    "average_cloud_cover_percent": None,
                    "total_shortwave_radiation_whm2": None,
                    "average_wind_speed_100m_kmh": None,
                }
            )
            continue
        locations.append(
            {
                "location_id": location_id,
                "status": "complete" if len(items) == expected else "incomplete",
                "period_count": len(items),
                "forecast_vintage_utc": _iso(max(item.forecast_vintage_utc for item in items)),
                "average_temperature_c": _average(item.temperature_c for item in items),
                "average_cloud_cover_percent": _average(item.cloud_cover_percent for item in items),
                "total_shortwave_radiation_whm2": _number(
                    sum((item.shortwave_radiation_wm2 for item in items), Decimal(0))
                ),
                "average_wind_speed_100m_kmh": _average(item.wind_speed_100m_kmh for item in items),
            }
        )
    return {
        "status": "unavailable" if not points else (
            "complete" if all(item["status"] == "complete" for item in locations) else "partial"
        ),
        "location_count": sum(item["status"] != "unavailable" for item in locations),
        "expected_location_count": len(WEATHER_LOCATIONS),
        "locations": locations,
    }


def _forecast_context(repository: Any, delivery_date: date, expected: int) -> dict[str, Any]:
    run = next(
        (item for item in repository.list_forecast_runs(limit=100) if item[1] == delivery_date),
        None,
    )
    if run is None:
        return {"status": "unavailable", "period_count": 0, "hourly": []}
    points = repository.list_forecast_points(run[0])
    return {
        "status": "complete" if len(points) == expected else "incomplete",
        "issued_at_utc": _iso(run[2]),
        "training_cutoff_date": run[3].isoformat(),
        "model_name": run[4],
        "model_version": run[5],
        "backtest_mae": _number(run[8]),
        "backtest_rmse": _number(run[9]),
        "absolute_error_p80": _number(run[10]),
        "period_count": len(points),
        "hourly": [
            {
                "delivery_start_utc": _iso(item[0]),
                "predicted_price": _number(item[1]),
                "interval_low": _number(item[2]),
                "interval_high": _number(item[3]),
                "method": item[4],
                "sample_count": item[5],
            }
            for item in points
        ],
    }


def _continuous(rows: list[tuple[Any, ...]], start: datetime, end: datetime) -> bool:
    if not rows or rows[0][0] != start or rows[-1][1] != end:
        return False
    return all(previous[1] == current[0] for previous, current in zip(rows, rows[1:]))


def _flow_energy(rows: list[tuple[Any, ...]]) -> tuple[Decimal, Decimal]:
    energy = Decimal(0)
    hours = Decimal(0)
    for start, end, _, _, power in rows:
        duration = Decimal(str((end - start).total_seconds() / 3600))
        energy += power * duration
        hours += duration
    return energy, hours


def _sum_optional(values: Any) -> Decimal | None:
    rows = list(values)
    if not rows or any(value is None for value in rows):
        return None
    return sum(rows, Decimal(0))


def _average(values: Any) -> int | float | None:
    rows = list(values)
    return _number(sum(rows, Decimal(0)) / len(rows)) if rows else None


def _percent_change(current: Decimal | None, baseline: Decimal | None) -> int | float | None:
    if current is None or baseline in {None, Decimal(0)}:
        return None
    return _number((current - baseline) / baseline * Decimal(100))


def _number(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    return int(value) if value == value.to_integral_value() else float(value)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _attempt(value: tuple[Any, ...] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "delivery_date": value[0].isoformat(),
        "attempted_at_utc": _iso(value[1]),
        "status": value[2],
        "inserted_records": value[3],
    }
