"""ENTSO-E Transparency Platform raw document client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from market_forecast.sources.base import RawResponse


API_URL = "https://web-api.tp.entsoe.eu/api"


@dataclass(frozen=True, slots=True)
class GenerationUnavailability:
    """One ENTSO-E generation-unit unavailability record."""

    event_id: str | None
    unit_name: str | None
    business_type: str | None
    available_capacity_mw: float | None
    start: datetime | None
    end: datetime | None


@dataclass(frozen=True, slots=True)
class SystemMetric:
    """One published ENTSO-E system observation in MW."""

    metric: str
    category: str
    observed_at: datetime
    value_mw: float
    source_revision: str | None = None


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
        self.session = session or _retrying_session()
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

    def fetch_generation_unavailability(
        self,
        period_start_utc: datetime,
        period_end_utc: datetime,
        bidding_zone_eic: str,
        business_type: str | None = None,
    ) -> RawResponse:
        """Fetch ENTSO-E A80 generation-unit availability for a bidding zone."""

        start = _require_utc(period_start_utc, "period_start_utc")
        end = _require_utc(period_end_utc, "period_end_utc")
        if end <= start:
            raise ValueError("period_end_utc must be after period_start_utc")
        params = {
            "securityToken": self._token,
            "documentType": "A80",
            "biddingZone_Domain": bidding_zone_eic,
            "periodStart": start.strftime("%Y%m%d%H%M"),
            "periodEnd": end.strftime("%Y%m%d%H%M"),
        }
        if business_type:
            params["businessType"] = business_type
        response = self.session.get(API_URL, params=params, timeout=self.timeout_seconds)
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

    def fetch_actual_generation(
        self, period_start_utc: datetime, period_end_utc: datetime, bidding_zone_eic: str
    ) -> RawResponse:
        """Fetch A75 realised generation by production type."""

        return self._fetch_generation_document(
            period_start_utc, period_end_utc, bidding_zone_eic,
            document_type="A75", process_type="A16",
        )

    def fetch_actual_load(
        self, period_start_utc: datetime, period_end_utc: datetime, bidding_zone_eic: str
    ) -> RawResponse:
        """Fetch A65 realised total load for a bidding zone."""

        return self._fetch_generation_document(
            period_start_utc, period_end_utc, bidding_zone_eic,
            document_type="A65", process_type="A16", domain_key="outBiddingZone_Domain",
        )

    def fetch_installed_capacity(
        self, period_start_utc: datetime, period_end_utc: datetime, bidding_zone_eic: str
    ) -> RawResponse:
        """Fetch A68 installed generation capacity by production type."""

        return self._fetch_generation_document(
            period_start_utc, period_end_utc, bidding_zone_eic,
            document_type="A68", process_type="A33",
        )

    def _fetch_generation_document(
        self, period_start_utc: datetime, period_end_utc: datetime,
        bidding_zone_eic: str, *, document_type: str, process_type: str,
        domain_key: str = "in_Domain",
    ) -> RawResponse:
        start = _require_utc(period_start_utc, "period_start_utc")
        end = _require_utc(period_end_utc, "period_end_utc")
        if end <= start:
            raise ValueError("period_end_utc must be after start")
        response = self.session.get(
            API_URL,
            params={
                "securityToken": self._token,
                "documentType": document_type,
                "processType": process_type,
                domain_key: bidding_zone_eic,
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
        raw = RawResponse(response.content, response.headers.get("Content-Type", ""), response.status_code, API_URL)
        raw.require_content()
        return raw


def parse_generation_unavailability(content: bytes) -> list[GenerationUnavailability]:
    """Parse A80 XML while preserving missing capacity as ``None``."""

    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise ValueError("ENTSO-E outage response is not valid XML") from exc
    records: list[GenerationUnavailability] = []
    for series in root.iter():
        if _local_name(series.tag) != "TimeSeries":
            continue
        values = {_local_name(node.tag): (node.text or "").strip() for node in series.iter()}
        records.append(
            GenerationUnavailability(
                event_id=values.get("mRID"),
                unit_name=(
                    values.get("production_RegisteredResource.name")
                    or values.get("registeredResource.name")
                    or values.get("name")
                ),
                business_type=values.get("businessType"),
                available_capacity_mw=_number(values.get("availableQuantity")),
                start=_datetime(values.get("start")),
                end=_datetime(values.get("end")),
            )
        )
    return records


def parse_system_metrics(content: bytes, metric: str) -> list[SystemMetric]:
    """Parse A75/A65/A68 generation/load XML into timestamped MW observations."""

    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise ValueError("ENTSO-E system response is not valid XML") from exc
    records: list[SystemMetric] = []
    for series in root.iter():
        if _local_name(series.tag) != "TimeSeries":
            continue
        values = {_local_name(node.tag): (node.text or "").strip() for node in series.iter()}
        category = values.get("psrType") or values.get("MktPSRType.psrType") or "total"
        revision = values.get("mRID")
        for period in (node for node in series.iter() if _local_name(node.tag) == "Period"):
            start_text = next((node.text for node in period.iter() if _local_name(node.tag) == "start"), None)
            resolution_text = next((node.text for node in period.iter() if _local_name(node.tag) == "resolution"), None)
            if not start_text or not resolution_text:
                continue
            start = _datetime(start_text.strip())
            resolution = _duration(resolution_text.strip())
            if start is None or resolution is None:
                continue
            for point in (node for node in period.iter() if _local_name(node.tag) == "Point"):
                position_text = next((node.text for node in point.iter() if _local_name(node.tag) == "position"), None)
                quantity_text = next((node.text for node in point.iter() if _local_name(node.tag) in {"quantity", "in_Qty", "out_Qty"}), None)
                try:
                    position = int(position_text or "")
                    value = float(quantity_text or "")
                except ValueError:
                    continue
                if position > 0:
                    records.append(SystemMetric(metric, category, start + resolution * (position - 1), value, revision))
    return records


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _number(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def _duration(value: str) -> timedelta | None:
    if not value.startswith("PT"):
        return None
    value = value[2:]
    try:
        if value.endswith("H"):
            return timedelta(hours=int(value[:-1]))
        if value.endswith("M"):
            return timedelta(minutes=int(value[:-1]))
    except ValueError:
        return None
    return None


def _require_utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    if value.utcoffset() != timezone.utc.utcoffset(None):
        raise ValueError(f"{name} must use UTC")
    return value.astimezone(timezone.utc)


def _retrying_session() -> requests.Session:
    """Build a session that retries only safe transient GET failures."""

    session = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=1.0,
        allowed_methods=frozenset({"GET"}),
        status_forcelist=(429, 500, 502, 503, 504),
        raise_on_status=False,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session
