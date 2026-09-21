"""Strict, source-native gas benchmark contracts for the isolated prototype."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import re


@dataclass(frozen=True, slots=True)
class GasIndexObservation:
    """A source quote, never an internally converted or backfilled price.

    available_at is deliberately the retrieval time: a historical quote date
    does not prove that a particular revision was available to a forecast.
    """

    series: str
    quote_date: date
    delivery_date: date
    price: Decimal
    currency: str
    unit: str
    vat: str
    payment_terms: str
    source_url: str
    raw_sha256: str
    available_at: datetime

    def __post_init__(self) -> None:
        if type(self.quote_date) is not date or type(self.delivery_date) is not date:
            raise ValueError("Quote and delivery dates must be dates")
        if not isinstance(self.available_at, datetime) or self.available_at.utcoffset() is None:
            raise ValueError("available_at must be timezone-aware")
        if self.quote_date > self.available_at.date():
            raise ValueError("Quote date is in the future")
        if not isinstance(self.price, Decimal) or not self.price.is_finite() or self.price <= 0:
            raise ValueError("Price must be a finite positive Decimal")
        if not re.fullmatch(r"[0-9a-f]{64}", self.raw_sha256):
            raise ValueError("Invalid raw response SHA256")
        if self.series == "CEGHIX_DA":
            expected = ("EUR", "MWh", "unspecified", "not_applicable")
            if self.delivery_date <= self.quote_date:
                raise ValueError("DA delivery must follow trading date")
            host = "https://www.cegh.at/"
        elif self.series == "UEEX_MONTHLY_VTT":
            expected = ("UAH", "1000m3", "excluded", self.payment_terms)
            if self.payment_terms not in {"all", "prepayment", "postpayment"}:
                raise ValueError("Unknown UEEX payment terms")
            if self.delivery_date.day != 1 or self.quote_date < date(2022, 7, 1):
                raise ValueError("Only explicit post-June-2022 monthly VAT regime supported")
            host = "https://www.ueex.com.ua/"
        elif self.series in {
            "UEEX_MARGIN_SALE",
            "UEEX_MARGIN_WEIGHTED_SHORT_TERM",
            "UEEX_MARGIN_PURCHASE",
        }:
            expected = ("UAH", "1000m3", "excluded", "not_applicable")
            if self.delivery_date != self.quote_date:
                raise ValueError("UEEX margin price must apply to its stated gas day")
            host = "https://www.ueex.com.ua/"
        else:
            raise ValueError("Unknown benchmark series")
        if (self.currency, self.unit, self.vat, self.payment_terms) != expected:
            raise ValueError("Incompatible source units or tax basis")
        if not self.source_url.startswith(host):
            raise ValueError("Unexpected source URL")
