"""Resolve the current monthly gas worksheet from the audited naming convention."""

from __future__ import annotations

from datetime import date


_UKRAINIAN = ("січні", "лютому", "березні", "квітні", "травні", "червні",
              "липні", "серпні", "вересні", "жовтні", "листопаді", "грудні")
_RUSSIAN = ("январе", "феврале", "марте", "апреле", "мае", "июне",
            "июле", "августе", "сентябре", "октябре", "ноябре", "декабре")


def current_gas_worksheet_candidates(reporting_month: date) -> tuple[str, ...]:
    """Return stable candidate names used by the internal workbook."""

    if reporting_month.day != 1:
        raise ValueError("reporting_month must be the first day of a month")
    short_year = reporting_month.year % 100
    number = reporting_month.month
    return (
        f"{number} ціна газу у {_UKRAINIAN[number - 1]} {short_year:02d}",
        f"{number} цена газа в {_RUSSIAN[number - 1]} {short_year:02d}",
        f"{number} ціна газа у {_UKRAINIAN[number - 1]} {short_year:02d}",
        f"{number} цена газу у {_RUSSIAN[number - 1]} {short_year:02d}",
    )
