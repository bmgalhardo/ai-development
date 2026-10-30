"""Codex: `codex exec --json`, with a JSONL event stream in its log."""

from datetime import datetime, timezone
import fcntl
import json

from .base import CONTAINER_HOME, ContainerLogin, Mount, Provider, QuotaWindow, Result

FULL_ACCESS = ("--sandbox", "danger-full-access")


class Codex(Provider):
    name = "codex"
    executable = "codex"
    rank = 2
    efforts = ("minimal", "low", "medium", "high", "xhigh")
    effort_flag = ("-c", 'model_reasoning_effort="{}"')
    base_flags = ("exec", "-c", 'approval_policy="never"', "--color", "never", "--json")
    role_flags = {"implement": FULL_ACCESS, "fix": FULL_ACCESS, "review": ("--sandbox", "read-only")}
    # Codex's own sandbox can't start in a container; there the read-only mounts are the reviewer's sandbox.
    # The container has no .git for the workflow folder, and no host config that trusts it.
    container_role_flags = {"review": FULL_ACCESS}
    container_flags = ("--skip-git-repo-check",)
    usage_url = "https://chatgpt.com/backend-api/wham/usage"
    login_file = ".codex.login"  # the workers' first login, in the logins folder; more are .codex-2.login, ...

    def read_event(self, event):
        kind = event.get("type")
        if kind in ("error", "turn.failed"):
            return Result(messages=json.dumps(event, ensure_ascii=False))
        if kind == "item.completed" and event.get("item", {}).get("type") == "agent_message":
            text = event["item"].get("text", "")
            return Result(messages=text, report=text)
        if kind == "turn.completed" and "usage" in event:
            return Result(usage=[event["usage"]])
        return None

    def read_quota(self, fetch):
        tokens = self.read_login(self.settings.logins_folder / self.login_file)["tokens"]
        usage = fetch(self.usage_url, {"Authorization": f"Bearer {tokens['access_token']}",
                                       "ChatGPT-Account-Id": tokens["account_id"], "User-Agent": "codex-cli"})
        limits = usage.get("rate_limit") or {}
        return [QuotaWindow(label=self.span(window["limit_window_seconds"]), used_percent=window["used_percent"],
                            resets_at=datetime.fromtimestamp(window["reset_at"], timezone.utc).isoformat())
                for key in ("primary_window", "secondary_window") if (window := limits.get(key))]

    def container_login(self):
        """A free login, locked for the container's life, else the first, waited for.

        Renewal replaces the refresh token, so one session at a time uses a login.
        It is mounted writable, so Codex saves renewed tokens to the host's file.
        """
        folder = self.settings.logins_folder
        first = folder / self.login_file
        if not first.is_file():
            raise FileNotFoundError(f"No {first}")
        held = wait_for = None
        for path in [first, *sorted(folder.glob(".codex-*.login"))]:
            held = path.open()
            try:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                held.close()
                held = None
        if held is None:
            path = wait_for = first
        return ContainerLogin(mounts=[Mount(host=path, target=CONTAINER_HOME / ".codex" / "auth.json", writable=True)],
                              sessions=CONTAINER_HOME / ".codex" / "sessions", held=held, wait_for=wait_for)

    @staticmethod
    def span(seconds):
        """A window's length as a label: 5h, 7d."""
        return f"{seconds // 86400}d" if seconds >= 86400 else f"{seconds // 3600}h"
