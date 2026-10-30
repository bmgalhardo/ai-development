"""Claude Code: `claude -p`, with one JSON result in its log."""

from .base import Provider, Result


class Claude(Provider):
    name = "claude"
    rank = 1
    efforts = ("low", "medium", "high", "xhigh", "max")
    effort_flag = ("--effort", "{}")
    base_flags = ("-p", "--permission-mode", "auto", "--output-format", "json")
    role_flags = {"review": ("--disallowedTools=Edit,Write,NotebookEdit",)}
    resets = ("zoned", "clock")

    def session_flags(self, project):
        return ["--add-dir", str(project), "--max-budget-usd", f"{self.settings.budget_usd:g}"]

    def parse_log(self, log):
        messages, usage, report = [], [], ""
        for line in self.lines(log):
            if isinstance(line, str):
                messages.append(line)
            elif line.get("type") == "result":
                messages += [str(line.get("result", "")), *map(str, filter(None, [line.get("api_error")])),
                             *map(str, line.get("errors", []))]
                usage.append({key: line[key] for key in ("usage", "modelUsage", "total_cost_usd", "num_turns")
                              if key in line})
                if not line.get("is_error"):
                    report = str(line.get("result", ""))
        return Result(messages="\n".join(messages), usage=usage, report=report.strip())
