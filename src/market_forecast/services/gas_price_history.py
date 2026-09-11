"""Explicit registry of audited historical monthly gas-price worksheets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class GasPriceWorksheet:
    """One read-only monthly worksheet known to state prices without VAT."""

    reporting_month: date
    sheet_name: str


# These sheet names, including their legacy spacing, are source identities.
# Do not derive names from dates: the workbook has mixed Ukrainian/Russian titles.
HISTORICAL_PRICE_WORKSHEETS = (
    GasPriceWorksheet(date(2022, 2, 1), "Февраль 22 цена газа"),
    GasPriceWorksheet(date(2022, 3, 1), "Март 22 цена газа "),
    GasPriceWorksheet(date(2022, 4, 1), "Апрель 22  цена газа"),
    GasPriceWorksheet(date(2022, 5, 1), "Май 22 цена газа"),
    GasPriceWorksheet(date(2022, 6, 1), "Июнь 22 цена газа"),
    GasPriceWorksheet(date(2022, 7, 1), "Июль 22 цена газа"),
    GasPriceWorksheet(date(2022, 9, 1), "Сентябрь 22 цена газа"),
    GasPriceWorksheet(date(2022, 10, 1), "Октябрь 22 цена газа"),
    GasPriceWorksheet(date(2022, 12, 1), "Декабрь 22 цена газа"),
    GasPriceWorksheet(date(2024, 5, 1), "5 май 24 цена газа"),
    GasPriceWorksheet(date(2024, 6, 1), "6 июнь 24 цена газа"),
    GasPriceWorksheet(date(2024, 7, 1), "7 июль 24 цена газа"),
    GasPriceWorksheet(date(2024, 8, 1), "8 серпень 24 ціна газа"),
    GasPriceWorksheet(date(2024, 9, 1), "9 вересень 24 ціна газа "),
    GasPriceWorksheet(date(2024, 10, 1), "10 жовтень 24 ціна газа"),
    GasPriceWorksheet(date(2024, 11, 1), "11 листопад 24 ціна газа"),
    GasPriceWorksheet(date(2024, 12, 1), "12 грудень 24 ціна газу"),
)


def historical_price_worksheets(date_from: date, date_to: date) -> tuple[GasPriceWorksheet, ...]:
    """Return audited source identities in an inclusive month range."""

    if date_from.day != 1 or date_to.day != 1 or date_from > date_to:
        raise ValueError("Historical gas price range must use ordered first-of-month dates")
    return tuple(item for item in HISTORICAL_PRICE_WORKSHEETS
                 if date_from <= item.reporting_month <= date_to)
