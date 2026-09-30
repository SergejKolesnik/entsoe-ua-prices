import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from market_forecast.persistence import RawArtifactStore, SQLiteMarketRepository
from market_forecast.sources.entsoe import GenerationUnavailability, parse_generation_unavailability


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

    def test_repository_round_trip_is_idempotent(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            repository = SQLiteMarketRepository(root / "market.sqlite3")
            artifact = RawArtifactStore(root / "raw").save(
                b"<outage />", "entsoe_outage", datetime.now(timezone.utc).date(), "xml"
            )
            item = GenerationUnavailability(
                event_id="event-1",
                unit_name="Unit 1",
                business_type="A53",
                available_capacity_mw=420.0,
                start=datetime(2026, 9, 29, tzinfo=timezone.utc),
                end=datetime(2026, 10, 1, tzinfo=timezone.utc),
            )

            first = repository.store_generation_unavailability(
                artifact, "https://example.test/api", item.start, "UA-IPS", [item]
            )
            second = repository.store_generation_unavailability(
                artifact, "https://example.test/api", item.start, "UA-IPS", [item]
            )

            self.assertEqual(first, 1)
            self.assertEqual(second, 1)
            rows = repository.list_generation_unavailability(
                datetime(2026, 9, 29, tzinfo=timezone.utc),
                datetime(2026, 10, 2, tzinfo=timezone.utc),
                "UA-IPS",
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], "Unit 1")


if __name__ == "__main__":
    unittest.main()
