"""An in-memory Forgejo contents API, served through `Http.send`, so tests never touch the network."""

import base64
import hashlib
import json
from urllib.parse import unquote, urlsplit

API = "https://forge.test/api/v1/repos/owner/context"
TOKEN = "secret"


class FakeForgejo:
    """Repos as {"owner/name": {path: bytes}}; it checks the token and the sha a replace must send."""

    def __init__(self, repos=None):
        self.repos = repos if repos is not None else {"owner/context": {}}
        self.requests = []
        self.down = False
        self.commits = 0

    def send(self, http, method, url, headers, body):
        self.requests.append((method, url, headers.get("Authorization")))
        if self.down:
            from overmind.memory.store import StoreError
            raise StoreError(f"{url}: connection refused")
        parts = urlsplit(url)
        if parts.hostname != "forge.test":
            return 404, b""
        if headers.get("Authorization") != f"token {TOKEN}":
            return 401, json.dumps({"message": "token is required"}).encode()
        segments = unquote(parts.path).split("/")  # '', api, v1, repos, owner, name, kind, *path
        repo = self.repos.get("/".join(segments[4:6]))
        if repo is None:
            return 404, b""
        kind, path = (segments[6] if len(segments) > 6 else ""), "/".join(segments[7:])
        if not kind:
            return 200, json.dumps({"full_name": "/".join(segments[4:6]), "private": True}).encode()
        if kind == "raw":
            return (200, repo[path]) if path in repo else (404, b"")
        payload = json.loads(body) if body else {}
        if method == "GET":
            return self._get(repo, path)
        if method == "POST":
            if path in repo:
                return 422, json.dumps({"message": "file exists"}).encode()
            repo[path] = base64.b64decode(payload["content"])
            return 201, self._commit()
        if path not in repo:
            return 404, b""
        if payload.get("sha") != sha(repo[path]):
            return 409, json.dumps({"message": "sha does not match"}).encode()
        if method == "PUT":
            repo[path] = base64.b64decode(payload["content"])
        else:
            del repo[path]
        return 200, self._commit()

    def _get(self, repo, path):
        if path in repo:
            return 200, json.dumps({"path": path, "type": "file", "sha": sha(repo[path])}).encode()
        prefix = f"{path}/" if path else ""
        names = {p[len(prefix):].split("/")[0] for p in repo if p.startswith(prefix)}
        if not names:
            return (200, b"[]") if not path else (404, b"")
        entries = [{"path": prefix + name, "type": "file" if prefix + name in repo else "dir"}
                   for name in sorted(names)]
        return 200, json.dumps(entries).encode()

    def _commit(self):
        self.commits += 1
        return json.dumps({"commit": {"sha": f"{self.commits:07d}abcdef"}}).encode()


def sha(content):
    return hashlib.sha1(content).hexdigest()
