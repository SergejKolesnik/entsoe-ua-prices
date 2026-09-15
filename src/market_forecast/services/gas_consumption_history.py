"""Explicit identities for restored 2022 daily gas-consumption worksheets."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class GasConsumptionWorksheet:
    reporting_month: date
    sheet_name: str


HISTORICAL_CONSUMPTION_WORKSHEETS = (
    GasConsumptionWorksheet(date(2022, 2, 1), "Февраль 22 газ"),
    GasConsumptionWorksheet(date(2022, 3, 1), "Март 22 газ"),
    GasConsumptionWorksheet(date(2022, 4, 1), "Апрель 22 газ"),
    GasConsumptionWorksheet(date(2022, 5, 1), "Май 22 газ"),
    GasConsumptionWorksheet(date(2022, 6, 1), "Июнь 22 газ"),
    GasConsumptionWorksheet(date(2022, 7, 1), "Июль газ 22"),
    GasConsumptionWorksheet(date(2022, 9, 1), "Сентябрь 22 газ"),
    GasConsumptionWorksheet(date(2022, 12, 1), "Декабрь 22 газ"),
)


def historical_consumption_worksheets(date_from: date, date_to: date) -> tuple[GasConsumptionWorksheet, ...]:
    if date_from.day != 1 or date_to.day != 1 or date_from > date_to:
        raise ValueError("Gas consumption history range must use ordered first-of-month dates")
    return tuple(item for item in HISTORICAL_CONSUMPTION_WORKSHEETS if date_from <= item.reporting_month <= date_to)
