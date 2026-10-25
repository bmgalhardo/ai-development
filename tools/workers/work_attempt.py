"""Read provider results and preserve unfinished work without changing the repo."""

from datetime import datetime, timedelta
import json
import re
import subprocess
import tarfile
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def read_result(log):
    """Ignore tool output when diagnosing limits; keep native usage units."""
    messages, usage = [], []
    for line in log.read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            messages.append(line)
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        if kind in ("error", "turn.failed"):
            messages.append(json.dumps(event, ensure_ascii=False))
        elif kind == "result":
            messages.append(str(event.get("result", "")))
            if event.get("api_error"):
                messages.append(str(event["api_error"]))
            messages.extend(str(error) for error in event.get("errors", []))
            usage.append({key: event[key] for key in
                          ("usage", "modelUsage", "total_cost_usd", "num_turns") if key in event})
        elif kind == "item.completed" and event.get("item", {}).get("type") == "agent_message":
            messages.append(event["item"].get("text", ""))
        elif kind == "turn.completed" and "usage" in event:
            usage.append(event["usage"])
    return "\n".join(messages), usage


def final_message(log):
    """The session's last reply: Claude's successful result, or Codex's last agent message."""
    final = ""
    for line in log.read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "result" and not event.get("is_error"):
            final = str(event.get("result", ""))
        elif event.get("type") == "item.completed" and event.get("item", {}).get("type") == "agent_message":
            final = event["item"].get("text", "")
    return final.strip()


def failure_kind(message):
    if re.search(r"invalid_api_key|authentication[_ ](?:failed|required|error)|not logged in|"
                 r"(?:refresh|access|oauth)[_ ]token.*(?:expired|revoked)|401 Unauthorized", message, re.I):
        return "authentication"
    if re.search(r"usage_limit_reached|rate_limit_exceeded|rate_limit_error|"
                 r"you(?:['’]ve| have) (?:hit|reached) your (?:(?:usage|session|weekly) )?limit|"
                 r"(?:usage|session|weekly) limit (?:reached|exceeded)|"
                 r"rate limit (?:reached|exceeded)|too many requests|429 Too Many Requests", message, re.I):
        return "quota"
    return "failure"


def retry_at(message, fallback, now=None):
    now = now or datetime.now().astimezone()
    match = re.search(r"try again at ([A-Z][a-z]{2} \d{1,2}(?:st|nd|rd|th)?, \d{4} \d{1,2}:\d{2} [AP]M)", message, re.I)
    if match:
        value = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", match[1], flags=re.I)
        try:
            reset = datetime.strptime(value, "%b %d, %Y %I:%M %p").replace(tzinfo=now.tzinfo)
            if reset > now:
                return reset.timestamp() + 30
        except ValueError:
            pass
    match = re.search(r"try again at (\d{1,2}:\d{2} [AP]M)\b", message, re.I)
    if match:
        try:
            clock = datetime.strptime(match[1].upper(), "%I:%M %p")
            reset = now.replace(hour=clock.hour, minute=clock.minute, second=0, microsecond=0)
            if reset <= now:
                reset += timedelta(days=1)
            return reset.timestamp() + 30
        except ValueError:
            pass
    match = re.search(r"resets\s+(\d{1,2}(?::\d{2})?\s*[ap]m)\s*\(([^)]+)\)", message, re.I)
    if match:
        try:
            local = now.astimezone(ZoneInfo(match[2]))
            value = match[1].replace(" ", "").upper()
            clock = datetime.strptime(value, "%I:%M%p" if ":" in value else "%I%p")
            reset = local.replace(hour=clock.hour, minute=clock.minute, second=0, microsecond=0)
            if reset <= local:
                reset += timedelta(days=1)
            return reset.timestamp() + 30
        except (ValueError, ZoneInfoNotFoundError):
            pass
    return now.timestamp() + fallback


def git(game, *args):
    return subprocess.check_output(["git", "-C", str(game), *args])


def snapshot(game, issue, directory):
    """Save tracked edits, untracked files and issue state, including failing work."""
    directory.mkdir()
    (directory / "HEAD").write_bytes(git(game, "rev-parse", "HEAD"))
    (directory / "status.txt").write_bytes(git(game, "status", "--porcelain"))
    (directory / "changes.patch").write_bytes(git(game, "diff", "--binary", "HEAD"))
    (directory / "index.patch").write_bytes(git(game, "diff", "--binary", "--cached"))
    (directory / "issue.md").write_bytes(issue.read_bytes())
    paths = git(game, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
    with tarfile.open(directory / "untracked.tar", "w") as archive:
        for path in filter(None, paths):
            name = path.decode("utf-8", errors="surrogateescape")
            archive.add(game / name, arcname=name, recursive=False)
