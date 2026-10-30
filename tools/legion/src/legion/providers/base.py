"""What every provider shares: building a command, reading its log, failures and reset times, and its quota.

A provider is a subclass of `Provider` in its own file. Its data are class
attributes; it reads its own log events.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
import json
import re
from typing import ClassVar
from urllib.error import HTTPError
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ValidationError, field_validator

RESET_MARGIN = 30  # seconds after a reset before trying again


class Result(BaseModel):
    """What a session's log says: its diagnostic messages (never tool output), usage and final report."""

    messages: str = ""
    usage: list[dict] = []
    report: str = ""


class QuotaUnavailable(Exception):
    """No quota reading, with a reason safe to show: never a token or a raw response."""


class QuotaWindow(BaseModel):
    """One usage window of a provider's quota: its label (5h, 7d), percent used and reset time (ISO)."""

    label: str
    used_percent: float
    resets_at: str | None = None

    @field_validator("used_percent")
    @classmethod
    def within_range(cls, value):
        if value != value:  # NaN
            raise ValueError("not a percentage")
        return max(0, min(100, value))


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
    authentication_patterns: ClassVar[tuple[str, ...]] = (
        r"invalid_api_key", r"authentication[_ ](?:failed|required|error)", r"not logged in",
        r"failed to authenticate", r"(?:refresh|access|oauth)[_ ](?:token|session).*(?:expired|revoked)",
        r"401 Unauthorized")
    quota_patterns: ClassVar[tuple[str, ...]] = (
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
        if re.search("|".join(self.authentication_patterns), message, re.I):
            return "authentication"
        if re.search("|".join(self.quota_patterns), message, re.I):
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

    def quota(self, fetch):
        """The provider's quota windows, or QuotaUnavailable with a reason safe to show.

        `fetch(url, headers)` returns the endpoint's JSON. Logins are only read, never renewed.
        """
        try:
            return self.read_quota(fetch)
        except HTTPError as error:
            raise QuotaUnavailable(f"usage endpoint refused ({error.code})") from None
        except OSError:
            raise QuotaUnavailable("usage endpoint unreachable") from None
        except (KeyError, TypeError, AttributeError, ValidationError, ValueError):
            raise QuotaUnavailable("unexpected login or usage format") from None

    @abstractmethod
    def read_quota(self, fetch):
        """The provider's quota windows from its usage endpoint."""

    @staticmethod
    def read_login(path):
        """A login file's JSON; QuotaUnavailable when it is missing or unreadable."""
        try:
            return json.loads(path.read_text())
        except FileNotFoundError:
            raise QuotaUnavailable("no login") from None
        except OSError:
            raise QuotaUnavailable("login unreadable") from None

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
