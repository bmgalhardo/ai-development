"""Where context lives: a repo on a git host, read and written over its API, never cloned.

A store is a subclass of `Repo`. `ForgejoRepo` reads and writes with the profile's token; `GitHubPublicRepo`
reads public GitHub repos without one. Every request goes through `Http`, which tests replace.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import base64
from dataclasses import dataclass
import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

TIMEOUT = 10  # seconds per request
GITHUB_PREFIX = "github:"


class StoreError(Exception):
    """A request the host refused or never answered."""


class NotFound(StoreError):
    """The path, or the repo, does not exist."""


@dataclass
class Entry:
    path: str
    folder: bool

    def __str__(self) -> str:
        return self.path + ("/" if self.folder else "")


class Http:
    """JSON and raw requests to a host; `send` is the only call that touches the network."""

    def __init__(self, ca: str = ""):
        self.context = ssl.create_default_context()
        if ca:
            self.context.load_verify_locations(cafile=ca)

    def send(self, method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, bytes]:
        request = Request(url, data=body, method=method, headers=headers)
        try:
            with urlopen(request, timeout=TIMEOUT, context=self.context) as response:
                return response.status, response.read()
        except HTTPError as error:
            return error.code, error.read()
        except (URLError, OSError) as error:
            raise StoreError(f"{url}: {getattr(error, 'reason', error)}") from error

    def request(self, method: str, url: str, headers: dict[str, str] | None = None, payload: dict | None = None) -> bytes:
        headers = dict(headers or {})
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        status, data = self.send(method, url, headers, body)
        if status == 404:
            raise NotFound(f"{method} {url}: not found")
        if status >= 400:
            raise StoreError(f"{method} {url}: HTTP {status} {_message(data)}".rstrip())
        return data

    def json(self, method: str, url: str, headers: dict[str, str] | None = None, payload: dict | None = None):
        return json.loads(self.request(method, url, headers, payload) or b"null")


class Repo(ABC):
    """A repo's files: read and listed by every store, written only where the host allows it."""

    @abstractmethod
    def read(self, path: str) -> bytes: ...

    @abstractmethod
    def list(self, folder: str = "") -> list[Entry]: ...

    def write(self, path: str, content: bytes, message: str | None = None) -> tuple[str, str]:
        raise StoreError(f"{self} is read only")

    def delete(self, path: str, message: str | None = None) -> str:
        raise StoreError(f"{self} is read only")


class ForgejoRepo(Repo):
    """A Forgejo (or Gitea) repo, at its API URL: `https://<host>/api/v1/repos/<owner>/<repo>`."""

    def __init__(self, api: str, token: str, ca: str = "", http: Http | None = None):
        self.api = api.rstrip("/")
        self.headers = {"Authorization": f"token {token}"}
        self.token = token
        self.ca = ca
        self.http = http or Http(ca)

    def __str__(self) -> str:
        return self.api

    @property
    def host_api(self) -> str:
        return self.api.split("/repos/", 1)[0]

    def other(self, repo: str) -> ForgejoRepo:
        """Another repo on the same host, as `owner/name`, with the same token."""
        return ForgejoRepo(f"{self.host_api}/repos/{repo}", self.token, self.ca, self.http)

    def describe(self) -> dict:
        """The repo's metadata: `full_name`, `private`, ..."""
        return self.http.json("GET", self.api, self.headers)

    def read(self, path: str) -> bytes:
        return self.http.request("GET", f"{self.api}/raw/{_path(path)}", self.headers)

    def list(self, folder: str = "") -> list[Entry]:
        entries = self.http.json("GET", f"{self.api}/contents/{_path(folder)}", self.headers)
        return _entries(entries)

    def sha(self, path: str) -> str | None:
        """The file's blob sha, which a write must send to replace it; None when it does not exist."""
        try:
            entry = self.http.json("GET", f"{self.api}/contents/{_path(path)}", self.headers)
        except NotFound:
            return None
        return entry.get("sha") if isinstance(entry, dict) else None

    def write(self, path: str, content: bytes, message: str | None = None) -> tuple[str, str]:
        """Create or replace a file in one commit; ('created' or 'updated', the commit's short sha).

        Replacing sends the sha it read, so the host refuses the write if someone changed the file since.
        The default message is 'add PATH' or 'update PATH'.
        """
        sha = self.sha(path)
        payload = {"content": base64.b64encode(content).decode(),
                   "message": message or f"{'update' if sha else 'add'} {path}"}
        if sha:
            payload["sha"] = sha
        result = self.http.json("PUT" if sha else "POST", f"{self.api}/contents/{_path(path)}", self.headers, payload)
        return ("updated" if sha else "created"), result["commit"]["sha"][:7]

    def delete(self, path: str, message: str | None = None) -> str:
        """Delete a file in one commit; the commit's short sha. The default message is 'remove PATH'."""
        sha = self.sha(path)
        if not sha:
            raise NotFound(f"{path} not found")
        result = self.http.json("DELETE", f"{self.api}/contents/{_path(path)}", self.headers,
                                {"sha": sha, "message": message or f"remove {path}"})
        return result["commit"]["sha"][:7]


class GitHubPublicRepo(Repo):
    """A public GitHub repo, as `owner/name`, read without a token from its default branch."""

    def __init__(self, repo: str, http: Http | None = None):
        self.repo = repo
        self.http = http or Http()

    def __str__(self) -> str:
        return GITHUB_PREFIX + self.repo

    def read(self, path: str) -> bytes:
        return self.http.request("GET", f"https://raw.githubusercontent.com/{self.repo}/HEAD/{_path(path)}")

    def list(self, folder: str = "") -> list[Entry]:
        url = f"https://api.github.com/repos/{self.repo}/contents/{_path(folder)}"
        return _entries(self.http.json("GET", url, {"Accept": "application/vnd.github+json"}))


def _path(path: str) -> str:
    return quote(path.strip("/"))


def _entries(entries) -> list[Entry]:
    if isinstance(entries, dict):
        entries = [entries]
    return [Entry(entry["path"], entry.get("type") == "dir") for entry in entries or []]


def _message(data: bytes) -> str:
    try:
        return json.loads(data).get("message", "")
    except (ValueError, AttributeError):
        return data[:200].decode(errors="replace").strip()
