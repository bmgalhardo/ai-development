"""Each provider's quota, read from its usage endpoint at most once a minute.

Logins are only read, never renewed; tokens and account identity are never served.
The runner doesn't use these readings.
"""

from datetime import datetime, timezone
from threading import Lock
import time

from pydantic import BaseModel

from ..providers import registry
from ..providers.base import QuotaUnavailable, QuotaWindow
from ..utils import fetch_json

REFRESH = 60  # seconds between readings
STALE = 180  # seconds after which a reading is marked stale


class Account(BaseModel):
    """A provider's last successful reading, and why the latest attempt failed, if it did."""

    provider: str
    captured_at: datetime | None = None
    windows: list[QuotaWindow] = []
    error: str | None = None

    def public(self):
        """What the board shows: the windows, the reading's time and whether it is stale."""
        age = (datetime.now(timezone.utc) - self.captured_at).total_seconds() if self.captured_at else None
        return {"provider": self.provider, "captured_at": self.captured_at.isoformat() if self.captured_at else None,
                "stale": age is None or age > STALE, "windows": [window.model_dump() for window in self.windows],
                "error": self.error}


class Quotas:
    def __init__(self, providers, fetch=fetch_json):
        self.providers = providers
        self.fetch = fetch
        self.lock = Lock()
        self.checked_at = None
        self.accounts = {provider.name: Account(provider=provider.name) for provider in providers}

    @classmethod
    def for_settings(cls, settings):
        """The quotas of the providers in the preference."""
        return cls([registry.provider(name, settings) for name in settings.preference])

    def read(self):
        with self.lock:
            if self.checked_at is None or time.monotonic() - self.checked_at >= REFRESH:
                for provider in self.providers:
                    self.refresh(provider)
                self.checked_at = time.monotonic()
            return {"accounts": [account.public() for account in self.accounts.values()], "error": None}

    def refresh(self, provider):
        account = self.accounts[provider.name]
        try:
            account.windows = provider.quota(self.fetch)
            account.captured_at = datetime.now(timezone.utc)
            account.error = None
        except QuotaUnavailable as error:
            account.error = str(error)
