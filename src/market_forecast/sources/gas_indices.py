"""Read-only, fixed-endpoint gas benchmark transports; no database access."""

import requests
from datetime import date

from .base import RawResponse

CEGHIX_URL = "https://www.cegh.at/wp-admin/admin-ajax.php?action=exportPosts&market=AT&postType=day-ahead"
UEEX_URL = "https://www.ueex.com.ua/exchange-quotations/natural-gas/medium-and-long-term-market/"
UEEX_MARGIN_URL = "https://www.ueex.com.ua/exchange-quotations/natural-gas/margin-price/"
UEEX_MARGIN_AJAX_URL = "https://www.ueex.com.ua/auctions_rates_naturalgas_ajax.php"


def fetch_gas_index(source: str) -> RawResponse:
    """Fetch a bounded response from one of two fixed public endpoints."""
    urls = {"ceghix": (CEGHIX_URL, {"application/csv", "text/csv"}),
            "ueex": (UEEX_URL, {"text/html"}),
            "ueex_margin": (UEEX_MARGIN_URL, {"text/html"})}
    if source not in urls:
        raise ValueError("Unknown gas source")
    url, accepted_types = urls[source]
    with requests.get(url, timeout=(10, 40), stream=True, allow_redirects=False) as response:
        if response.status_code != 200:
            raise ValueError(f"Unexpected HTTP status {response.status_code} for {source}")
        content_type = response.headers.get("Content-Type", "").split(";")[0].lower().strip()
        if content_type not in accepted_types:
            raise ValueError(f"Unexpected content type for {source}: {content_type}")
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > 10_000_000:
                raise ValueError("Gas source response exceeds 10 MB")
            chunks.append(chunk)
    raw = RawResponse(b"".join(chunks), content_type, 200, url)
    raw.require_content()
    return raw


def fetch_ueex_margin_for_date(gas_day: str) -> RawResponse:
    """Fetch one historical UEEX margin snapshot through the official selector."""
    if len(gas_day) != 10 or gas_day[4] != "-" or gas_day[7] != "-":
        raise ValueError("gas_day must use YYYY-MM-DD")
    with requests.post(
        UEEX_MARGIN_AJAX_URL,
        data={"ogts_date": gas_day, "lang": "ukr"},
        headers={"Referer": UEEX_MARGIN_URL},
        timeout=(10, 40),
        stream=True,
        allow_redirects=False,
    ) as response:
        if response.status_code != 200:
            raise ValueError(f"Unexpected HTTP status {response.status_code} for UEEX margin history")
        content_type = response.headers.get("Content-Type", "").split(";")[0].lower().strip()
        if content_type not in {"text/html", "text/plain", "application/octet-stream"}:
            raise ValueError(f"Unexpected content type for UEEX margin history: {content_type}")
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > 2_000_000:
                raise ValueError("UEEX margin history response exceeds 2 MB")
            chunks.append(chunk)
    raw = RawResponse(b"".join(chunks), content_type, 200, UEEX_MARGIN_AJAX_URL)
    raw.require_content()
    return raw


def fetch_ueex_monthly_for_month(month: date) -> RawResponse:
    """Fetch the official UEEX medium/long-term page for one calendar month."""
    if month.day != 1:
        raise ValueError("month must be the first day of a month")
    with requests.get(
        UEEX_URL,
        params={"m_w": f"{month.month:02d}", "y_w": str(month.year)},
        timeout=(10, 40),
        stream=True,
        allow_redirects=False,
    ) as response:
        if response.status_code != 200:
            raise ValueError(f"Unexpected HTTP status {response.status_code} for UEEX monthly history")
        content_type = response.headers.get("Content-Type", "").split(";")[0].lower().strip()
        if content_type != "text/html":
            raise ValueError(f"Unexpected content type for UEEX monthly history: {content_type}")
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > 10_000_000:
                raise ValueError("UEEX monthly history response exceeds 10 MB")
            chunks.append(chunk)
        url = response.url
    raw = RawResponse(b"".join(chunks), content_type, 200, url)
    raw.require_content()
    return raw
