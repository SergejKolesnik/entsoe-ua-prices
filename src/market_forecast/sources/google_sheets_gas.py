"""Read-only transport for one Google Sheets worksheet CSV export."""

from __future__ import annotations

from urllib.parse import quote

import requests

from .base import RawResponse


class GoogleSheetsGasSource:
    """Fetch evaluated values from an explicitly configured worksheet."""

    def __init__(self, spreadsheet_id: str, timeout_seconds: float = 30.0) -> None:
        if not spreadsheet_id.strip() or not spreadsheet_id.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Invalid Google spreadsheet id")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.spreadsheet_id = spreadsheet_id
        self.timeout_seconds = timeout_seconds

    def fetch_worksheet(self, sheet_name: str) -> RawResponse:
        """Fetch one named worksheet as CSV without making any Sheet changes."""

        if not sheet_name.strip():
            raise ValueError("sheet_name must not be empty")
        url = (
            f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}/gviz/tq"
            f"?tqx=out:csv&sheet={quote(sheet_name, safe='')}"
        )
        response = requests.get(
            url,
            headers={"Accept": "text/csv", "User-Agent": "RDN-Market-Intelligence/1.0"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        if "text/csv" not in content_type.lower():
            raise ValueError("Google Sheets response is not CSV; check read access")
        return RawResponse(response.content, content_type, response.status_code, url)
