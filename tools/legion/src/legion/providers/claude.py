"""Claude Code: `claude -p`, with one JSON result in its log."""

from .base import Provider, Result


class Claude(Provider):
    name = "claude"
    executable = "claude"
    rank = 1
    moshi_agent = "claude-code"  # its name in Moshi's quota snapshots
    efforts = ("low", "medium", "high", "xhigh", "max")
    effort_flag = ("--effort", "{}")
    base_flags = ("-p", "--permission-mode", "auto", "--output-format", "json")
    role_flags = {"review": ("--disallowedTools=Edit,Write,NotebookEdit",)}

    def session_flags(self, project):
        return ["--add-dir", str(project), "--max-budget-usd", f"{self.settings.budget_usd:g}"]

    def read_event(self, event):
        if event.get("type") != "result":
            return None
        result = str(event.get("result", ""))
        errors = [str(event["api_error"])] if event.get("api_error") else []
        usage = {key: event[key] for key in ("usage", "modelUsage", "total_cost_usd", "num_turns") if key in event}
        return Result(messages="\n".join([result, *errors, *map(str, event.get("errors", []))]),
                      usage=[usage], report="" if event.get("is_error") else result)
