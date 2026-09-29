import unittest

from market_forecast.sources.entsoe import parse_generation_unavailability


class EntsoeOutageParserTests(unittest.TestCase):
    def test_parses_compact_generation_unavailability_record(self):
        xml = b'''<?xml version="1.0"?>
        <Unavailability_MarketDocument xmlns="urn:test">
          <TimeSeries>
            <businessType>A53</businessType>
            <production_RegisteredResource.name>Unit 1</production_RegisteredResource.name>
            <availableQuantity>420</availableQuantity>
            <timeInterval><start>2026-09-29T00:00Z</start><end>2026-10-01T00:00Z</end></timeInterval>
          </TimeSeries>
        </Unavailability_MarketDocument>'''

        rows = parse_generation_unavailability(xml)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].unit_name, "Unit 1")
        self.assertEqual(rows[0].business_type, "A53")
        self.assertEqual(rows[0].available_capacity_mw, 420.0)
        self.assertIsNotNone(rows[0].start)

    def test_keeps_missing_capacity_as_none(self):
        rows = parse_generation_unavailability(b"<root><TimeSeries /></root>")

        self.assertIsNone(rows[0].available_capacity_mw)


if __name__ == "__main__":
    unittest.main()
