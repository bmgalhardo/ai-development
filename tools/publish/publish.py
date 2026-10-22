#!/usr/bin/env python3
"""Publish a game's outputs to the games server: its menu page and the latest
game, docs page and mocks.

The game's .agents/context/publishing.md lists its outputs in a table whose
first column is the output (`game` or `docs`) and whose second names the
prepared folder in backticks, relative to the game's root:

    | game | `artifacts/artifact-site/` (`tools/package_artifact.py`) |

The docs page includes the current review (docs/review.md). The mocks are the
current cycle's (this repo's .scratch/<game>/<latest cycle>/mocks/), newest
first, each as it was made. Each output is uploaded to <server>/<game>/.staging/<output>/ and then moved to
<server>/<game>/<output>/, replacing the previous build. The server keeps
games.json, the list of games the menu pages are built from.

    python3 tools/publish/publish.py ../<game>
"""

import argparse
from datetime import datetime
import html
import json
import os
from pathlib import Path
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request

WORKFLOW = Path(__file__).resolve().parents[2]
SERVER = os.environ.get("GAMES_URL", "https://games.bgalhardo.internal")
OUTPUTS = {"game": "Game", "docs": "Docs", "mocks": "Mocks"}
# What a mock folder keeps to itself: the scripts and notes that made it,
# and kept/ (things set aside, such as a replaced model).
MOCK_SOURCES = ("*.gd", "*.py", "*.md", "*.json", "*.uid", "*.template.html", "kept")
# A mock made for the old review board links back to its page there.
BACK_LINK = re.compile(r'(?:\.\./)+index\.html#mocks/[\w.-]+')
HEADING = re.compile(r"^#\s+(.+)$", re.M)
ROW = re.compile(r"^\|\s*(game|docs)\s*\|\s*`([^`]+)`", re.IGNORECASE)

STYLE = """
:root { color-scheme: light dark; --bg: #f6f5f2; --fg: #1d1d1b; --muted: #6b6a66;
  --card: #ffffff; --line: #dedcd6; --accent: #3a5ccc; }
@media (prefers-color-scheme: dark) { :root { --bg: #161615; --fg: #ecebe7;
  --muted: #9b9a95; --card: #20201e; --line: #34332f; --accent: #8ea6ff; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg);
  font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 40rem; margin: 0 auto; padding: 3rem 16px; }
h1 { font-size: 1.6rem; margin: 0 0 .25rem; }
p { color: var(--muted); margin: 0 0 2rem; }
nav { display: grid; gap: .75rem; }
a { display: block; padding: 1rem 1.25rem; border: 1px solid var(--line);
  border-radius: 10px; background: var(--card); color: var(--fg);
  text-decoration: none; font-weight: 600; }
a:hover { border-color: var(--accent); color: var(--accent); }
"""


def page(title, subtitle, links):
    items = "\n".join(f'<a href="{html.escape(href)}">{html.escape(label)}</a>' for label, href in links)
    return (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>{html.escape(title)}</title><style>{STYLE}</style></head>\n'
            f'<body><main><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p>\n'
            f'<nav>\n{items}\n</nav></main></body></html>\n')


def game_menu(slug, entry):
    links = [(OUTPUTS[name], f"{name}/") for name in OUTPUTS if name in entry["outputs"]]
    return page(entry["title"], f"Latest build, published {entry['published']}.", links)


def index(games):
    links = [(games[slug]["title"], f"{slug}/") for slug in sorted(games)]
    return page("Games", "Pick a game.", links)


def outputs(game):
    """The game's prepared folders by output, from its publishing doc."""
    doc = game / ".agents/context/publishing.md"
    found = {}
    for line in doc.read_text(encoding="utf-8").splitlines():
        match = ROW.match(line.strip())
        if match:
            found[match.group(1).lower()] = game / match.group(2)
    return found


