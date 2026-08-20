"""Official National Bank of Ukraine exchange-rate client."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import requests


API_URL = "https://bank.gov.ua/NBU_Exchange/exchange_site"


class NbuExchangeRateSource:
    """Fetch official daily UAH-per-EUR rates for an inclusive date range."""

    def __init__(self, session: requests.Session | None = None, timeout_seconds: float = 30.0):
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    def fetch_eur_rates(self, date_from: date, date_to: date) -> dict[date, Decimal]:
        """Return validated official EUR rates keyed by effective date."""

        if date_to < date_from:
            raise ValueError("Exchange-rate range is reversed")
        response = self.session.get(
            API_URL,
            params={
                "start": date_from.strftime("%Y%m%d"),
                "end": date_to.strftime("%Y%m%d"),
                "valcode": "eur",
                "sort": "exchangedate",
                "order": "asc",
                "json": "",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        rates: dict[date, Decimal] = {}
        for item in payload:
            if item.get("cc") != "EUR":
                continue
            try:
                effective_date = datetime.strptime(item["exchangedate"], "%d.%m.%Y").date()
                raw_rate = item.get("rate_per_unit")
                if raw_rate is None:
                    raw_rate = item["rate"]
                rate = Decimal(str(raw_rate))
            except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
                raise ValueError("NBU returned an invalid EUR exchange rate") from exc
            if rate <= 0:
                raise ValueError("NBU returned a non-positive EUR exchange rate")
            rates[effective_date] = rate
        if not rates:
            raise ValueError("NBU returned no EUR exchange rates")
        return rates
