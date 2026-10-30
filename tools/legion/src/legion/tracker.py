"""The tracker: a project's cycles and issues, as Markdown in the workflow's scratch folder.

A project's cycles are in `.scratch/<project>/`, one folder per cycle, each issue
a file in its `issues/` with a `**Status:**` and a `**Blocked by:**` line.
"""

from pathlib import Path
import re

from pydantic import BaseModel

STATUS = re.compile(r"^\*\*Status:\*\*\s*(.+?)\s*$", re.M)
BLOCKED_BY = re.compile(r"^\*\*Blocked by:\*\*\s*(.+?)\s*$", re.M)


class TrackerError(Exception):
    """A tracker that can't be read: no project, no cycle, or an issue without a status."""


class Issue(BaseModel):
    number: str
    path: Path
    status: str
    blockers: list[str]

    @classmethod
    def read(cls, path):
        text = path.read_text(encoding="utf-8")
        status = STATUS.search(text)
        if not status:
            raise TrackerError(f"{path}: no **Status:** line")
        blocked = BLOCKED_BY.search(text)
        blockers = re.findall(r"\b(\d{2})\b", blocked[1]) if blocked else []
        return cls(number=path.name[:2], path=path, status=status[1], blockers=blockers)


class Cycle(BaseModel):
    path: Path
    issues: dict[str, Issue]

    @classmethod
    def read(cls, path):
        issues = [Issue.read(file) for file in sorted((path / "issues").glob("[0-9][0-9]-*.md"))]
        return cls(path=path, issues={issue.number: issue for issue in issues})

    @property
    def build(self):
        """The cycle's last issue, the build."""
        return list(self.issues.values())[-1] if self.issues else None

    def next_issue(self):
        """An issue left in progress (its worker died), then one in review, then the first ready one."""
        for status in ("in progress", "in review"):
            issue = next((issue for issue in self.issues.values() if issue.status == status), None)
            if issue:
                return issue
        return next((issue for issue in self.issues.values() if self.is_ready(issue)), None)

    def is_ready(self, issue):
        """Open with every blocker done; the build once every other issue is done or blocked."""
        if issue.status != "open":
            return False
        if issue.number == self.build.number:
            return all(other.status in ("done", "blocked") for other in self.issues.values() if other is not issue)
        return all(blocker in self.issues and self.issues[blocker].status == "done" for blocker in issue.blockers)

    def blockers(self, issue):
        """What the issue still waits for: its unfinished blockers; for the build, every unfinished issue."""
        if issue.number == self.build.number:
            return [other.number for other in self.issues.values()
                    if other is not issue and other.status not in ("done", "blocked")]
        return [number for number in issue.blockers
                if number not in self.issues or self.issues[number].status != "done"]


class Tracker:
    """A project's cycles, in the scratch folder under the project's folder name."""

    def __init__(self, folder):
        self.folder = folder

    @classmethod
    def for_project(cls, root, name):
        """The tracker of the project repo `name`, relative to the workflow root (`../<project>`)."""
        return cls(root / ".scratch" / cls.project(root, name).name)

    @staticmethod
    def project(root, name):
        """The project repo `name`, relative to the workflow root, checked to be a git repo."""
        project = (root / name).resolve()
        if not (project / ".git").exists():
            raise TrackerError(f"{project} is not a git repo")
        return project

    def cycle_paths(self):
        if not self.folder.is_dir():
            return []
        return sorted(path for path in self.folder.iterdir() if (path / "issues").is_dir())

    def current_cycle(self):
        """The oldest cycle with an issue ready or under way, so a cycle ticketed meanwhile waits;
        else the newest."""
        paths = self.cycle_paths()
        if not paths:
            raise TrackerError(f"No cycle with issues in {self.folder}")
        for path in paths:
            cycle = Cycle.read(path)
            if cycle.next_issue():
                return cycle
        return cycle
