"""Profiles: which context store this machine uses, and how to reach it. The only reader of the environment.

A profile is a folder `~/.config/overmind/memory/<name>/` with `env` (`OVERMIND_MEMORY_API`, optional `OVERMIND_MEMORY_CA`) and
`token`, both mode 600 and never in git. The active profile is `$OVERMIND_MEMORY_PROFILE`, else the name in
`~/.config/overmind/memory/active`, else `off`: memory uses nothing on a machine until a profile is chosen.
`OVERMIND_MEMORY_API`, `OVERMIND_MEMORY_CA`, `OVERMIND_MEMORY_TOKEN` and `OVERMIND_MEMORY_TOKEN_FILE` in the environment win over the files;
`OVERMIND_MEMORY_HOME` and `OVERMIND_MEMORY_CACHE` move the config and cache folders.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

OFF = "off"


class ProfileError(Exception):
    """A profile that is off or not set up, for a command that needs one."""


def config_home() -> Path:
    return Path(os.environ.get("OVERMIND_MEMORY_HOME") or Path.home() / ".config/overmind/memory")


def cache_home() -> Path:
    return Path(os.environ.get("OVERMIND_MEMORY_CACHE") or Path.home() / ".cache/overmind/memory")


@dataclass
class Profile:
    """One context store: its repo's API URL, an optional CA file and a token."""

    name: str
    api: str = ""
    ca: str = ""
    token: str = ""

    @classmethod
    def active(cls) -> Profile:
        return cls.load(os.environ.get("OVERMIND_MEMORY_PROFILE") or _read(config_home() / "active") or OFF)

    @classmethod
    def load(cls, name: str) -> Profile:
        profile = cls(name)
        if profile.off:
            return profile
        env = _parse_env(profile.folder / "env")
        profile.api = (os.environ.get("OVERMIND_MEMORY_API") or env.get("OVERMIND_MEMORY_API", "")).rstrip("/")
        profile.ca = os.environ.get("OVERMIND_MEMORY_CA") or env.get("OVERMIND_MEMORY_CA", "")
        profile.token = os.environ.get("OVERMIND_MEMORY_TOKEN") or _read(profile.token_file)
        return profile

    @staticmethod
    def use(name: str) -> None:
        """Make `name` the machine's active profile; `off` turns memory off."""
        config_home().mkdir(parents=True, exist_ok=True)
        (config_home() / "active").write_text(name + "\n")

    @staticmethod
    def names() -> list[str]:
        """The profiles set up on this machine."""
        home = config_home()
        return sorted(p.name for p in home.iterdir() if (p / "env").is_file()) if home.is_dir() else []

    @property
    def off(self) -> bool:
        return self.name == OFF

    @property
    def folder(self) -> Path:
        return config_home() / self.name

    @property
    def token_file(self) -> Path:
        return Path(os.environ.get("OVERMIND_MEMORY_TOKEN_FILE") or self.folder / "token")

    @property
    def cache(self) -> Path:
        return cache_home() / self.name

    @property
    def set_up(self) -> bool:
        return not self.off and bool(self.api and self.token)

    def require(self) -> Profile:
        """This profile, or a ProfileError saying how to turn it on or set it up."""
        if self.off:
            raise ProfileError("memory is off on this machine (`overmind memory use <profile>` to turn it on)")
        if not self.set_up:
            raise ProfileError(f"profile '{self.name}' is not set up: run `overmind memory setup`")
        return self

    def save(self, token: str | None) -> None:
        """Write `env`, and `token` when given, mode 600."""
        self.folder.mkdir(parents=True, exist_ok=True)
        lines = [f"OVERMIND_MEMORY_API={self.api}"] + ([f"OVERMIND_MEMORY_CA={self.ca}"] if self.ca else [])
        _write_private(self.folder / "env", "\n".join(lines) + "\n")
        if token:
            _write_private(self.token_file, token + "\n")


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _parse_env(path: Path) -> dict[str, str]:
    """KEY=VALUE lines; blank lines and # comments are skipped, surrounding quotes dropped."""
    values = {}
    for line in _read(path).splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("'\"")
    return values


def _write_private(path: Path, text: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as file:
        file.write(text)
    os.chmod(path, 0o600)
