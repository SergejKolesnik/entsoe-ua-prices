import unittest

from market_forecast.sources.entsoe import parse_system_metrics


class EntsoeSystemMetricTests(unittest.TestCase):
    def test_parses_generation_series(self):
        xml = b"""<GL_MarketDocument>
          <TimeSeries><mRID>r1</mRID><MktPSRType><psrType>B14</psrType></MktPSRType>
            <Period><timeInterval><start>2026-09-30T00:00:00Z</start></timeInterval>
              <resolution>PT1H</resolution><Point><position>1</position><quantity>1200</quantity></Point>
              <Point><position>2</position><quantity>1180</quantity></Point>
            </Period>
          </TimeSeries>
        </GL_MarketDocument>"""
        rows = parse_system_metrics(xml, "actual_generation")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].category, "B14")
        self.assertEqual(rows[1].value_mw, 1180)


if __name__ == "__main__":
    unittest.main()
