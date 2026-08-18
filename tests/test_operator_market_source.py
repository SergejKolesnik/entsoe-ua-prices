import unittest
from datetime import date
from unittest.mock import Mock

from market_forecast.sources.operator_market import OperatorMarketSource, RESULTS_URL


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class OperatorMarketSourceTests(unittest.TestCase):
    def test_discovers_matching_official_artifact(self):
        session = Mock()
        session.post.return_value = FakeResponse(
            '<input type="hidden" class="other hdata_link" value="19.08.2026/DAM/2">'
        )
        source = OperatorMarketSource(session=session, timeout_seconds=12)

        result = source.discover(date(2026, 8, 19))

        self.assertIsNotNone(result)
        self.assertEqual(result.source_reference, "19.08.2026/DAM/2")
        self.assertEqual(
            result.artifact_url,
            "https://www.oree.com.ua/index.php/PXS/downloadxlsx/19.08.2026/DAM/2",
        )
        session.post.assert_called_once()
        _, kwargs = session.post.call_args
        self.assertEqual(session.post.call_args.args[0], RESULTS_URL)
        self.assertEqual(kwargs["data"], {"day": "19.08.2026"})
        self.assertEqual(kwargs["timeout"], 12)

    def test_returns_none_when_results_are_not_published(self):
        session = Mock()
        session.post.return_value = FakeResponse("Розрахунки не проводилися")

        result = OperatorMarketSource(session=session).discover(date(2026, 8, 19))

        self.assertIsNone(result)

    def test_rejects_artifact_for_a_different_date(self):
        session = Mock()
        session.post.return_value = FakeResponse(
            '<input class="hdata_link" value="18.08.2026/DAM/2">'
        )

        with self.assertRaisesRegex(ValueError, "does not match"):
            OperatorMarketSource(session=session).discover(date(2026, 8, 19))

    def test_rejects_unsafe_artifact_reference(self):
        session = Mock()
        session.post.return_value = FakeResponse(
            '<input class="hdata_link" value="19.08.2026/DAM/../secret">'
        )

        with self.assertRaisesRegex(ValueError, "unsafe"):
            OperatorMarketSource(session=session).discover(date(2026, 8, 19))

    def test_rejects_empty_success_response(self):
        session = Mock()
        session.post.return_value = FakeResponse("   ")

        with self.assertRaisesRegex(ValueError, "empty"):
            OperatorMarketSource(session=session).discover(date(2026, 8, 19))


if __name__ == "__main__":
    unittest.main()
