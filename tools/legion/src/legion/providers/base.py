"""What every provider shares: building a command, reading its log, and reading failures and reset times.

A provider is a subclass of `Provider` in its own file. Its data are class
attributes; it reads its own log events.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
import json
import re
from typing import ClassVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel

RESET_MARGIN = 30  # seconds after a reset before trying again


class Result(BaseModel):
    """What a session's log says: its diagnostic messages (never tool output), usage and final report."""

    messages: str = ""
    usage: list[dict] = []
    report: str = ""


class Reset:
    """The reset-time formats limit messages use; each returns a datetime, or None if absent or invalid."""

    @staticmethod
    def dated(message, now):
        """'try again at Oct 25th, 2026 4:52 PM', in local time."""
        match = re.search(r"try again at ([A-Z][a-z]{2} \d{1,2}(?:st|nd|rd|th)?, \d{4} \d{1,2}:\d{2} [AP]M)",
                          message, re.I)
        if not match:
            return None
        value = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", match[1], flags=re.I)
        try:
            reset = datetime.strptime(value, "%b %d, %Y %I:%M %p").replace(tzinfo=now.tzinfo)
        except ValueError:
            return None
        return reset if reset > now else None

    @staticmethod
    def clock(message, now):
        """'try again at 4:52 AM', the next such local time."""
        match = re.search(r"try again at (\d{1,2}:\d{2} [AP]M)\b", message, re.I)
        if not match:
            return None
        try:
            return Reset.next_time(now, datetime.strptime(match[1].upper(), "%I:%M %p"))
        except ValueError:
            return None

    @staticmethod
    def zoned(message, now):
        """'resets 4pm (Europe/Lisbon)', the next such time in that zone."""
        match = re.search(r"resets\s+(\d{1,2}(?::\d{2})?\s*[ap]m)\s*\(([^)]+)\)", message, re.I)
        if not match:
            return None
        try:
            value = match[1].replace(" ", "").upper()
            clock = datetime.strptime(value, "%I:%M%p" if ":" in value else "%I%p")
            return Reset.next_time(now.astimezone(ZoneInfo(match[2])), clock)
        except (ValueError, ZoneInfoNotFoundError):
            return None

    @staticmethod
    def next_time(now, clock):
        """The next moment after `now`, in its zone, at the clock's hour and minute."""
        reset = now.replace(hour=clock.hour, minute=clock.minute, second=0, microsecond=0)
        return reset + timedelta(days=1) if reset <= now else reset


class Provider(ABC):
    name: ClassVar[str]
    executable: ClassVar[str]
    rank: ClassVar[int]  # the default preference order, lowest first
    efforts: ClassVar[tuple[str, ...]]
    effort_flag: ClassVar[tuple[str, ...]]  # each part formatted with the effort
    base_flags: ClassVar[tuple[str, ...]] = ()
    role_flags: ClassVar[dict[str, tuple[str, ...]]] = {}
    container_flags: ClassVar[tuple[str, ...]] = ()
    container_role_flags: ClassVar[dict[str, tuple[str, ...]]] = {}  # replace role_flags in a container
    model_flag: ClassVar[str] = "--model"
    # Limit and login wording both CLIs use; a provider may add its own.
    authentication: ClassVar[tuple[str, ...]] = (
        r"invalid_api_key", r"authentication[_ ](?:failed|required|error)", r"not logged in",
        r"failed to authenticate", r"(?:refresh|access|oauth)[_ ](?:token|session).*(?:expired|revoked)",
        r"401 Unauthorized")
    quota: ClassVar[tuple[str, ...]] = (
        r"usage_limit_reached", r"rate_limit_exceeded", r"rate_limit_error",
        r"you(?:['’]ve| have) (?:hit|reached) your (?:(?:usage|session|weekly) )?limit",
        r"(?:usage|session|weekly) limit (?:reached|exceeded)", r"rate limit (?:reached|exceeded)",
        r"too many requests", r"429 Too Many Requests")
    resets: ClassVar[tuple] = (Reset.dated, Reset.clock, Reset.zoned)  # tried in order

    def __init__(self, settings):
        self.settings = settings

    def command(self, role, prompt, project):
        """The CLI command for a session in a role (implement, review or fix) on the project."""
        settings = self.settings.role(self.name, role)
        command = [self.executable, *self.base_flags, *self.session_flags(project), *self.flags_for(role)]
        if settings.model:
            command += [self.model_flag, settings.model]
        command += [part.format(settings.effort) for part in self.effort_flag]
        return command + [prompt]

    def flags_for(self, role):
        if self.settings.container:
            return [*self.container_role_flags.get(role, self.role_flags.get(role, ())), *self.container_flags]
        return list(self.role_flags.get(role, ()))

    def session_flags(self, project):
        """Flags that depend on the project or the settings; none by default."""
        return []

    def classify(self, message):
        """A failure's kind from the session's messages: authentication, quota or failure."""
        if re.search("|".join(self.authentication), message, re.I):
            return "authentication"
        if re.search("|".join(self.quota), message, re.I):
            return "quota"
        return "failure"

    def reset_at(self, message, fallback, now=None):
        """When to try again after a limit, in Unix seconds; `fallback` seconds from now if no format matches."""
        now = now or datetime.now().astimezone()
        for reset_format in self.resets:
            reset = reset_format(message, now)
            if reset:
                return reset.timestamp() + RESET_MARGIN
        return now.timestamp() + fallback

    def parse_log(self, log):
        """The session's Result: text lines are diagnostics; the provider reads its JSON events."""
        messages, usage, report = [], [], ""
        for line in self.lines(log):
            event = Result(messages=line) if isinstance(line, str) else self.read_event(line)
            if event:
                messages += filter(None, [event.messages])
                usage += event.usage
                report = event.report or report
        return Result(messages="\n".join(messages), usage=usage, report=report.strip())

    @abstractmethod
    def read_event(self, event):
        """A log event's part of the Result, or None for an event that doesn't matter."""

    def read_quota(self):
        """The provider's quota reading. Filled by the quota ticket."""
        raise NotImplementedError

    def container_login(self):
        """The login and session folder a container needs. Filled by the containers ticket."""
        raise NotImplementedError

    @staticmethod
    def lines(log):
        """Each line of a log: a JSON object as a dict, anything else as text."""
        for line in log.read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                yield line
                continue
            if isinstance(event, dict):
                yield event
