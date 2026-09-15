"""Strict parsers for audited natural-gas history worksheet layouts."""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from io import StringIO
import re

from market_forecast.domain.gas_history import GasHistoryMonth
from market_forecast.domain.gas_procurement import GasProcurementMonth

MONTHS = "январь февраль март апрель май июнь июль август сентябрь октябрь ноябрь декабрь".split()
HEADERS = (
    "Месяц", "цена за 1000 м3 природного газа без НДС, грн.",
    "цена за 1000 м3 природного газа с НДС, грн.",
    "тариф за 1000 м3 за транспортировку с НДС, грн.",
    "тариф за 1000 м3 за распределение с НДС, грн.",
    "Цена всего за 1000 м3 (природный газ, транспортировка, распределение) с НДС, грн.",
    "объем (завод), тыс.м3", "объем (профилакторий), тыс.м3",
    "объем всего (завод, профилакторий) тыс.м3", "сумма с НДС, грн.",
)
PRICE_SNAPSHOT_HEADERS = (
    "Месяц", "цена за 1000 м3 природного газа без НДС, грн.",
    "тариф за 1000 м3 за транспортировку без НДС, грн.",
    "тариф за 1000 м3 за распределение без НДС, грн.",
    "цена всего за 1000 м3 (природный газ, транспортировка, распределение) без НДС, грн.",
    "объем (завод), тыс.м3", "объем (профилакторий), тыс.м3",
    "ФАКТ объем всего (завод, профилакторий) тыс.м3", "сумма с НДС, грн.",
)
_MONTH_BY_NAME = {name: index for index, name in enumerate(MONTHS, start=1)}


def _number(value: str) -> Decimal:
    value = value.strip().replace("\xa0", " ")
    if not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?: [0-9]{3})+)(?:[.,][0-9]+)?", value):
        raise ValueError(f"Invalid annual gas number: {value!r}")
    return Decimal(value.replace(" ", "").replace(",", "."))


def _normalized(value: str) -> str:
    return " ".join(value.split())


def parse_gas_price_snapshot_csv(content: bytes, source_sheet: str) -> list[GasProcurementMonth]:
    """Read verified VAT-exclusive price rows without creating consumption facts.

    The combined worksheet also displays factual volumes. They are reconciled only
    as a source-integrity check and are deliberately not returned or persisted.
    """

    if not source_sheet.strip():
        raise ValueError("Gas price snapshot source sheet is required")
    try:
        rows = list(csv.reader(StringIO(content.decode("utf-8-sig", errors="strict")), strict=True))
    except UnicodeDecodeError as exc:
        raise ValueError("Gas price snapshot must be UTF-8") from exc
    if not rows:
        raise ValueError("Gas price snapshot is empty")
    header = rows[0]
    if len(header) < 10:
        raise ValueError("Gas price snapshot header is incomplete")
    # Google gviz joins the title and first header cell. Its remaining headers
    # retain this exact, audited VAT-exclusive layout.
    if not re.search(r"ПРИРОДНЫЙ ГАЗ.*Месяц$", header[1]):
        raise ValueError("Gas price snapshot title/header is unsupported")
    if ("Месяц", *( _normalized(value) for value in header[2:10])) != PRICE_SNAPSHOT_HEADERS:
        raise ValueError("Gas price snapshot units, VAT basis or header order are unsupported")

    result: list[GasProcurementMonth] = []
    seen: set[date] = set()
    for row_number, row in enumerate(rows[1:], start=2):
        if not any(value.strip() for value in row):
            continue
        if len(row) != 10 or row[0].strip():
            raise ValueError(f"Gas price snapshot row {row_number} has an unexpected shape")
        match = re.fullmatch(r"(" + "|".join(MONTHS) + r")\s+(20[0-9]{2})", row[1].strip().lower())
        if not match:
            raise ValueError(f"Gas price snapshot row {row_number} has an invalid reporting month")
        reporting_month = date(int(match.group(2)), _MONTH_BY_NAME[match.group(1)], 1)
        if reporting_month in seen:
            raise ValueError("Gas price snapshot has duplicate reporting months")
        seen.add(reporting_month)
        commodity, capacity, distribution, total, plant, sanatorium, actual_total, _amount = (
            _number(value) for value in row[2:]
        )
        if min(commodity, capacity, distribution, total, plant, sanatorium, actual_total) < 0:
            raise ValueError(f"Gas price snapshot row {row_number} contains a negative value")
        if total != commodity + capacity + distribution:
            raise ValueError(f"Gas price snapshot row {row_number} price total does not reconcile")
        if actual_total != plant + sanatorium:
            raise ValueError(f"Gas price snapshot row {row_number} factual volume does not reconcile")
        result.append(GasProcurementMonth(
            reporting_month=reporting_month,
            commodity_price_uah_per_1000m3=commodity,
            distribution_price_uah_per_1000m3=distribution,
            capacity_price_uah_per_1000m3=capacity,
            total_price_uah_per_1000m3=total,
            planned_volume_m3=Decimal(0),
            vat_included=False,
            source_sheet=source_sheet,
        ))
    if not result:
        raise ValueError("Gas price snapshot has no data rows")
    return sorted(result, key=lambda month: month.reporting_month)


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
    if tuple(map(_normalized, rows[index][offset:offset + 10])) != HEADERS:
        raise ValueError("Unsupported annual gas units, VAT or header order")
    body = [r for r in rows[index + 1:] if any(v.strip() for v in r)]
    if len(body) != 13:
        raise ValueError("Annual gas history requires twelve months and annual totals")
    result = []
    for month, row in enumerate(body[:12], 1):
        values = row[offset:offset + 10]
        if len(values) != 10 or values[0].strip().lower() != MONTHS[month - 1]:
            raise ValueError("Missing, duplicate or unordered gas history month")
        numbers = list(map(_number, values[1:]))
        result.append(GasHistoryMonth(date(year, month, 1), *numbers[:5],
                                      *(v * 1000 for v in numbers[5:8]), numbers[8]))
    totals = body[-1][offset:offset + 10]
    if len(totals) != 10 or totals[0].strip() != "ГОД":
        raise ValueError("Annual gas totals row missing")
    for column, attr, scale, tolerance in (
        (6, "plant_volume_m3", 1000, Decimal("0.00001")),
        (7, "sanatorium_volume_m3", 1000, Decimal("0.00001")),
        (8, "total_volume_m3", 1000, Decimal("0.00001")),
        (9, "amount_uah", 1, Decimal("0.06")),
    ):
        if abs(sum(getattr(r, attr) for r in result) - _number(totals[column]) * scale) > tolerance:
            raise ValueError(f"Annual gas total mismatch: {attr}")
    return result
