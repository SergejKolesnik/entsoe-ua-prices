import unittest
from datetime import datetime, timezone
from decimal import Decimal

from market_forecast.parsers import parse_price_document
from market_forecast.validation import validate_delivery_periods


NAMESPACE = "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:0"


def build_document(points: list[tuple[int, str]], end: str = "2026-08-19T00:00Z") -> bytes:
    point_xml = "".join(
        f"<Point><position>{position}</position><price.amount>{price}</price.amount></Point>"
        for position, price in points
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <Publication_MarketDocument xmlns="{NAMESPACE}">
      <mRID>revision-42</mRID>
      <currency_Unit.name>EUR</currency_Unit.name>
      <TimeSeries>
        <in_Domain.mRID>10Y1001C--00003F</in_Domain.mRID>
        <Period>
          <timeInterval>
            <start>2026-08-18T00:00Z</start>
            <end>{end}</end>
          </timeInterval>
          <resolution>PT60M</resolution>
          {point_xml}
        </Period>
      </TimeSeries>
    </Publication_MarketDocument>""".encode()


class EntsoeXmlTests(unittest.TestCase):
    def test_parses_declared_intervals_and_decimal_prices(self):
        records = parse_price_document(build_document([(1, "5000.25"), (2, "5100.75")]))

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].price, Decimal("5000.25"))
        self.assertEqual(records[0].delivery_start_utc, datetime(2026, 8, 18, tzinfo=timezone.utc))
        self.assertEqual(records[1].delivery_start_utc.hour, 1)
        self.assertEqual(records[0].source_revision, "revision-42")

    def test_rejects_html_error_body(self):
        with self.assertRaisesRegex(ValueError, "missing currency"):
            parse_price_document(b"<html><body>Unauthorized</body></html>")

    def test_rejects_point_outside_period(self):
        xml = build_document([(25, "5000")])

        with self.assertRaisesRegex(ValueError, "outside"):
            parse_price_document(xml)

    def test_rejects_non_hourly_resolution(self):
        xml = build_document([(1, "5000")]).replace(b"PT60M", b"PT15M")

        with self.assertRaisesRegex(ValueError, "Expected hourly"):
            parse_price_document(xml)

    def test_parsed_records_can_be_validated(self):
        records = parse_price_document(build_document([(1, "5000"), (2, "5100")]))

        validate_delivery_periods(records, expected_periods=2)


if __name__ == "__main__":
    unittest.main()
