"""The L0 map: `L0.md` in the store, fetched for a session start and cached for when the store is away.

Its repo table is also the list `overmind memory repos` prints: the rows whose last column is a host and a repo,
like ``Forgejo `owner/repo` `` or ``GitHub `owner/repo` ``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import re

from .profiles import Profile
from .store import GITHUB_PREFIX, ForgejoRepo, StoreError

FILE = "L0.md"
REMOTE = re.compile(r"(Forgejo|GitHub)\b[^`]*`([^`]+)`")


@dataclass
class TableRepo:
    """A repo the L0 names: its `-r` reference and what it is."""

    ref: str
    description: str


def fetch(profile: Profile) -> tuple[str, datetime | None]:
    """The store's L0, saved to the cache; when the store can't be read, the cached copy and its time."""
    cache = profile.cache / FILE
    try:
        text = ForgejoRepo(profile.api, profile.token, profile.ca).read(FILE).decode()
    except StoreError:
        if cache.is_file():
            return cache.read_text(), datetime.fromtimestamp(cache.stat().st_mtime)
        raise
    cache.parent.mkdir(parents=True, exist_ok=True)
    partial = cache.with_suffix(".tmp")
    partial.write_text(text)
    partial.replace(cache)
    return text, None


def for_session(profile: Profile) -> str:
    """What a session start adds: the L0, a note when it comes from the cache, or nothing when memory is off.

    Never raises: a session must start even when the store, the cache and the network are all gone.
    """
    if not profile.set_up:
        return ""
    try:
        text, cached = fetch(profile)
    except Exception:  # noqa: BLE001 - nothing may stop a session start
        return f"(context store '{profile.name}' unreachable and no cached L0)"
    if cached:
        return f"(context store '{profile.name}' unreachable: cached L0 from {cached:%Y-%m-%d %H:%M})\n{text}"
    return text


def hook_output(text: str) -> str:
    """The SessionStart hook's JSON for Claude Code and Codex; empty when there is nothing to add."""
    if not text:
        return ""
    return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}})


def table(text: str) -> list[TableRepo]:
    """The repos in the L0's table, in order."""
    repos = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        match = REMOTE.search(cells[-1]) if len(cells) >= 3 else None
        if match:
            prefix = GITHUB_PREFIX if match.group(1) == "GitHub" else ""
            repos.append(TableRepo(prefix + match.group(2), cells[-2]))
    return repos