def mocks(game):
    """The mocks page, prepared in artifacts/mocks/<game>/; None if there are no mocks."""
    cycles = sorted((WORKFLOW / ".scratch" / game.name).glob("[0-9]*-*/"))
    found = sorted(cycles[-1].glob("mocks/*/index.html"), reverse=True) if cycles else []
    if not found:
        return None
    out = WORKFLOW / "artifacts/mocks" / game.name
    if out.exists():
        shutil.rmtree(out)
    links = []
    for index in found:
        folder = index.parent
        shutil.copytree(folder, out / folder.name, ignore=shutil.ignore_patterns(*MOCK_SOURCES))
        mock = out / folder.name / "index.html"
        mock.write_text(BACK_LINK.sub("../", mock.read_text(encoding="utf-8")), encoding="utf-8")
        readme = folder / "README.md"
        match = HEADING.search(readme.read_text(encoding="utf-8")) if readme.exists() else None
        links.append((match.group(1) if match else folder.name, f"{folder.name}/"))
    (out / "index.html").write_text(page(f"{title(game)}: mocks", "Newest first.", links), encoding="utf-8")
    return out


def title(game):
    first = (game / "AGENTS.md").read_text(encoding="utf-8").splitlines()[0]
    return re.sub(r":\s*agent notes$", "", first.lstrip("# ").strip()) or game.name


class Server:
    def __init__(self, url):
        self.url = url.rstrip("/")

    def request(self, method, path, data=None, headers=None, missing_ok=False):
        url = self.url + urllib.parse.quote(path)
        req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if missing_ok and error.code == 404:
                return None
            raise SystemExit(f"{method} {url}: {error.code} {error.reason}")

    def put(self, path, data):
        self.request("PUT", path, data)

    def upload(self, folder, slug, name):
        """Upload a folder to /<slug>/<name>/ and replace whatever was there."""
        staging = f"/{slug}/.staging/{name}/"
        self.request("DELETE", staging, missing_ok=True)
        files = sorted(p for p in folder.rglob("*") if p.is_file())
        for file in files:
            self.put(staging + file.relative_to(folder).as_posix(), file.read_bytes())
        # nginx accepts an https Destination only on its own TLS; the gateway terminates it.
        host = urllib.parse.urlsplit(self.url).netloc
        destination = f"http://{host}" + urllib.parse.quote(f"/{slug}/{name}/")
        self.request("MOVE", staging, headers={"Destination": destination, "Overwrite": "T"})
        return len(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("game", help="the game's repo, relative to this one (../<game>)")
    parser.add_argument("--server", default=SERVER, help=f"the games server (default {SERVER}, or GAMES_URL)")
    args = parser.parse_args()
    game = (WORKFLOW / args.game).resolve()
    slug = game.name
    folders = outputs(game)
    if mock_folder := mocks(game):
        folders["mocks"] = mock_folder
    for name, folder in folders.items():
        if not (folder / "index.html").is_file():
            print(f"Missing {folder}/index.html: prepare the {name} output first", file=sys.stderr)
            return 1
    server = Server(args.server)
    for name, folder in folders.items():
        count = server.upload(folder, slug, name)
        print(f"uploaded {name}: {count} files")
    games = json.loads(server.request("GET", "/games.json", missing_ok=True) or b"{}")
    entry = games.get(slug, {"outputs": []})
    for name in entry["outputs"]:
        if name not in folders:
            server.request("DELETE", f"/{slug}/{name}/", missing_ok=True)
    entry["title"] = title(game)
    entry["outputs"] = [name for name in OUTPUTS if name in folders]
    entry["published"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    games[slug] = entry
    server.put("/games.json", json.dumps(games, indent=2).encode())
    server.put(f"/{slug}/index.html", game_menu(slug, entry).encode())
    server.put("/index.html", index(games).encode())
    for path in [f"/{slug}/"] + [f"/{slug}/{name}/" for name in folders]:
        server.request("GET", path)
        print(f"{server.url}{path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
