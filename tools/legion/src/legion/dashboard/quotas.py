"""Read local Moshi quota snapshots; never sync them or access credentials directly."""

from datetime import datetime
import json
import math
import subprocess
from threading import Lock
import time

from ..providers import registry


def provider_of(agent):
    """The registered provider whose Moshi agent name this is, or None."""
    return next((name for name in registry.names() if agent == registry.classes[name].moshi_agent), None)


def normalize(snapshots):
    if not isinstance(snapshots, list):
        raise ValueError("Expected quota snapshots")
    accounts = []
    for snapshot in snapshots:
        if not isinstance(snapshot, dict) or not provider_of(snapshot.get("agent")):
            continue
        windows = []
        for window in snapshot.get("windows", []):
            used = window.get("usedPercentage")
            if isinstance(used, bool) or not isinstance(used, (int, float)) or not math.isfinite(used):
                continue
            windows.append({"label": str(window.get("label", "Quota")),
                            "used_percent": max(0, min(100, used)),
                            "resets_at": window.get("resetsAt")})
        captured = snapshot.get("capturedAt")
        try:
            age = max(0, time.time() - datetime.fromisoformat(captured.replace("Z", "+00:00")).timestamp())
        except (AttributeError, ValueError, TypeError):
            age = None
        # Strip account IDs, email labels and host identity before serving LAN clients.
        accounts.append({"provider": provider_of(snapshot["agent"]), "captured_at": captured,
                         "stale": age is None or age > 180, "windows": windows})
    return accounts


class Quotas:
    def __init__(self, command="moshi-hook"):
        self.command = command
        self.lock = Lock()
        self.checked_at = None
        self.snapshot = {"accounts": [], "error": None, "source": "moshi-hook usage"}

    def read(self):
        with self.lock:
            if self.checked_at is not None and time.monotonic() - self.checked_at < 60:
                return self.snapshot
            try:
                result = subprocess.run([self.command, "usage"], capture_output=True,
                                        text=True, timeout=30, check=True)
                accounts = normalize(json.loads(result.stdout))
                self.snapshot = {"accounts": accounts, "error": None, "source": "moshi-hook usage"}
            except FileNotFoundError:
                self.failed("Moshi helper is not installed on this host")
            except (subprocess.SubprocessError, OSError, ValueError, TypeError, AttributeError):
                self.failed("Quota refresh unavailable; retrying in one minute")
            self.checked_at = time.monotonic()
            return self.snapshot

    def failed(self, message):
        self.snapshot = {**self.snapshot, "error": message,
                         "accounts": [{**account, "stale": True} for account in self.snapshot["accounts"]]}
