"""ENTSO-E Transparency Platform raw document client."""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from market_forecast.sources.base import RawResponse


API_URL = "https://web-api.tp.entsoe.eu/api"


class EntsoeSource:
    """Fetch raw ENTSO-E price documents without parsing or persistence."""

    def __init__(
        self,
        token: str,
        session: requests.Session | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not token.strip():
            raise ValueError("ENTSO-E token is required")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._token = token
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    def fetch_day_ahead_prices(
        self,
        period_start_utc: datetime,
        period_end_utc: datetime,
        bidding_zone_eic: str,
    ) -> RawResponse:
        """Fetch an A44 day-ahead price document for an explicit UTC interval."""

        start = _require_utc(period_start_utc, "period_start_utc")
        end = _require_utc(period_end_utc, "period_end_utc")
        if end <= start:
            raise ValueError("period_end_utc must be after period_start_utc")
        if not bidding_zone_eic.strip():
            raise ValueError("bidding_zone_eic is required")

        response = self.session.get(
            API_URL,
            params={
                "securityToken": self._token,
                "documentType": "A44",
                "processType": "A01",
                "in_Domain": bidding_zone_eic,
                "out_Domain": bidding_zone_eic,
                "periodStart": start.strftime("%Y%m%d%H%M"),
                "periodEnd": end.strftime("%Y%m%d%H%M"),
            },
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(
                f"ENTSO-E request failed with HTTP status {response.status_code}"
            ) from exc
        raw = RawResponse(
            content=response.content,
            content_type=response.headers.get("Content-Type", ""),
            status_code=response.status_code,
            # response.url contains the securityToken query parameter.
            # Store only the stable endpoint so credentials cannot leak into logs.
            source_url=API_URL,
        )
        raw.require_content()
        return raw

    def fetch_physical_flows(
        self,
        period_start_utc: datetime,
        period_end_utc: datetime,
        source_zone_eic: str,
        target_zone_eic: str,
    ) -> RawResponse:
        """Fetch an A11 physical-flow document for one directed border."""

        start = _require_utc(period_start_utc, "period_start_utc")
        end = _require_utc(period_end_utc, "period_end_utc")
        response = self.session.get(
            API_URL,
            params={
                "securityToken": self._token,
                "documentType": "A11",
                "out_Domain": source_zone_eic,
                "in_Domain": target_zone_eic,
                "periodStart": start.strftime("%Y%m%d%H%M"),
                "periodEnd": end.strftime("%Y%m%d%H%M"),
            },
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(
                f"ENTSO-E request failed with HTTP status {response.status_code}"
            ) from exc
        raw = RawResponse(
            content=response.content,
            content_type=response.headers.get("Content-Type", ""),
            status_code=response.status_code,
            source_url=API_URL,
        )
        raw.require_content()
        return raw


def _require_utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    if value.utcoffset() != timezone.utc.utcoffset(None):
        raise ValueError(f"{name} must use UTC")
    return value.astimezone(timezone.utc)
