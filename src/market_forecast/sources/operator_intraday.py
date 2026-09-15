"""Quarterly public CSV source for Ukrainian intraday-market results."""

from __future__ import annotations

import requests

from market_forecast.sources.base import RawResponse


RESULTS_CSV_URL = "https://www.oree.com.ua/index.php/control/results_mo_stat_csv/IDM/{year}/{quarter}"


class OperatorIntradaySource:
    """Fetch one explicitly selected official VDR quarter without persistence."""

    source_name = "operator_intraday"

    def __init__(self, session: requests.Session | None = None, timeout_seconds: float = 30.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    def fetch_quarter(self, year: int, quarter: int) -> RawResponse:
        """Return the official CSV response for one calendar quarter."""

        if year < 2019 or year > 2100:
            raise ValueError("year is outside the supported official archive")
        if quarter not in (1, 2, 3, 4):
            raise ValueError("quarter must be between 1 and 4")
        url = RESULTS_CSV_URL.format(year=year, quarter=quarter)
        response = self.session.get(url, timeout=self.timeout_seconds)
        response.raise_for_status()
        raw = RawResponse(
            content=response.content,
            content_type=response.headers.get("Content-Type", ""),
            status_code=response.status_code,
            source_url=url,
        )
        raw.require_content()
        if not raw.content_type.lower().startswith("text/csv"):
            raise ValueError("Operator intraday response is not CSV")
        return raw
