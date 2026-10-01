"""Send the previous day's anonymous usage summary to Telegram."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


APP_LABELS = {
    "rdn-market-intelligence": "RDN Market Intelligence",
    "skygrid-solar": "SkyGrid Solar",
}


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _previous_day_bounds(timezone_name: str) -> tuple[date, datetime, datetime]:
    local_zone = ZoneInfo(timezone_name)
    today = datetime.now(local_zone).date()
    report_day = today - timedelta(days=1)
    start_local = datetime.combine(report_day, time.min, tzinfo=local_zone)
    end_local = start_local + timedelta(days=1)
    return report_day, start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _query_posthog(
    *, host: str, project_id: str, api_key: str, start: datetime, end: datetime
) -> dict[str, object]:
    start_text = start.strftime("%Y-%m-%d %H:%M:%S")
    end_text = end.strftime("%Y-%m-%d %H:%M:%S")
    query = f"""
SELECT
    properties.app_name AS app_name,
    count() AS views,
    count(DISTINCT distinct_id) AS visitors
FROM events
WHERE event = '$pageview'
  AND timestamp >= toDateTime('{start_text}')
  AND timestamp < toDateTime('{end_text}')
  AND properties.app_name IN ('rdn-market-intelligence', 'skygrid-solar')
GROUP BY app_name
ORDER BY app_name
""".strip()
    payload = json.dumps(
        {
            "query": {"kind": "HogQLQuery", "query": query},
            "name": "daily two-app usage report",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{host.rstrip('/')}/api/projects/{project_id}/query/",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"PostHog query failed with HTTP {error.code}: {body}") from error


def _rows(response: dict[str, object]) -> dict[str, tuple[int, int]]:
    columns = response.get("columns")
    results = response.get("results")
    if not isinstance(columns, list) or not isinstance(results, list):
        raise RuntimeError("PostHog query response has no tabular results")

    column_names = [str(column) for column in columns]
    try:
        app_index = column_names.index("app_name")
        views_index = column_names.index("views")
        visitors_index = column_names.index("visitors")
    except ValueError as error:
        raise RuntimeError("PostHog response is missing expected usage columns") from error

    parsed: dict[str, tuple[int, int]] = {}
    for row in results:
        if not isinstance(row, list) or len(row) <= max(app_index, views_index, visitors_index):
            raise RuntimeError("PostHog query returned a malformed row")
        app_name = str(row[app_index])
        if app_name in APP_LABELS:
            parsed[app_name] = (int(row[views_index] or 0), int(row[visitors_index] or 0))
    return parsed


def _message(report_day: date, usage: dict[str, tuple[int, int]]) -> str:
    lines = [f"📊 Відвідування застосунків за {report_day:%d.%m.%Y}", ""]
    total_views = 0
    total_visitors = 0
    for app_name, label in APP_LABELS.items():
        views, visitors = usage.get(app_name, (0, 0))
        total_views += views
        total_visitors += visitors
        lines.extend([f"{label}", f"• перегляди: {views}", f"• унікальні відвідувачі: {visitors}", ""])
    lines.extend([f"Разом переглядів: {total_views}", f"Разом унікальних відвідувачів: {total_visitors}"])
    return "\n".join(lines)


def _send_telegram(*, bot_token: str, chat_id: str, message: str) -> None:
    payload = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Telegram request failed with HTTP {error.code}: {body}") from error
    if not result.get("ok"):
        raise RuntimeError("Telegram rejected the daily usage report")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print the report without sending it")
    args = parser.parse_args()

    timezone_name = os.environ.get("REPORT_TIMEZONE", "Europe/Kyiv")
    report_day, start, end = _previous_day_bounds(timezone_name)
    response = _query_posthog(
        host=os.environ.get("POSTHOG_HOST", "https://eu.i.posthog.com"),
        project_id=_required("POSTHOG_PROJECT_ID"),
        api_key=_required("POSTHOG_PERSONAL_API_KEY"),
        start=start,
        end=end,
    )
    message = _message(report_day, _rows(response))
    if args.dry_run:
        print(message)
        return
    _send_telegram(
        bot_token=_required("TELEGRAM_BOT_TOKEN"),
        chat_id=_required("TELEGRAM_CHAT_ID"),
        message=message,
    )


if __name__ == "__main__":
    main()
