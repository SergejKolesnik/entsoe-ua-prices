"""Static safety checks for manually dispatched data backfills."""

import unittest
from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "refresh-market-data.yml"
)


class RefreshWorkflowTests(unittest.TestCase):
    def test_intraday_refresh_is_scheduled_and_uses_current_kyiv_quarter(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn('- cron: "25 17 * * *"', workflow)
        self.assertIn("- intraday", workflow)
        self.assertIn("inputs.task == 'intraday'", workflow)
        self.assertIn("github.event.schedule == '25 17 * * *'", workflow)
        self.assertIn("TZ: Europe/Kyiv", workflow)
        self.assertIn("python -m market_forecast.cli import-idm-quarter", workflow)
        self.assertIn("--allow-partial-quarter --write", workflow)
        self.assertIn('month=$(date +%-m)', workflow)
        self.assertNotIn("GOOGLE", workflow)

    def test_operator_refresh_retries_after_evening_gate_closes(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn('- cron: "55 18-23 * * *"', workflow)
        self.assertIn('- cron: "0 0 * * *"', workflow)
        self.assertIn("github.event.schedule == '55 18-23 * * *'", workflow)
        self.assertIn("github.event.schedule == '0 0 * * *'", workflow)
        self.assertIn('refresh-operator --date "${{ inputs.delivery_date }}"', workflow)

    def test_flow_backfill_is_bounded_and_secret_based(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("- backfill_flows", workflow)
        self.assertIn("inputs.task == 'backfill_flows'", workflow)
        self.assertIn("secrets.DATABASE_URL", workflow)
        self.assertIn("secrets.ENTSOE_TOKEN", workflow)
        self.assertIn("days > 14", workflow)
        self.assertIn("python -m market_forecast.cli backfill-flows", workflow)
        self.assertIn("--max-days 14", workflow)
        self.assertNotIn("database_url:\n", workflow.lower())
        self.assertNotIn("entsoe_token:\n", workflow.lower())


if __name__ == "__main__":
    unittest.main()
