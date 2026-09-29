"""Read-only public feeds for the system-status dashboard panel."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urljoin

import requests


@dataclass(frozen=True, slots=True)
class SystemStatusItem:
    """One publicly reported system-status event or announcement."""

    source: str
    title: str
    published_at: datetime | None
    url: str


class _TelegramParser(HTMLParser):
    def __init__(self, channel: str) -> None:
        super().__init__(convert_charrefs=True)
        self.channel = channel
        self.items: list[SystemStatusItem] = []
        self._text_depth = 0
        self._text_parts: list[str] = []
        self._message_url: str | None = None
        self._published_at: datetime | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if tag == "br" and self._text_depth:
            self._text_parts.append(" ")
        if tag == "div" and "tgme_widget_message_text" in classes:
            self._text_depth = 1
            self._text_parts = []
        elif self._text_depth and tag == "div":
            self._text_depth += 1
        if tag == "a" and attributes.get("href", "").startswith("https://t.me/"):
            href = attributes["href"]
            if href.rstrip("/").rsplit("/", 1)[-1].isdigit():
                self._message_url = href
        if tag == "time" and attributes.get("datetime"):
            try:
                self._published_at = datetime.fromisoformat(
                    attributes["datetime"].replace("Z", "+00:00")
                )
            except ValueError:
                self._published_at = None

    def handle_data(self, data: str) -> None:
        if self._text_depth:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._text_depth or tag != "div":
            return
        self._text_depth -= 1
        if self._text_depth == 0:
            title = " ".join("".join(self._text_parts).split())
            if title and self._message_url:
                self.items.append(
                    SystemStatusItem(self.channel, title, self._published_at, self._message_url)
                )
            self._text_parts = []
            self._message_url = None
            self._published_at = None


def fetch_telegram_channel(
    channel: str,
    *,
    session: requests.Session | None = None,
    timeout_seconds: float = 15.0,
    limit: int = 8,
) -> list[SystemStatusItem]:
    """Fetch the public Telegram preview without authentication or mutation."""

    if not channel or not channel.replace("_", "").isalnum():
        raise ValueError("channel must be a Telegram public channel name")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    response = (session or requests.Session()).get(
        f"https://t.me/s/{channel}",
        timeout=timeout_seconds,
        headers={"User-Agent": "RDN-Market-Intelligence/1.0"},
    )
    response.raise_for_status()
    parser = _TelegramParser(channel)
    parser.feed(response.content.decode(response.encoding or "utf-8", errors="replace"))
    return parser.items[-limit:][::-1]
