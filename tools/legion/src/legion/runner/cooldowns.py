"""Provider cooldowns: when each provider's quota resets, kept across restarts."""

import json

from ..utils import save_json


class Cooldowns:
    """Reset times in Unix seconds, shared by every project's runner: a provider's quota is per account."""

    def __init__(self, path):
        self.path = path
        self.until = json.loads(path.read_text()) if path.exists() else {}

    def set(self, provider, until):
        self.until[provider] = until
        self.path.parent.mkdir(parents=True, exist_ok=True)
        save_json(self.path, self.until)
