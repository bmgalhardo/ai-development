#!/usr/bin/env python3
"""Print the next issue a worker should take in the latest cycle, or nothing.

An issue left `in progress` comes first (its worker died). Otherwise the
first `open` issue whose `Blocked by` issues are all `done`; the last issue
(the build) is ready once every other issue is `done` or `blocked`.
See the workflow's context/issue-tracker.md. --status prints every issue's
status. The project is the git repo of the current directory.
"""

import argparse
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                           text=True, check=True).stdout.strip())
STATUS = re.compile(r"^\*\*Status:\*\*\s*(.+?)\s*$", re.M)
BLOCKED_BY = re.compile(r"^\*\*Blocked by:\*\*\s*(.+?)\s*$", re.M)


def latest_cycle():
    cycles = sorted(p for p in (ROOT / ".scratch").iterdir() if (p / "issues").is_dir())
    if not cycles:
        sys.exit("No cycle with issues in .scratch/")
    return cycles[-1]


def read_issues(cycle):
    issues = {}
    for path in sorted((cycle / "issues").glob("[0-9][0-9]-*.md")):
        text = path.read_text(encoding="utf-8")
        status = STATUS.search(text)
        if not status:
            sys.exit(f"{path}: no **Status:** line")
        blocked = BLOCKED_BY.search(text)
        blockers = re.findall(r"\b(\d{2})\b", blocked.group(1)) if blocked else []
        issues[path.name[:2]] = {"path": path, "status": status.group(1), "blockers": blockers}
    return issues


def next_issue(issues):
    for issue in issues.values():
        if issue["status"] == "in progress":
            return issue
    numbers = list(issues)
    build = numbers[-1]
    for number in numbers:
        issue = issues[number]
        if issue["status"] != "open":
            continue
        if number == build:
            others = [issues[n]["status"] for n in numbers[:-1]]
            if all(s in ("done", "blocked") for s in others):
                return issue
            continue
        if all(issues.get(b, {}).get("status") == "done" for b in issue["blockers"]):
            return issue
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true", help="list every issue's status")
    args = parser.parse_args()
    issues = read_issues(latest_cycle())
    if args.status:
        for number, issue in issues.items():
            print(f"{number}  {issue['status']:12s} {issue['path'].name}")
        return
    issue = next_issue(issues)
    if issue:
        print(issue["path"].relative_to(ROOT))


if __name__ == "__main__":
    main()
