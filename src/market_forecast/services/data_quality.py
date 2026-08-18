"""Coverage and value-quality reporting for persisted hourly prices."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from market_forecast.persistence import SQLiteMarketRepository


@dataclass(frozen=True, slots=True)
class DailyQuality:
    """Quality summary for one delivery day."""

    delivery_date: date
    expected_periods: int
    actual_periods: int
    status: str
    minimum_price: Decimal | None = None
    maximum_price: Decimal | None = None
    average_price: Decimal | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe representation."""

        result = asdict(self)
        result["delivery_date"] = self.delivery_date.isoformat()
        for key in ("minimum_price", "maximum_price", "average_price"):
            value = result[key]
            result[key] = str(value) if value is not None else None
        return result


def build_quality_report(
    repository: SQLiteMarketRepository,
    date_from: date,
    date_to: date,
    source: str,
) -> list[DailyQuality]:
    """Compare persisted intervals with every expected Kyiv delivery hour."""

    if date_to < date_from:
        raise ValueError("date_to must not be before date_from")
    kyiv = ZoneInfo("Europe/Kyiv")
    utc_start = datetime.combine(date_from, time.min, kyiv).astimezone(timezone.utc)
    utc_end = datetime.combine(date_to + timedelta(days=1), time.min, kyiv).astimezone(
        timezone.utc
    )
    prices = repository.list_prices(source, utc_start, utc_end)
    grouped: dict[date, list[Decimal]] = {}
    for timestamp, price in prices:
        local_date = timestamp.astimezone(kyiv).date()
        grouped.setdefault(local_date, []).append(price)

    report: list[DailyQuality] = []
    current = date_from
    while current <= date_to:
        day_start = datetime.combine(current, time.min, kyiv).astimezone(timezone.utc)
        day_end = datetime.combine(current + timedelta(days=1), time.min, kyiv).astimezone(
            timezone.utc
        )
        expected = int((day_end - day_start).total_seconds() // 3600)
        values = grouped.get(current, [])
        actual = len(values)
        status = "complete" if actual == expected else "missing"
        average = sum(values, Decimal(0)) / actual if actual else None
        report.append(
            DailyQuality(
                delivery_date=current,
                expected_periods=expected,
                actual_periods=actual,
                status=status,
                minimum_price=min(values) if values else None,
                maximum_price=max(values) if values else None,
                average_price=average,
            )
        )
        current += timedelta(days=1)
    return report
