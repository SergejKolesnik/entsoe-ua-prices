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
