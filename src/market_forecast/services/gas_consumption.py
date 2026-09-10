"""Monthly gas chart data with explicit observation coverage and facility scope."""

from calendar import monthrange
from collections import defaultdict
from decimal import Decimal


def monthly_consumption(history: list[tuple], days: list[tuple]) -> list[dict]:
    """Prefer verified monthly facts; never add them to overlapping daily values."""
    result = {}
    for row in history:
        result[row[0]] = dict(reporting_month=row[0], plant_volume_m3=row[5],
                              sanatorium_volume_m3=row[6], total_volume_m3=row[7],
                              coverage="Місячний факт", actual_days=None)
    grouped = defaultdict(list)
    for row in days:
        grouped[row[0].replace(day=1)].append(row)
    for month, rows in grouped.items():
        if month in result:
            continue
        known = [r for r in rows if r[2] is not None]
        complete = len({r[0] for r in known}) == monthrange(month.year, month.month)[1]
        result[month] = dict(reporting_month=month,
                             plant_volume_m3=sum((r[2] for r in known), Decimal(0)) if known else None,
                             sanatorium_volume_m3=None, total_volume_m3=None,
                             coverage="Повний добовий факт" if complete else "Неповні добові дані",
                             actual_days=len(known))
    return [result[month] for month in sorted(result)]
