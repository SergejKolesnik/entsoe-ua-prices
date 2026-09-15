import unittest
from unittest.mock import Mock

from market_forecast.sources.operator_intraday import OperatorIntradaySource, RESULTS_CSV_URL


class OperatorIntradaySourceTests(unittest.TestCase):
    def test_fetches_explicit_quarter_csv(self) -> None:
        session = Mock()
        response = Mock(
            content=b"header;row", status_code=200,
            headers={"Content-Type": "text/csv; charset=utf-8"},
        )
        session.get.return_value = response

        raw = OperatorIntradaySource(session=session, timeout_seconds=12).fetch_quarter(2026, 2)

        self.assertEqual(raw.source_url, RESULTS_CSV_URL.format(year=2026, quarter=2))
        session.get.assert_called_once_with(raw.source_url, timeout=12)

    def test_rejects_non_csv_response_and_invalid_quarter(self) -> None:
        session = Mock()
        session.get.return_value = Mock(content=b"html", headers={"Content-Type": "text/html"})
        source = OperatorIntradaySource(session=session)
        with self.assertRaisesRegex(ValueError, "not CSV"):
            source.fetch_quarter(2026, 1)
        with self.assertRaisesRegex(ValueError, "quarter"):
            source.fetch_quarter(2026, 5)
