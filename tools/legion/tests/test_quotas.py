"""Quota readings from the usage endpoints, with a faked HTTP call: readings, refusals, logins, caching, privacy."""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from fastapi.testclient import TestClient

from legion.dashboard.app import create_app
from legion.dashboard.quotas import Quotas
from legion.providers import registry
from legion.providers.base import QuotaUnavailable
from legion.settings import Settings

CLAUDE_USAGE = {"five_hour": {"utilization": 24.0, "resets_at": "2026-10-29T14:59:59+00:00"},
                "seven_day": {"utilization": 11.0, "resets_at": "2026-11-03T23:59:59+00:00"},
                "seven_day_opus": None, "extra_usage": {"is_enabled": False}}
CODEX_USAGE = {"user_id": "private-user", "account_id": "private-account", "email": "private@example.com",
               "rate_limit": {"primary_window": {"used_percent": 44, "limit_window_seconds": 18000,
                                                 "reset_after_seconds": 4401, "reset_at": 1793286923},
                              "secondary_window": {"used_percent": 9, "limit_window_seconds": 604800,
                                                   "reset_after_seconds": 503821, "reset_at": 1793786344}}}


class Fetch:
    """A fake usage endpoint: each URL answers from a table; records what was asked."""

    def __init__(self, **answers):
        self.answers = answers
        self.calls = []

    def __call__(self, url, headers):
        self.calls.append((url, headers))
        answer = self.answers["claude" if "anthropic" in url else "codex"]
        if isinstance(answer, Exception):
            raise answer
        return answer


class QuotaTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        clean = {key: value for key, value in os.environ.items() if not key.upper().startswith("LEGION_")}
        with patch.dict(os.environ, clean, clear=True):
            self.settings = Settings(_env_file=None, logins=self.folder, preference=["claude", "codex"])
        self.claude = registry.provider("claude", self.settings)
        self.claude.credentials = self.folder / "credentials.json"
        self.codex = registry.provider("codex", self.settings)
        self.login("claude", expires_in=3600)
        self.login("codex")

    def login(self, name, expires_in=3600):
        if name == "claude":
            self.claude.credentials.write_text(json.dumps({"claudeAiOauth": {
                "accessToken": "claude-token", "expiresAt": (time.time() + expires_in) * 1000}}))
        else:
            (self.folder / ".codex.login").write_text(json.dumps({"tokens": {
                "access_token": "codex-token", "refresh_token": "codex-refresh", "account_id": "private-account"}}))

    def test_claude_reads_its_usage_endpoint_with_the_host_login(self):
        fetch = Fetch(claude=CLAUDE_USAGE)
        windows = self.claude.quota(fetch)
        self.assertEqual([(w.label, w.used_percent, w.resets_at) for w in windows],
                         [("5h", 24.0, "2026-10-29T14:59:59+00:00"), ("7d", 11.0, "2026-11-03T23:59:59+00:00")])
        url, headers = fetch.calls[0]
        self.assertEqual(url, "https://api.anthropic.com/api/oauth/usage")
        self.assertEqual(headers, {"Authorization": "Bearer claude-token", "anthropic-beta": "oauth-2025-04-20"})

    def test_codex_reads_its_usage_endpoint_with_the_workers_login(self):
        fetch = Fetch(codex=CODEX_USAGE)
        windows = self.codex.quota(fetch)
        self.assertEqual([(w.label, w.used_percent) for w in windows], [("5h", 44), ("7d", 9)])
        self.assertEqual(datetime.fromisoformat(windows[0].resets_at),
                         datetime.fromtimestamp(1793286923, timezone.utc))
        url, headers = fetch.calls[0]
        self.assertEqual(url, "https://chatgpt.com/backend-api/wham/usage")
        self.assertEqual(headers["Authorization"], "Bearer codex-token")
        self.assertEqual(headers["ChatGPT-Account-Id"], "private-account")

    def test_an_expired_claude_login_is_unavailable_without_calling(self):
        self.login("claude", expires_in=-60)
        fetch = Fetch(claude=CLAUDE_USAGE)
        with self.assertRaisesRegex(QuotaUnavailable, "login expired"):
            self.claude.quota(fetch)
        self.assertEqual(fetch.calls, [])

    def test_a_missing_login_is_unavailable(self):
        (self.folder / ".codex.login").unlink()
        with self.assertRaisesRegex(QuotaUnavailable, "no login"):
            self.codex.quota(Fetch(codex=CODEX_USAGE))

    def test_an_unreadable_login_is_unavailable(self):
        (self.folder / ".codex.login").chmod(0)
        self.addCleanup((self.folder / ".codex.login").chmod, 0o600)
        with self.assertRaisesRegex(QuotaUnavailable, "login unreadable"):
            self.codex.quota(Fetch(codex=CODEX_USAGE))

    def test_a_refusal_is_unavailable_with_its_status_only(self):
        refusal = HTTPError("https://chatgpt.com/backend-api/wham/usage", 401, "token expired", {}, None)
        with self.assertRaisesRegex(QuotaUnavailable, r"^usage endpoint refused \(401\)$"):
            self.codex.quota(Fetch(codex=refusal))

    def test_an_unexpected_answer_is_unavailable(self):
        for answer in ({"five_hour": {"utilization": "a lot"}}, {"five_hour": {"resets_at": "soon"}}, ["list"]):
            with self.subTest(answer=answer):
                with self.assertRaisesRegex(QuotaUnavailable, "unexpected"):
                    self.claude.quota(Fetch(claude=answer))

    def test_percentages_stay_within_range(self):
        windows = self.claude.quota(Fetch(claude={"five_hour": {"utilization": 130, "resets_at": None}}))
        self.assertEqual(windows[0].used_percent, 100)

    def test_reads_at_most_once_a_minute_and_serves_no_identity(self):
        fetch = Fetch(claude=CLAUDE_USAGE, codex=CODEX_USAGE)
        quotas = Quotas([self.claude, self.codex], fetch)
        first = quotas.read()
        self.assertEqual(quotas.read(), first)
        self.assertEqual(len(fetch.calls), 2)
        self.assertEqual([account["provider"] for account in first["accounts"]], ["claude", "codex"])
        self.assertFalse(first["accounts"][0]["stale"])
        served = json.dumps(first)
        for secret in ("private", "token", "refresh"):
            self.assertNotIn(secret, served)

    def test_a_failure_keeps_the_last_reading_and_says_why(self):
        fetch = Fetch(claude=CLAUDE_USAGE, codex=CODEX_USAGE)
        quotas = Quotas([self.claude], fetch)
        quotas.read()
        quotas.checked_at = None
        fetch.answers["claude"] = OSError("network down")
        account = quotas.read()["accounts"][0]
        self.assertEqual(account["error"], "usage endpoint unreachable")
        self.assertEqual(account["windows"][0]["used_percent"], 24.0)

    def test_an_old_reading_is_stale_and_no_reading_is_unavailable(self):
        quotas = Quotas([self.claude, self.codex], Fetch(claude=CLAUDE_USAGE, codex=QuotaUnavailable("no login")))
        accounts = quotas.read()["accounts"]
        self.assertEqual((accounts[1]["captured_at"], accounts[1]["stale"], accounts[1]["error"]),
                         (None, True, "no login"))
        quotas.accounts["claude"].captured_at = datetime.now(timezone.utc) - timedelta(minutes=4)
        self.assertTrue(quotas.accounts["claude"].public()["stale"])

    def test_panels_follow_the_preference(self):
        quotas = Quotas.for_settings(self.settings.model_copy(update={"preference": ["claude"]}))
        self.assertEqual([provider.name for provider in quotas.providers], ["claude"])

    def test_quota_endpoint_is_independent_of_board_and_not_cached_by_browser(self):
        reader = Mock()
        reader.read.return_value = {"accounts": [{"provider": "codex", "windows": []}], "error": None}
        with TestClient(create_app(self.folder, quotas=reader)) as client:
            response = client.get("/api/quotas")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.json()["accounts"][0]["provider"], "codex")


if __name__ == "__main__":
    unittest.main()
