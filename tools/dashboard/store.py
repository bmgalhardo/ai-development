"""Read snapshots of the local tracker and worker artifacts without changing them."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time

from tools.workers import next_issue


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def catalog(self):
        scratch = self.root / ".scratch"
        if not scratch.is_dir():
            return []
        return [
            {"project": project.name, "cycles": cycles}
            for project in sorted(scratch.iterdir()) if project.is_dir() and not project.is_symlink()
            if (cycles := [cycle.name for cycle in sorted(project.iterdir(), reverse=True)
                           if cycle.is_dir() and not cycle.is_symlink()
                           and (cycle / "issues").is_dir()])
        ]

    def cycle_path(self, project, cycle):
        entry = next((entry for entry in self.catalog() if entry["project"] == project), None)
        if entry is None or cycle not in entry["cycles"]:
            raise LookupError("Project or cycle not found")
        return self.root / ".scratch" / project / cycle

    def board(self, project, cycle):
        path = self.cycle_path(project, cycle)
        warnings = []
        try:
            issues = next_issue.read_issues(path)
            cards = [self.card(number, issue, issues) for number, issue in issues.items()]
        except (OSError, SystemExit) as error:
            raise ValueError("Issue files are being updated or cannot be read; retry shortly") from error
        directory = self.root / ".scratch" / project / "runner"
        current = read_json(directory / "current.json", [], warnings)
        history = read_history(path / "work" / "attempts.jsonl", warnings)
        cooldowns = read_json(self.root / ".scratch" / "runner" / "cooldowns.json", {}, warnings)
        if not isinstance(current, list) or not all(isinstance(row, dict) for row in current):
            warnings.append("Invalid current attempt snapshot")
            current = []
        if not isinstance(cooldowns, dict):
            warnings.append("Invalid cooldown snapshot")
            cooldowns = {}
        running = runner_active(directory / "runner.lock")
        for card in cards:
            card["reviews"] = read_reviews(path, card["number"])
            identity = str((path / "issues" / card["filename"]).relative_to(self.root))
            attempts = {row.get("attempt"): row for row in history if row.get("issue") == identity}
            attempts.update({row.get("attempt"): row for row in current if row.get("issue") == identity})
            card["attempts"] = [public_attempt(row, running, path / "work") for row in attempts.values()]
            card["total_attempt_seconds"] = sum(row["elapsed_seconds"] for row in card["attempts"])
            card["active_attempts"] = [row for row in card["attempts"] if row["active"]]
        selected_prefix = str(path.relative_to(self.root)) + "/issues/"
        active = [public_attempt(row, running, path / "work") for row in current
                  if str(row.get("issue", "")).startswith(selected_prefix) and not row.get("outcome")]
        return {"project": project, "cycle": cycle, "issues": cards, "warnings": warnings,
                "runner": {"active": running, "attempts": active,
                           "cooldowns": {provider: reset for provider, reset in cooldowns.items()
                                         if isinstance(reset, (int, float)) and reset > time.time()}},
                "updated_at": datetime.now(timezone.utc).isoformat()}

    def card(self, number, issue, issues):
        content = issue["path"].read_text(encoding="utf-8")
        heading = re.search(r"^#\s+(.+)$", content, re.M)
        # Ask the runner's selector about each open issue while keeping the full
        # dependency graph and the final build's position intact.
        candidates = {key: {**value, "status": value["status"] if key == number
                           or value["status"] in ("done", "blocked") else "waiting"}
                      for key, value in issues.items()}
        ready = issue["status"] == "open" and next_issue.next_issue(candidates) is not None
        stage = {"open": "ready" if ready else "waiting", "in progress": "implementing",
                 "in review": "reviewing", "done": "done", "blocked": "blocked"}.get(issue["status"], "blocked")
        build = issue is next_issue.build_issue(issues)
        blockers = [key for key, value in issues.items() if key != number
                    and value["status"] not in ("done", "blocked")] if build else [
                        key for key in issue["blockers"] if issues.get(key, {}).get("status") != "done"]
        progress = re.search(r"^## Progress\s*\n(.*?)(?=^## |\Z)", content, re.M | re.S)
        return {"number": number, "title": heading[1] if heading else issue["path"].stem,
                "filename": issue["path"].name, "status": issue["status"], "stage": stage,
                "blockers": blockers, "progress": progress[1].strip() if progress else "",
                "content": content}


def read_reviews(cycle, number):
    reports = []
    for axis in ("standards", "spec"):
        path = cycle / "reviews" / f"{number}-{axis}.md"
        try:
            content = path.read_text(encoding="utf-8")
            reviewer = re.search(r"^Reviewer:\s*(claude|codex)\b", content, re.M | re.I)
            reports.append({"axis": axis, "status": "available", "content": content,
                            "provider": reviewer[1].lower() if reviewer else None})
        except FileNotFoundError:
            reports.append({"axis": axis, "status": "missing", "content": "", "provider": None})
        except OSError:
            reports.append({"axis": axis, "status": "unreadable", "content": "", "provider": None})
    return reports


def read_json(path, default, warnings):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default
    except (OSError, ValueError):
        warnings.append(f"Could not read {path.name}; it may be updating")
        return default


def read_history(path, warnings):
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError:
        return []
    except OSError:
        warnings.append("Could not read attempt history")
        return []
    records = []
    for line in lines:
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                records.append(row)
        except ValueError:
            warnings.append("Incomplete attempt history record; retrying next refresh")
    return records


def runner_active(path):
    try:
        stat = path.stat()
    except FileNotFoundError:
        return False
    identity = f"{os.major(stat.st_dev):02x}:{os.minor(stat.st_dev):02x}:{stat.st_ino}"
    # Inspect Linux's lock table instead of acquiring even a temporary shared
    # lock, which could race a worker trying to claim its exclusive lock.
    return any(len(fields := line.split()) > 5 and fields[1] == "FLOCK"
               and fields[3] == "WRITE" and fields[5] == identity
               for line in Path("/proc/locks").read_text().splitlines())


def public_attempt(row, running, directory):
    active = running and not row.get("outcome")
    elapsed = row.get("duration_seconds", 0)
    if not row.get("outcome"):
        try:
            start = datetime.fromisoformat(row["started_at"]).timestamp()
            elapsed = max(0, time.time() - start) if active else 0
        except (KeyError, TypeError, ValueError):
            elapsed = 0
    log_age = None
    # Only inspect the local log's timestamp. Never serve native logs or recovery files.
    attempt = row.get("attempt", "")
    if isinstance(attempt, str) and Path(attempt).name == attempt:
        try:
            log_age = max(0, time.time() - (directory / f"{attempt}.log").stat().st_mtime)
        except OSError:
            pass
    return {key: row.get(key) for key in ("attempt", "role", "axis", "provider", "model", "started_at", "outcome")} | {
        "active": active, "elapsed_seconds": elapsed if isinstance(elapsed, (int, float)) else 0,
        "log_age_seconds": log_age}
