import unittest
from unittest.mock import Mock

from market_forecast.sources.system_status import fetch_telegram_channel


class SystemStatusSourceTests(unittest.TestCase):
    def test_fetch_telegram_channel_parses_public_messages(self):
        response = Mock()
        response.encoding = "utf-8"
        response.content = '''
        <div class="tgme_widget_message">
          <a href="https://t.me/ukrenergo/123"></a>
          <time datetime="2026-09-29T08:30:00+00:00"></time>
          <div class="tgme_widget_message_text">Блок повернуто в роботу<br>після ремонту</div>
        </div>
        '''.encode("utf-8")
        response.raise_for_status = Mock()
        session = Mock()
        session.get.return_value = response

        items = fetch_telegram_channel("ukrenergo", session=session)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Блок повернуто в роботу після ремонту")
        self.assertEqual(items[0].url, "https://t.me/ukrenergo/123")
        response.raise_for_status.assert_called_once_with()

    def test_rejects_invalid_channel_name(self):
        with self.assertRaises(ValueError):
            fetch_telegram_channel("ukrenergo/123")


if __name__ == "__main__":
    unittest.main()
