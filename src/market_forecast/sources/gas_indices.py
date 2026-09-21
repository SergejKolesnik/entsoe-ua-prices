"""Read-only, fixed-endpoint gas benchmark transports; no database access."""

import requests

from .base import RawResponse

CEGHIX_URL = "https://www.cegh.at/wp-admin/admin-ajax.php?action=exportPosts&market=AT&postType=day-ahead"
UEEX_URL = "https://www.ueex.com.ua/exchange-quotations/natural-gas/medium-and-long-term-market/"
UEEX_MARGIN_URL = "https://www.ueex.com.ua/exchange-quotations/natural-gas/margin-price/"


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
