"""Notifications to the user's phone: Telegram messages, sent only.

Unconfigured, nothing is sent. A failed send is logged and never stops the run.
"""

import json
import urllib.request

from .utils import say

LIMIT = 4096  # Telegram's longest message, in characters


class Notifier:
    """Sends messages to one Telegram chat with a bot, when `LEGION_TELEGRAM_TOKEN` and `_CHAT_ID` are set."""

    def __init__(self, settings):
        self.token = settings.telegram_token.get_secret_value() if settings.telegram_token else None
        self.chat = settings.telegram_chat_id
        self.api = settings.telegram_api.rstrip("/")

    @property
    def enabled(self):
        return bool(self.token and self.chat)

    def send(self, text):
        """Send the text, cut to Telegram's limit; True when Telegram accepted it."""
        if not self.enabled:
            return False
        if len(text) > LIMIT:
            text = text[:LIMIT - 1] + "…"
        body = json.dumps({"chat_id": self.chat, "text": text, "disable_web_page_preview": True}).encode()
        request = urllib.request.Request(f"{self.api}/bot{self.token}/sendMessage", data=body,
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read()).get("ok", False)
        except (OSError, ValueError) as error:
            # The URL holds the token: report only the error's kind and reason.
            say(f"Telegram notification not sent: {type(error).__name__}: {getattr(error, 'reason', '')}")
            return False
