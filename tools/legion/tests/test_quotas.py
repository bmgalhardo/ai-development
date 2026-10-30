"""Validate quota normalization, privacy, caching and failure behavior."""

import json
import subprocess
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from legion.dashboard.app import create_app
from legion.dashboard.quotas import Quotas, normalize


SNAPSHOTS = [
    {"agent": "codex", "accountId": "private-account", "accountLabel": "private@example.com",
     "hostName": "private-host", "capturedAt": "2026-01-01T00:00:00Z",
     "windows": [{"label": "5h", "usedPercentage": 11, "resetsAt": "2026-10-26T01:38:00Z"}]},
    {"agent": "claude-code", "windows": [{"label": "7d", "usedPercentage": 68}]},
]


class QuotaTests(unittest.TestCase):
    def test_serves_quota_windows_without_account_identity(self):
        accounts = normalize(SNAPSHOTS)
        self.assertEqual(accounts[0]["windows"], [{"label": "5h", "used_percent": 11,
                                                  "resets_at": "2026-10-26T01:38:00Z"}])
        self.assertEqual(accounts[1]["provider"], "claude")
        self.assertTrue(accounts[0]["stale"])
        self.assertTrue(accounts[1]["stale"])
        self.assertNotIn("private", json.dumps(accounts))

    @patch("legion.dashboard.quotas.subprocess.run")
    def test_polls_at_most_once_per_minute_and_never_syncs(self, run):
        run.return_value = Mock(stdout=json.dumps(SNAPSHOTS))
        reader = Quotas()
        first = reader.read()
        self.assertEqual(reader.read(), first)
        run.assert_called_once_with(["moshi-hook", "usage"], capture_output=True,
                                    text=True, timeout=30, check=True)

    @patch("legion.dashboard.quotas.subprocess.run")
    def test_retains_last_snapshot_as_stale_after_poll_failure(self, run):
        run.return_value = Mock(stdout=json.dumps(SNAPSHOTS))
        reader = Quotas()
        reader.read()
        reader.checked_at = None
        run.side_effect = subprocess.TimeoutExpired("moshi-hook", 30)
        failed = reader.read()
        self.assertEqual(failed["accounts"][0]["windows"][0]["used_percent"], 11)
        self.assertTrue(failed["accounts"][0]["stale"])
        self.assertIn("unavailable", failed["error"])

    @patch("legion.dashboard.quotas.subprocess.run", side_effect=FileNotFoundError)
    def test_missing_helper_reports_unavailable_without_inventing_usage(self, run):
        result = Quotas().read()
        self.assertEqual(result["accounts"], [])
        self.assertIn("not installed", result["error"])

    @patch("legion.dashboard.quotas.subprocess.run")
    def test_malformed_output_does_not_expose_raw_output(self, run):
        run.return_value = Mock(stdout="secret-provider-diagnostic")
        result = Quotas().read()
        self.assertEqual(result["accounts"], [])
        self.assertNotIn("secret", json.dumps(result))

    def test_unknown_providers_and_non_numeric_percentages_are_not_quotas(self):
        self.assertEqual(normalize([{"agent": "other"}]), [])
        accounts = normalize([{"agent": "codex", "windows": [{"usedPercentage": None},
                              {"usedPercentage": float("nan")}, {"usedPercentage": True}]}])
        self.assertEqual(accounts[0]["windows"], [])

    def test_quota_endpoint_is_independent_of_board_and_not_cached_by_browser(self):
        reader = Mock()
        reader.read.return_value = {"accounts": normalize(SNAPSHOTS), "error": None}
        with TestClient(create_app(quotas=reader)) as client:
            response = client.get("/api/quotas")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.json()["accounts"][0]["provider"], "codex")
