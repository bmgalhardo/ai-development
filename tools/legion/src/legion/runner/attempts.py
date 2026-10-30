"""A cycle's attempts: each session's record, its log and, when unfinished, its recovery snapshot."""

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel


class Attempt(BaseModel):
    """One session's record in `attempts.jsonl`; the last five fields are set when it ends."""

    attempt: str
    issue: str  # the issue file, relative to the workflow root
    role: str
    axis: str | None = None
    provider: str
    model: str
    effort: str
    review_model: str
    started_at: str
    log: str
    exit_code: int | None = None
    outcome: str | None = None
    duration_seconds: float | None = None
    usage: list = []
    recovery: str | None = None

    @property
    def log_path(self):
        return Path(self.log)

    def record(self):
        """The record as written: only the fields set so far, in today's order."""
        return self.model_dump(exclude_unset=True)


class AttemptLog:
    """`<cycle>/work/`: attempts.jsonl, each attempt's log and recovery snapshots."""

    def __init__(self, cycle, root):
        self.folder = cycle / "work"
        self.folder.mkdir(exist_ok=True)
        self.root = root
        self.history = self.folder / "attempts.jsonl"

    def new(self, issue, role, provider, settings, axis=None):
        name = f"{issue.stem}-{axis or role}-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"
        role_settings = settings.role(provider, role)
        return Attempt(attempt=name, issue=str(issue.relative_to(self.root)), role=role, axis=axis,
                       provider=provider, model=role_settings.model or "CLI default", effort=role_settings.effort,
                       review_model=settings.role(provider, "review").model or "inherited",
                       started_at=datetime.now(timezone.utc).isoformat(), log=str(self.folder / f"{name}.log"))

    def recovery(self, attempt):
        return self.folder / f"{attempt.attempt}-recovery"

    def append(self, attempt):
        with self.history.open("a") as output:
            output.write(json.dumps(attempt.record()) + "\n")

    def implementer(self, issue):
        """The provider of the issue's last implement attempt, or None."""
        identity = str(issue.relative_to(self.root))
        provider = None
        for line in self.history.read_text().splitlines() if self.history.exists() else []:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("issue") == identity and row.get("role") == "implement":
                provider = row.get("provider")
        return provider
