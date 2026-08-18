import unittest
from datetime import date, datetime, timezone
from unittest.mock import Mock

from market_forecast.domain import SourceObservation
from market_forecast.sources.operator_market import (
    DOWNLOAD_BASE_URL,
    OperatorMarketSource,
    RESULTS_URL,
)


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

    def test_downloads_only_validated_operator_url(self):
        session = Mock()
        response = Mock(
            content=b"PK\x03\x04xlsx-bytes",
            status_code=200,
            headers={"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        )
        session.get.return_value = response
        source = OperatorMarketSource(session=session)
        observation = SourceObservation(
            source="operator_market",
            delivery_date=date(2026, 8, 19),
            artifact_url=f"{DOWNLOAD_BASE_URL}/19.08.2026/DAM/result.xlsx",
            discovered_at=datetime.now(timezone.utc),
            source_reference="19.08.2026/DAM/result.xlsx",
        )

        raw = source.download(observation)

        self.assertEqual(raw.content, b"PK\x03\x04xlsx-bytes")
        session.get.assert_called_once_with(observation.artifact_url, timeout=30.0)
        response.raise_for_status.assert_called_once()


if __name__ == "__main__":
    unittest.main()
