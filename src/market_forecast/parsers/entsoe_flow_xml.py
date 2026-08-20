"""Parser for ENTSO-E A11 physical-flow publications."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from market_forecast.domain import CrossBorderFlow


_DURATION_PATTERN = re.compile(r"^PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?$")


def parse_flow_document(xml_content: bytes) -> list[CrossBorderFlow]:
    """Expand ENTSO-E fixed or variable-block flow curves into intervals."""

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as exc:
        raise ValueError("ENTSO-E flow response is not valid XML") from exc
    if root.tag.split("}", 1)[-1] != "Publication_MarketDocument":
        raise ValueError("ENTSO-E response is not a physical-flow publication")
    namespace = root.tag[1:].split("}", 1)[0] if root.tag.startswith("{") else ""
    q = lambda path: "/".join(
        f"{{{namespace}}}{part}" if namespace else part for part in path.split("/")
    )
    document_id = root.findtext(q("mRID"))
    records: list[CrossBorderFlow] = []
    for series in root.findall(q("TimeSeries")):
        source_zone = series.findtext(q("out_Domain.mRID"))
        target_zone = series.findtext(q("in_Domain.mRID"))
        unit = series.findtext(q("quantity_Measure_Unit.name"))
        curve_type = series.findtext(q("curveType"))
        if not source_zone or not target_zone or unit != "MAW":
            raise ValueError("ENTSO-E flow series has invalid zones or unit")
        for period in series.findall(q("Period")):
            start = _datetime(period.findtext(q("timeInterval/start")))
            end = _datetime(period.findtext(q("timeInterval/end")))
            resolution = _duration(period.findtext(q("resolution")))
            interval_count, remainder = divmod(end - start, resolution)
            if remainder or interval_count < 1:
                raise ValueError("ENTSO-E flow period is not resolution-aligned")
            points: list[tuple[int, Decimal]] = []
            for point in period.findall(q("Point")):
                try:
                    position = int(point.findtext(q("position")) or "")
                    quantity = Decimal(point.findtext(q("quantity")) or "")
                except (ValueError, InvalidOperation) as exc:
                    raise ValueError("ENTSO-E flow point is invalid") from exc
                points.append((position, quantity))
            points.sort()
            for index, (position, quantity) in enumerate(points):
                next_position = points[index + 1][0] if index + 1 < len(points) else interval_count + 1
                block_end = next_position if curve_type == "A03" else position + 1
                for expanded in range(position, block_end):
                    interval_start = start + resolution * (expanded - 1)
                    interval_end = interval_start + resolution
                    if position < 1 or interval_end > end:
                        raise ValueError("ENTSO-E flow point is outside its period")
                    records.append(CrossBorderFlow(
                        interval_start, interval_end, source_zone, target_zone,
                        quantity, document_id,
                    ))
    if not records:
        raise ValueError("ENTSO-E flow document contains no points")
    unique: dict[tuple[datetime, str, str], CrossBorderFlow] = {}
    for record in records:
        key = (record.delivery_start_utc, record.source_zone, record.target_zone)
        existing = unique.get(key)
        if existing is not None and existing.power_mw != record.power_mw:
            raise ValueError("ENTSO-E flow document contains conflicting duplicates")
        unique.setdefault(key, record)
    return sorted(unique.values(), key=lambda item: item.delivery_start_utc)


def _datetime(value: str | None) -> datetime:
    if not value:
        raise ValueError("ENTSO-E flow timestamp is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("ENTSO-E flow timestamp has no timezone")
    return parsed.astimezone(timezone.utc)


def _duration(value: str | None) -> timedelta:
    match = _DURATION_PATTERN.fullmatch(value or "")
    if not match:
        raise ValueError("Unsupported ENTSO-E flow resolution")
    duration = timedelta(
        hours=int(match.group("hours") or 0),
        minutes=int(match.group("minutes") or 0),
    )
    if duration <= timedelta(0):
        raise ValueError("ENTSO-E flow resolution must be positive")
    return duration

