"""Open the public Streamlit app as a real browser session and wake it if needed."""

from __future__ import annotations

import os
import re
import sys
import time
from collections.abc import Iterable
from typing import Any

APP_URL = "https://rdn-market-intelligence-ua-v2.streamlit.app/"
APP_MARKER = "RDN Market Intelligence"
WAKE_BUTTON = re.compile(r"Yes, get this app back up!", re.IGNORECASE)


def browser_contexts(page: Any) -> Iterable[Any]:
    """Return the top-level page and all currently attached frames."""

    yield page
    yield from page.frames


def marker_is_visible(contexts: Iterable[Any]) -> bool:
    """Check whether the real dashboard marker is visible in any page context."""

    for context in contexts:
        try:
            if context.get_by_text(APP_MARKER, exact=False).first.is_visible():
                return True
        except Exception:
            # Frames can detach while Streamlit transitions from sleep to the app.
            continue
    return False


def click_wake_button(contexts: Iterable[Any]) -> bool:
    """Click Streamlit Community Cloud's wake button when it is visible."""

    for context in contexts:
        try:
            button = context.get_by_role("button", name=WAKE_BUTTON).first
            if button.is_visible():
                button.click()
                return True
        except Exception:
            continue
    return False


def wake_and_verify(page: Any, timeout_seconds: int = 180) -> str:
    """Wake the app if necessary and wait until its own UI is visible."""

    deadline = time.monotonic() + timeout_seconds
    wake_clicked = False

    while time.monotonic() < deadline:
        contexts = tuple(browser_contexts(page))
        if marker_is_visible(contexts):
            return "woke" if wake_clicked else "already_awake"

        if not wake_clicked and click_wake_button(contexts):
            wake_clicked = True
            print("Streamlit sleep screen detected; wake button clicked.", flush=True)

        page.wait_for_timeout(2_000)

    state = "after clicking the wake button" if wake_clicked else "without a wake button"
    raise TimeoutError(f"Dashboard marker was not visible within {timeout_seconds}s {state}.")


def main() -> int:
    """Run the browser keepalive check."""

    from playwright.sync_api import sync_playwright

    app_url = os.environ.get("STREAMLIT_APP_URL", APP_URL)
    timeout_seconds = int(os.environ.get("STREAMLIT_WAKE_TIMEOUT_SECONDS", "180"))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            page.goto(app_url, wait_until="domcontentloaded", timeout=90_000)
            outcome = wake_and_verify(page, timeout_seconds=timeout_seconds)
            print(f"Streamlit keepalive succeeded: {outcome}; url={app_url}")
        finally:
            browser.close()

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Streamlit keepalive failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
