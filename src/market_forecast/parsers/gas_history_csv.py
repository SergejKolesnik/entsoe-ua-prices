"""Versioned parser for the verified annual gas history worksheet layout."""

import csv
from datetime import date
from decimal import Decimal
from io import StringIO
import re

from market_forecast.domain.gas_history import GasHistoryMonth

MONTHS = "январь февраль март апрель май июнь июль август сентябрь октябрь ноябрь декабрь".split()
HEADERS = (
    "Месяц", "цена за 1000 м3 природного газа с НДС, грн.",
    "тариф за 1000 м3 за транспортировку с НДС, грн.",
    "тариф за 1000 м3 за распределение с НДС, грн.",
    "Цена всего за 1000 м3 (природный газ, транспортировка, распределение) с НДС, грн.",
    "объем (завод), тыс.м3", "объем (профилакторий), тыс.м3",
    "объем всего (завод, профилакторий) тыс.м3", "сумма с НДС, грн.",
)


def _number(value: str) -> Decimal:
    value = value.strip().replace("\xa0", " ")
    if not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?: [0-9]{3})+)(?:[.,][0-9]+)?", value):
        raise ValueError(f"Invalid annual gas number: {value!r}")
    return Decimal(value.replace(" ", "").replace(",", "."))


def parse_gas_history_csv(content: bytes, year: int) -> list[GasHistoryMonth]:
    """Require all twelve months and reconcile source totals before accepting."""
    text = content.decode("utf-8-sig", errors="strict")
    if not re.search(rf"ПРИРОДНЫЙ ГАЗ\s+{year}\s+год", text):
        raise ValueError("Annual gas title/year does not match")
    rows = list(csv.reader(StringIO(text), strict=True))
    # Google gviz may collapse the title and header rows into one label.
    # Accept only that explicitly verified variant, keeping every other header exact.
    for row in rows:
        for column, value in enumerate(row):
            if re.fullmatch(rf'ПРИРОДНЫЙ ГАЗ\s+{year}\s+год\s+\(Поставщик [^\r\n]+\)\s+Месяц', value):
                row[column] = "Месяц"
    headers = [(i, row.index("Месяц")) for i, row in enumerate(rows) if "Месяц" in row]
    if len(headers) != 1:
        raise ValueError("Expected one annual gas header")
    index, offset = headers[0]
    normalize = lambda value: " ".join(value.split())
    if tuple(map(normalize, rows[index][offset:offset + 9])) != HEADERS:
        raise ValueError("Unsupported annual gas units, VAT or header order")
    body = [r for r in rows[index + 1:] if any(v.strip() for v in r)]
    if len(body) != 13:
        raise ValueError("Annual gas history requires twelve months and annual totals")
    result = []
    for month, row in enumerate(body[:12], 1):
        values = row[offset:offset + 9]
        if len(values) != 9 or values[0].strip().lower() != MONTHS[month - 1]:
            raise ValueError("Missing, duplicate or unordered gas history month")
        numbers = list(map(_number, values[1:]))
        result.append(GasHistoryMonth(date(year, month, 1), *numbers[:4],
                                      *(v * 1000 for v in numbers[4:7]), numbers[7]))
    totals = body[-1][offset:offset + 9]
    if len(totals) != 9 or totals[0].strip() != "ГОД":
        raise ValueError("Annual gas totals row missing")
    for column, attr, scale, tolerance in (
        (5, "plant_volume_m3", 1000, Decimal("0.00001")),
        (6, "sanatorium_volume_m3", 1000, Decimal("0.00001")),
        (7, "total_volume_m3", 1000, Decimal("0.00001")),
        (8, "amount_uah", 1, Decimal("0.06")),
    ):
        # CSV may expose monthly amounts rounded to cents: at most 12 half-cents.
        if abs(sum(getattr(r, attr) for r in result) - _number(totals[column]) * scale) > tolerance:
            raise ValueError(f"Annual gas total mismatch: {attr}")
    return result
