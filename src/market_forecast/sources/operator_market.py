"""Official Ukrainian Market Operator result discovery."""

from __future__ import annotations

from datetime import date, datetime, timezone
from html.parser import HTMLParser
from urllib.parse import quote

import requests

from market_forecast.domain import SourceObservation


RESULTS_URL = "https://www.oree.com.ua/index.php/PXS/get_pxs_res"
DOWNLOAD_BASE_URL = "https://www.oree.com.ua/index.php/PXS/downloadxlsx"


class _HiddenInputParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hdata_link: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "input":
            return
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        value = (values.get("value") or "").strip()
        if "hdata_link" in classes and value:
            self.hdata_link = value


class OperatorMarketSource:
    """Discover official DAM Excel artifacts for an explicit delivery date."""

    source_name = "operator_market"

    def __init__(
        self,
        session: requests.Session | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    def discover(self, delivery_date: date) -> SourceObservation | None:
        """Return a validated artifact reference, or None if unpublished."""

        requested_day = delivery_date.strftime("%d.%m.%Y")
        response = self.session.post(
            RESULTS_URL,
            data={"day": requested_day},
            headers={
                "Accept": "*/*",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Referer": "https://www.oree.com.ua/index.php/control/results_mo/DAM",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        if not response.text.strip():
            raise ValueError("Market Operator returned an empty response")

        parser = _HiddenInputParser()
        parser.feed(response.text)
        reference = parser.hdata_link
        if not reference:
            return None
        if not reference.startswith(f"{requested_day}/DAM/"):
            raise ValueError("Market Operator artifact date or market does not match request")
        if any(part in reference for part in ("..", "\\", "?", "#")):
            raise ValueError("Market Operator returned an unsafe artifact reference")

        encoded_reference = "/".join(quote(part, safe="") for part in reference.split("/"))
        return SourceObservation(
            source=self.source_name,
            delivery_date=delivery_date,
            artifact_url=f"{DOWNLOAD_BASE_URL}/{encoded_reference}",
            discovered_at=datetime.now(timezone.utc),
            source_reference=reference,
        )
