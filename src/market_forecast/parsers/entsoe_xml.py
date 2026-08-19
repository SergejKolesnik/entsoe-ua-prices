"""Parser for ENTSO-E Publication_MarketDocument price XML."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from market_forecast.domain import HourlyMarketPrice


_DURATION_PATTERN = re.compile(r"^PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?$")


def parse_price_document(xml_content: bytes) -> list[HourlyMarketPrice]:
    """Parse every ENTSO-E price point using its declared interval and resolution."""

    if not xml_content.strip():
        raise ValueError("ENTSO-E XML document is empty")
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as exc:
        raise ValueError("ENTSO-E response is not valid XML") from exc

    if root.tag.split("}", 1)[-1] != "Publication_MarketDocument":
        raise ValueError("ENTSO-E response is not a price publication document")

    namespace = _namespace(root.tag)
    document_id = _text(root, "mRID", namespace, required=False)
    document_currency = _text(
        root, "currency_Unit.name", namespace, required=False
    )
    records: list[HourlyMarketPrice] = []

    for series in root.findall(_q("TimeSeries", namespace)):
        currency = (
            _text(series, "currency_Unit.name", namespace, required=False)
            or document_currency
        )
        if not currency:
            raise ValueError("ENTSO-E TimeSeries has no currency")
        curve_type = _text(series, "curveType", namespace, required=False)
        zone = (
            _text(series, "in_Domain.mRID", namespace, required=False)
            or _text(series, "out_Domain.mRID", namespace, required=False)
        )
        if not zone:
            raise ValueError("ENTSO-E TimeSeries has no bidding zone")

        for period in series.findall(_q("Period", namespace)):
            start = _parse_datetime(_text(period, "timeInterval/start", namespace))
            end = _parse_datetime(_text(period, "timeInterval/end", namespace))
            resolution = _parse_duration(_text(period, "resolution", namespace))
            if resolution not in {
                timedelta(minutes=15),
                timedelta(minutes=30),
                timedelta(hours=1),
            }:
                raise ValueError(
                    f"Unsupported ENTSO-E price resolution: {resolution}"
                )
            if end <= start:
                raise ValueError("ENTSO-E period end must be after start")

            parsed_points: list[tuple[int, Decimal]] = []
            for point in period.findall(_q("Point", namespace)):
                position_text = _text(point, "position", namespace)
                price_text = _text(point, "price.amount", namespace)
                try:
                    position = int(position_text)
                    price = Decimal(price_text)
                except (ValueError, InvalidOperation) as exc:
                    raise ValueError("ENTSO-E point contains invalid position or price") from exc
                if position < 1:
                    raise ValueError("ENTSO-E position must be positive")
                parsed_points.append((position, price))

            parsed_points.sort(key=lambda item: item[0])
            if len({position for position, _ in parsed_points}) != len(parsed_points):
                raise ValueError("ENTSO-E period contains duplicate positions")
            interval_count, remainder = divmod(end - start, resolution)
            if remainder:
                raise ValueError("ENTSO-E period is not aligned to its resolution")
            for index, (position, price) in enumerate(parsed_points):
                next_position = (
                    parsed_points[index + 1][0]
                    if index + 1 < len(parsed_points)
                    else interval_count + 1
                )
                block_end = next_position if curve_type == "A03" else position + 1
                for expanded_position in range(position, block_end):
                    delivery_start = start + resolution * (expanded_position - 1)
                    delivery_end = delivery_start + resolution
                    if delivery_end > end:
                        raise ValueError("ENTSO-E point falls outside declared period")
                    records.append(
                        HourlyMarketPrice(
                            delivery_start_utc=delivery_start,
                            delivery_end_utc=delivery_end,
                            price=price,
                            currency=currency,
                            bidding_zone=zone,
                            market="day_ahead",
                            source="entsoe",
                            settlement_period=expanded_position,
                            source_revision=document_id,
                        )
                    )

    if not records:
        raise ValueError("ENTSO-E document contains no price points")

    unique: dict[tuple[datetime, datetime, str, str], HourlyMarketPrice] = {}
    for record in records:
        key = (
            record.delivery_start_utc,
            record.delivery_end_utc,
            record.bidding_zone,
            record.currency,
        )
        existing = unique.get(key)
        if existing is not None and existing.price != record.price:
            raise ValueError("ENTSO-E document contains conflicting duplicate prices")
        unique.setdefault(key, record)
    return sorted(unique.values(), key=lambda item: item.delivery_start_utc)


def _namespace(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag[1:].split("}", 1)[0]
    return ""


def _q(path: str, namespace: str) -> str:
    return "/".join(f"{{{namespace}}}{part}" if namespace else part for part in path.split("/"))


def _text(
    element: ET.Element,
    path: str,
    namespace: str,
    required: bool = True,
) -> str | None:
    child = element.find(_q(path, namespace))
    value = child.text.strip() if child is not None and child.text else None
    if required and not value:
        raise ValueError(f"ENTSO-E XML is missing {path}")
    return value


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid ENTSO-E datetime: {value}") from exc
    if parsed.tzinfo is None:
        raise ValueError("ENTSO-E datetime must include timezone")
    return parsed.astimezone(timezone.utc)


def _parse_duration(value: str) -> timedelta:
    match = _DURATION_PATTERN.fullmatch(value)
    if not match:
        raise ValueError(f"Unsupported ENTSO-E resolution: {value}")
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    duration = timedelta(hours=hours, minutes=minutes)
    if duration <= timedelta(0):
        raise ValueError("ENTSO-E resolution must be positive")
    return duration
