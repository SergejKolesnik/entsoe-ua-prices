"""Version-one parsers for verified public CEGH CSV and UEEX weighted HTML."""

import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from html.parser import HTMLParser
from html import unescape
from io import StringIO
import re

from ..domain.gas_indices import GasIndexObservation
from ..sources.base import RawResponse
from ..sources.gas_indices import CEGHIX_URL, UEEX_MARGIN_URL, UEEX_URL
from ..validation.gas_indices import validate_snapshot_date

CEGH_HEADER = "Trading Day;Contract;Open;High;Low;Close;Volume acc.;Trades;CEGHEDI;VWAP;CEGHIX".split(";")
MONTHS = "січня лютого березня квітня травня червня липня серпня вересня жовтня листопада грудня".split()


@dataclass(frozen=True)
class ParseResult:
    """Accepted observations plus explicit counts of unsupported/missing rows."""

    observations: tuple[GasIndexObservation, ...]
    missing_prices: int = 0
    unsupported_contracts: int = 0
    unsupported_vat_rows: int = 0


def _price(text: str, localized: bool = False) -> Decimal:
    text = text.strip()
    pattern = r"(?:\d+|\d{1,3}(?:[ \xa0]\d{3})+)(?:,\d+)?" if localized else r"\d+(?:\.\d+)?"
    if not re.fullmatch(pattern, text):
        raise ValueError(f"Invalid price token: {text!r}")
    return Decimal(text.replace("\xa0", "").replace(" ", "").replace(",", "."))


def _content(raw: RawResponse, url: str) -> str:
    if raw.status_code != 200 or raw.source_url != url:
        raise ValueError("Unexpected response provenance")
    return raw.require_content().decode("utf-8-sig", errors="strict")


