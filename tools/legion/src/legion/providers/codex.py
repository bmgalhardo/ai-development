"""Codex: `codex exec --json`, with a JSONL event stream in its log."""

import json

from .base import Provider, Result

FULL_ACCESS = ("--sandbox", "danger-full-access")


class Codex(Provider):
    name = "codex"
    executable = "codex"
    rank = 2
    moshi_agent = "codex"  # its name in Moshi's quota snapshots
    efforts = ("minimal", "low", "medium", "high", "xhigh")
    effort_flag = ("-c", 'model_reasoning_effort="{}"')
    base_flags = ("exec", "-c", 'approval_policy="never"', "--color", "never", "--json")
    role_flags = {"implement": FULL_ACCESS, "fix": FULL_ACCESS, "review": ("--sandbox", "read-only")}
    # Codex's own sandbox can't start in a container; there the read-only mounts are the reviewer's sandbox.
    # The container has no .git for the workflow folder, and no host config that trusts it.
    container_role_flags = {"review": FULL_ACCESS}
    container_flags = ("--skip-git-repo-check",)

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
