import unittest
from decimal import Decimal

from market_forecast.parsers import parse_flow_document


class EntsoeFlowXmlTests(unittest.TestCase):
    def test_expands_variable_blocks(self):
        xml = b"""<Publication_MarketDocument xmlns="urn:test">
        <mRID>flow-1</mRID><TimeSeries><out_Domain.mRID>UA</out_Domain.mRID>
        <in_Domain.mRID>PL</in_Domain.mRID><quantity_Measure_Unit.name>MAW</quantity_Measure_Unit.name>
        <curveType>A03</curveType><Period><timeInterval><start>2026-08-18T00:00Z</start>
        <end>2026-08-18T01:00Z</end></timeInterval><resolution>PT15M</resolution>
        <Point><position>1</position><quantity>100</quantity></Point>
        <Point><position>3</position><quantity>150</quantity></Point>
        </Period></TimeSeries></Publication_MarketDocument>"""

        rows = parse_flow_document(xml)

        self.assertEqual([row.power_mw for row in rows], [
            Decimal("100"), Decimal("100"), Decimal("150"), Decimal("150")
        ])
        self.assertEqual(rows[0].source_zone, "UA")
        self.assertEqual(rows[0].target_zone, "PL")