def _finish(rows: list[GasIndexObservation], missing: int, unsupported: int = 0,
            legacy: int = 0) -> ParseResult:
    if not rows:
        raise ValueError("No supported gas index observations")
    keys = [(r.series, r.quote_date, r.delivery_date, r.payment_terms) for r in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate gas index observation")
    return ParseResult(tuple(rows), missing, unsupported, legacy)


def parse_ceghix(raw: RawResponse, retrieved_at: datetime) -> ParseResult:
    """Import only explicit CEGHIX DA rows; never substitute VWAP or CEGHEDI."""
    reader = csv.reader(StringIO(_content(raw, CEGHIX_URL)), delimiter=";", strict=True)
    if next(reader, None) != CEGH_HEADER:
        raise ValueError("Unsupported CEGH CSV header")
    rows, missing, unsupported = [], 0, 0
    digest = sha256(raw.content).hexdigest()
    for line, values in enumerate(reader, 2):
        if len(values) != len(CEGH_HEADER):
            raise ValueError(f"Malformed CEGH row {line}")
        trading = datetime.strptime(values[0], "%d.%m.%Y").date()
        contract = re.fullmatch(r"CEGH VTP DA (\d{4}-\d{2}-\d{2})", values[1])
        if not contract:
            if values[1].startswith("CEGH VTP DA"):
                raise ValueError(f"Malformed CEGH DA contract at row {line}")
            unsupported += 1
            continue
        delivery = date.fromisoformat(contract[1])
        if delivery <= trading:
            raise ValueError(f"DA delivery must follow trading date at row {line}")
        if values[-1] == "-":
            missing += 1
            continue
        rows.append(GasIndexObservation("CEGHIX_DA", trading, delivery, _price(values[-1]),
                    "EUR", "MWh", "unspecified", "not_applicable", raw.source_url, digest, retrieved_at))
    result = _finish(rows, missing, unsupported)
    validate_snapshot_date(max(r.quote_date for r in rows), retrieved_at)
    return result


class _WeightedTable(HTMLParser):
    """Read the unique weighted table, retaining only explicitly UAH spans."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.active = False
        self.tables = 0
        self.rows = []
        self.row = None
        self.cell = None
        self.span = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table" and self.active:
            raise ValueError("Nested UEEX table is unsupported")
        if tag == "table" and "weighted" in attrs.get("class", "").split():
            self.tables += 1
            self.active = True
        if not self.active:
            return
        if tag == "tr":
            if self.row is not None:
                raise ValueError("Unclosed UEEX row")
            self.row = []
        elif tag in {"td", "th"}:
            if self.row is None or self.cell is not None:
                raise ValueError("Misplaced or unclosed UEEX cell")
            if attrs.get("colspan", "1") != "1" or attrs.get("rowspan", "1") != "1":
                raise ValueError("Merged UEEX cells are unsupported")
            self.cell = {"text": "", "uah": [], "header": tag == "th"}
        elif tag == "br" and self.cell is not None:
            self.cell["text"] += " "
        elif tag == "span":
            if self.span is not None:
                raise ValueError("Nested UEEX spans are unsupported")
            self.span = attrs.get("class", "")
            if self.span == "u" and self.cell is not None:
                self.cell["uah"].append("")

    def handle_data(self, data):
        if self.active and self.cell is not None:
            self.cell["text"] += data
            if self.span == "u":
                self.cell["uah"][-1] += data

    def handle_endtag(self, tag):
        if not self.active:
            return
        if tag == "span":
            if self.span is None:
                raise ValueError("Unmatched UEEX span closure")
            self.span = None
        elif tag in {"td", "th"}:
            if self.row is None or self.cell is None or self.span is not None:
                raise ValueError("Malformed UEEX table")
            if self.cell["header"] != (tag == "th"):
                raise ValueError("Mismatched UEEX cell closure")
            self.row.append(self.cell)
            self.cell = None
        elif tag == "tr":
            if self.row is None or self.cell is not None:
                raise ValueError("Malformed UEEX row closure")
            self.rows.append(self.row)
            self.row = None
        elif tag == "table":
            if self.row is not None or self.cell is not None or self.span is not None:
                raise ValueError("Unclosed UEEX table contents")
            self.active = False


def parse_ueex(raw: RawResponse, retrieved_at: datetime) -> ParseResult:
    """Parse monthly VTT weighted prices by payment terms, without FX conversion."""
    parser = _WeightedTable()
    content = _content(raw, UEEX_URL)
    dates = re.findall(r"станом на\s*(\d{2}\.\d{2}\.\d{4})", unescape(content))
    if len(dates) != 1:
        raise ValueError("Expected one UEEX snapshot date")
    as_of = datetime.strptime(dates[0], "%d.%m.%Y").date()
    validate_snapshot_date(as_of, retrieved_at)
    if "З 1 липня 2022 року" not in content or "без урахування ПДВ" not in content:
        raise ValueError("Missing UEEX VAT regime notice")
    parser.feed(content)
    parser.close()
    if parser.tables != 1 or parser.active or len(parser.rows) < 2:
        raise ValueError("Expected one complete UEEX weighted table")
    header, *body = parser.rows
    expected = ("дата фіксації ціни", "по всіх умовах оплати", "передоплата", "післяплата")
    if len(header) != 4 or any(not c["header"] or term not in c["text"] for c, term in zip(header, expected)):
        raise ValueError("Unsupported UEEX header or payment order")
    if any("тис." not in c["text"] or "куб." not in c["text"] or "грн" not in c["text"] for c in header[1:]):
        raise ValueError("Unsupported UEEX price units")
    rows, missing, legacy = [], 0, 0
    digest = sha256(raw.content).hexdigest()
    for cells in body:
        if len(cells) != 4 or any(c["header"] for c in cells):
            raise ValueError("Malformed UEEX row")
        label = " ".join(cells[0]["text"].split())
        match = re.fullmatch(r"(\w+) (\d{4})\s*\((\d{2}\.\d{2}\.\d{4})\)", label)
        if not match or match[1] not in MONTHS:
            raise ValueError(f"Invalid UEEX resource/date: {label!r}")
        resource = date(int(match[2]), MONTHS.index(match[1]) + 1, 1)
        fixed = datetime.strptime(match[3], "%d.%m.%Y").date()
        if fixed > as_of:
            raise ValueError("UEEX fixing date is after snapshot date")
        if fixed < date(2022, 7, 1):
            legacy += 1
            continue
        for cell, terms in zip(cells[1:], ("all", "prepayment", "postpayment")):
            if not cell["uah"] and not cell["text"].strip():
                missing += 1
                continue
            if len(cell["uah"]) != 1:
                raise ValueError("Expected one explicit UAH value per UEEX cell")
            token = cell["uah"][0].strip()
            if token == "-":
                missing += 1
                continue
            rows.append(GasIndexObservation("UEEX_MONTHLY_VTT", fixed, resource, _price(token, True),
                        "UAH", "1000m3", "excluded", terms, raw.source_url, digest, retrieved_at))
    return _finish(rows, missing, legacy=legacy)


class _MarginTable(HTMLParser):
    """Read one exact UEEX margin-price table without guessing its layout."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.active = False
        self.tables = 0
        self.rows: list[list[str]] = []
        self.row: list[str] | None = None
        self.cell: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table" and attributes.get("id") == "ogts_table":
            if self.active or self.tables:
                raise ValueError("Expected one UEEX margin table")
            self.active = True
            self.tables += 1
            return
        if not self.active:
            return
        if tag == "table":
            raise ValueError("Nested UEEX margin table is unsupported")
        if tag == "tr":
            if self.row is not None:
                raise ValueError("Unclosed UEEX margin row")
            self.row = []
        elif tag == "td":
            if self.row is None or self.cell is not None:
                raise ValueError("Malformed UEEX margin cell")
            if attributes.get("colspan", "1") != "1" or attributes.get("rowspan", "1") != "1":
                raise ValueError("Merged UEEX margin cells are unsupported")
            self.cell = ""
        elif tag == "br" and self.cell is not None:
            self.cell += " "

    def handle_data(self, data: str) -> None:
        if self.active and self.cell is not None:
            self.cell += data

    def handle_endtag(self, tag: str) -> None:
        if not self.active:
            return
        if tag == "td":
            if self.row is None or self.cell is None:
                raise ValueError("Malformed UEEX margin cell closure")
            self.row.append(self.cell)
            self.cell = None
        elif tag == "tr":
            if self.row is None or self.cell is not None:
                raise ValueError("Malformed UEEX margin row closure")
            self.rows.append(self.row)
            self.row = None
        elif tag == "table":
            if self.row is not None or self.cell is not None:
                raise ValueError("Unclosed UEEX margin table")
            self.active = False


def parse_ueex_margin(raw: RawResponse, retrieved_at: datetime) -> ParseResult:
    """Parse the final no-VAT UEEX margin indicators for one stated gas day."""

    content = _content(raw, UEEX_MARGIN_URL)
    gas_days = re.findall(
        r'name\s*=\s*(?:["\'])?ogts_date(?:["\'])?[^>]*'
        r'placeholder\s*=\s*(?:["\'])?(\d{2}\.\d{2}\.\d{4})(?:["\'])?',
        content,
    )
    if len(gas_days) != 1:
        raise ValueError("Expected one UEEX margin gas day")
    gas_day = datetime.strptime(gas_days[0], "%d.%m.%Y").date()
    validate_snapshot_date(gas_day, retrieved_at)
    parser = _MarginTable()
    parser.feed(content)
    parser.close()
    if parser.tables != 1 or parser.active:
        raise ValueError("Expected one complete UEEX margin table")
    expected = {
        "Маржинальна ціна продажу:": "UEEX_MARGIN_SALE",
        "Середньозважена ціна короткострокових стандартизованих продуктів:": "UEEX_MARGIN_WEIGHTED_SHORT_TERM",
        "Маржинальна ціна придбання:": "UEEX_MARGIN_PURCHASE",
    }
    if len(parser.rows) != 6:
        raise ValueError("Unsupported UEEX margin table row count")
    rows: list[GasIndexObservation] = []
    digest = sha256(raw.content).hexdigest()
    for position, (label, series) in enumerate(expected.items()):
        without_vat, with_vat = parser.rows[position * 2: position * 2 + 2]
        if len(without_vat) != 2 or len(with_vat) != 2:
            raise ValueError("Unsupported UEEX margin table columns")
        if " ".join(without_vat[0].split()) != label:
            raise ValueError("Unsupported UEEX margin row label")
        if "з ПДВ" not in " ".join(with_vat[1].split()):
            raise ValueError("UEEX margin VAT row is missing")
        value = re.match(r"^\s*([\d\xa0 ]+(?:,\d+)?)\s+грн/тис\.\s*куб\.\s*м\.\s*без\s+ПДВ\s*$", without_vat[1])
        if value is None:
            raise ValueError("Unsupported UEEX margin no-VAT value")
        rows.append(GasIndexObservation(
            series, gas_day, gas_day, _price(value[1], localized=True), "UAH", "1000m3",
            "excluded", "not_applicable", raw.source_url, digest, retrieved_at,
        ))
    return _finish(rows, 0)
