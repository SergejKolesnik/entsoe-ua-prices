import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import Mock

from market_forecast.sources import NbuExchangeRateSource


class NbuSourceTests(unittest.TestCase):
    def test_parses_official_eur_range(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [
            {"cc": "EUR", "exchangedate": "18.08.2026", "rate_per_unit": 51.8082}
        ]
        session = Mock()
        session.get.return_value = response

        rates = NbuExchangeRateSource(session=session).fetch_eur_rates(
            date(2026, 8, 18), date(2026, 8, 18)
        )

        self.assertEqual(rates, {date(2026, 8, 18): Decimal("51.8082")})
        _, kwargs = session.get.call_args
        self.assertEqual(kwargs["params"]["valcode"], "eur")

