"""Read snapshots of the local tracker and worker artifacts without changing them."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time

from ..providers import registry
from ..tracker import Cycle, TrackerError

AXES = ("standards", "spec")
STAGES = {"in progress": "implementing", "in review": "reviewing", "done": "done", "blocked": "blocked"}


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
        try:
            tracked = Cycle.read(path)
            cards = [self.card(issue, tracked) for issue in tracked.issues.values()]
        except (OSError, TrackerError) as error:
            raise ValueError("Issue files are being updated or cannot be read; retry shortly") from error
        artifacts = Artifacts(self.root, project, path)
        for card in cards:
            card["reviews"] = self.reviews(path, card["number"])
            artifacts.attach(card)
        return {"project": project, "cycle": cycle, "issues": cards, "warnings": artifacts.warnings,
                "runner": artifacts.runner(), "updated_at": datetime.now(timezone.utc).isoformat()}

    def card(self, issue, cycle):
        """An issue's card; its readiness and blockers follow the runner's tracker rules."""
        content = issue.path.read_text(encoding="utf-8")
        heading = re.search(r"^#\s+(.+)$", content, re.M)
        stage = ("ready" if cycle.is_ready(issue) else "waiting") if issue.status == "open" else \
            STAGES.get(issue.status, "blocked")
        progress = re.search(r"^## Progress\s*\n(.*?)(?=^## |\Z)", content, re.M | re.S)
        return {"number": issue.number, "title": heading[1] if heading else issue.path.stem,
                "filename": issue.path.name, "status": issue.status, "stage": stage,
                "blockers": cycle.blockers(issue), "progress": progress[1].strip() if progress else "",
                "content": content}

    @staticmethod
    def reviews(folder, number):
        """The issue's saved review reports in the cycle folder, with the reviewer each names."""
        names = "|".join(map(re.escape, registry.names()))
        reviewer = re.compile(rf"^Reviewer:\s*({names})\b", re.M | re.I)
        reports = []
        for axis in AXES:
            report = {"axis": axis, "status": "available", "content": "", "provider": None}
            try:
                report["content"] = (folder / "reviews" / f"{number}-{axis}.md").read_text(encoding="utf-8")
            except FileNotFoundError:
                report["status"] = "missing"
            except OSError:
                report["status"] = "unreadable"
            if found := reviewer.search(report["content"]):
                report["provider"] = found[1].lower()
            reports.append(report)
        return reports


class Artifacts:
    """The runner's files for one cycle, read once per board; unreadable parts become warnings."""

    def __init__(self, root, project, cycle):
        self.root = root
        self.cycle = cycle
        self.warnings = []
        directory = root / ".scratch" / project / "runner"
        self.running = self.lock_held(directory / "runner.lock")
        self.current = self.read_json(directory / "current.json", [])
        self.history = self.read_history(cycle / "work" / "attempts.jsonl")
        self.cooldowns = self.read_json(root / ".scratch" / "runner" / "cooldowns.json", {})
        if not isinstance(self.current, list) or not all(isinstance(row, dict) for row in self.current):
            self.warnings.append("Invalid current attempt snapshot")
            self.current = []
        if not isinstance(self.cooldowns, dict):
            self.warnings.append("Invalid cooldown snapshot")
            self.cooldowns = {}

    def attach(self, card):
        """Add the issue's attempts, finished and current, to its card."""
        identity = str((self.cycle / "issues" / card["filename"]).relative_to(self.root))
        attempts = {row.get("attempt"): row for row in self.history if row.get("issue") == identity}
        attempts.update({row.get("attempt"): row for row in self.current if row.get("issue") == identity})
        card["attempts"] = [self.public(row) for row in attempts.values()]
        card["total_attempt_seconds"] = sum(row["elapsed_seconds"] for row in card["attempts"])
        card["active_attempts"] = [row for row in card["attempts"] if row["active"]]

    def runner(self):
        """Whether a runner is alive, its unfinished attempts in this cycle, and the cooldowns still running."""
        prefix = str(self.cycle.relative_to(self.root)) + "/issues/"
        active = [self.public(row) for row in self.current
                  if str(row.get("issue", "")).startswith(prefix) and not row.get("outcome")]
        return {"active": self.running, "attempts": active,
                "cooldowns": {provider: reset for provider, reset in self.cooldowns.items()
                              if isinstance(reset, (int, float)) and reset > time.time()}}

    def public(self, row):
        """What the board shows of an attempt: never its native log or recovery files."""
        active = self.running and not row.get("outcome")
        elapsed = row.get("duration_seconds", 0)
        if not row.get("outcome"):
            try:
                start = datetime.fromisoformat(row["started_at"]).timestamp()
                elapsed = max(0, time.time() - start) if active else 0
            except (KeyError, TypeError, ValueError):
                elapsed = 0
        keys = ("attempt", "role", "axis", "provider", "model", "started_at", "outcome")
        return {key: row.get(key) for key in keys} | {
            "active": active, "elapsed_seconds": elapsed if isinstance(elapsed, (int, float)) else 0,
            "log_age_seconds": self.log_age(row.get("attempt", ""))}

    def log_age(self, attempt):
        """Seconds since the attempt's log last changed; only its timestamp is read."""
        if not isinstance(attempt, str) or Path(attempt).name != attempt:
            return None
        try:
            return max(0, time.time() - (self.cycle / "work" / f"{attempt}.log").stat().st_mtime)
        except OSError:
            return None

    def read_json(self, path, default):
        try:
            return json.loads(path.read_text())
        except FileNotFoundError:
            return default
        except (OSError, ValueError):
            self.warnings.append(f"Could not read {path.name}; it may be updating")
            return default

    def read_history(self, path):
        try:
            lines = path.read_text().splitlines()
        except FileNotFoundError:
            return []
        except OSError:
            self.warnings.append("Could not read attempt history")
            return []
        records = []
        for line in lines:
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    records.append(row)
            except ValueError:
                self.warnings.append("Incomplete attempt history record; retrying next refresh")
        return records

    @staticmethod
    def lock_held(path):
        """Whether a runner holds its lock, read from Linux's lock table.

        Acquiring even a temporary shared lock could race a worker claiming its exclusive lock.
        """
        try:
            stat = path.stat()
        except FileNotFoundError:
            return False
        identity = f"{os.major(stat.st_dev):02x}:{os.minor(stat.st_dev):02x}:{stat.st_ino}"
        return any(len(fields := line.split()) > 5 and fields[1] == "FLOCK"
                   and fields[3] == "WRITE" and fields[5] == identity
                   for line in Path("/proc/locks").read_text().splitlines())
