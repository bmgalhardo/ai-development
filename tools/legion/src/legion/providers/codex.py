"""Codex: `codex exec --json`, with a JSONL event stream in its log."""

import json

from .base import Provider, Result

FULL_ACCESS = ("--sandbox", "danger-full-access")


class Codex(Provider):
    name = "codex"
    rank = 2
    efforts = ("minimal", "low", "medium", "high", "xhigh")
    effort_flag = ("-c", 'model_reasoning_effort="{}"')
    base_flags = ("exec", "-c", 'approval_policy="never"', "--color", "never", "--json")
    role_flags = {"implement": FULL_ACCESS, "fix": FULL_ACCESS, "review": ("--sandbox", "read-only")}
    # Codex's own sandbox can't start in a container; there the read-only mounts are the reviewer's sandbox.
    # The container has no .git for the workflow folder, and no host config that trusts it.
    container_role_flags = {"review": FULL_ACCESS}
    container_flags = ("--skip-git-repo-check",)
    resets = ("dated", "clock")

    def parse_log(self, log):
        messages, usage, report = [], [], ""
        for line in self.lines(log):
            if isinstance(line, str):
                messages.append(line)
            elif line.get("type") in ("error", "turn.failed"):
                messages.append(json.dumps(line, ensure_ascii=False))
            elif line.get("type") == "item.completed" and line.get("item", {}).get("type") == "agent_message":
                report = line["item"].get("text", "")
                messages.append(report)
            elif line.get("type") == "turn.completed" and "usage" in line:
                usage.append(line["usage"])
        return Result(messages="\n".join(messages), usage=usage, report=report.strip())
