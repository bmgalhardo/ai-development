#!/usr/bin/env python3
"""Publish a project's outputs to the publish server, with its menu page.

The project's .agents/context/publishing.md lists its outputs in a table
whose first column is the output (`game` or `docs`) and whose second names
the prepared folder in backticks, relative to the project's root:

    | game | `artifacts/artifact-site/` (`tools/package_artifact.py`) |

A project without that doc has no outputs. The docs page includes the
current review (docs/review.md). The mocks are the review's: the current
cycle's (this repo's .scratch/<project>/<latest cycle>/mocks/), newest first,
each as it was made. Each output is uploaded to
<server>/<project>/.staging/<output>/ and then moved to
<server>/<project>/<output>/, replacing the previous one. The server keeps
projects.json, the list of projects the menu pages are built from.

    python3 tools/publish/publish.py ../<project>          the build: its outputs
    python3 tools/publish/publish.py ../<project> mocks    the review: its mocks

Only the named outputs change on the server. With nothing to publish it says
so and never contacts the server.
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
import tempfile
import urllib.error
import urllib.parse
import urllib.request

WORKFLOW = Path(__file__).resolve().parents[2]
SERVER = os.environ.get("PUBLISH_URL", "https://projects.bgalhardo.internal")
OUTPUTS = {"game": "Game", "docs": "Docs", "mocks": "Mocks"}
BUILD = ("game", "docs")  # what the build publishes; the review publishes the mocks
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


def project_menu(slug, entry):
    links = [(OUTPUTS[name], f"{name}/") for name in OUTPUTS if name in entry["outputs"]]
    return page(entry["title"], f"Latest build, published {entry['published']}.", links)


def index(projects):
    links = [(projects[slug]["title"], f"{slug}/") for slug in sorted(projects)]
    return page("Projects", "Pick a project.", links)


def outputs(project):
    """The project's prepared folders by output, from its publishing doc."""
    doc = project / ".agents/context/publishing.md"
    found = {}
    if not doc.is_file():
        return found
    for line in doc.read_text(encoding="utf-8").splitlines():
        match = ROW.match(line.strip())
        if match:
            found[match.group(1).lower()] = project / match.group(2)
    return found


def mocks(project, out):
    """The current cycle's mocks page, prepared in out; None if the cycle has no mocks."""
    cycles = sorted((WORKFLOW / ".scratch" / project.name).glob("[0-9]*-*/"))
    found = sorted(cycles[-1].glob("mocks/*/index.html"), reverse=True) if cycles else []
    if not found:
        return None
    links = []
    for index in found:
        folder = index.parent
        shutil.copytree(folder, out / folder.name, ignore=shutil.ignore_patterns(*MOCK_SOURCES))
        mock = out / folder.name / "index.html"
        mock.write_text(BACK_LINK.sub("../", mock.read_text(encoding="utf-8")), encoding="utf-8")
        readme = folder / "README.md"
        match = HEADING.search(readme.read_text(encoding="utf-8")) if readme.exists() else None
        links.append((match.group(1) if match else folder.name, f"{folder.name}/"))
    (out / "index.html").write_text(page(f"{title(project)}: mocks", "Newest first.", links), encoding="utf-8")
    return out


def title(project):
    first = (project / "AGENTS.md").read_text(encoding="utf-8").splitlines()[0]
    return re.sub(r":\s*agent notes$", "", first.lstrip("# ").strip()) or project.name


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
    parser.add_argument("project", help="the project's repo, relative to this one (../<project>)")
    parser.add_argument("only", nargs="*", choices=list(OUTPUTS), metavar="output",
                        help="what to publish: mocks (the review), or by default the build's outputs")
    parser.add_argument("--server", default=SERVER, help=f"the publish server (default {SERVER}, or PUBLISH_URL)")
    args = parser.parse_args()
    project = (WORKFLOW / args.project).resolve()
    with tempfile.TemporaryDirectory() as staging:
        return publish(project, args.only or list(BUILD), Server(args.server), Path(staging))


def publish(project, names, server, staging):
    """Upload the named outputs the project has; remove the named ones it no longer has."""
    slug = project.name
    available = outputs(project)
    if "mocks" in names and (mock_folder := mocks(project, staging / "mocks")):
        available["mocks"] = mock_folder
    folders = {name: folder for name, folder in available.items() if name in names}
    if not folders:
        print(f"Nothing to publish for {slug} ({', '.join(names)})")
        return 0
    for name, folder in folders.items():
        if not (folder / "index.html").is_file():
            print(f"Missing {folder}/index.html: prepare the {name} output first", file=sys.stderr)
            return 1
    for name, folder in folders.items():
        count = server.upload(folder, slug, name)
        print(f"uploaded {name}: {count} files")
    projects = json.loads(server.request("GET", "/projects.json", missing_ok=True) or b"{}")
    entry = projects.get(slug, {"outputs": []})
    gone = [name for name in entry["outputs"] if name in names and name not in folders]
    for name in gone:
        server.request("DELETE", f"/{slug}/{name}/", missing_ok=True)
    entry["title"] = title(project)
    entry["outputs"] = [name for name in OUTPUTS if name in folders
                        or (name in entry["outputs"] and name not in gone)]
    entry["published"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    projects[slug] = entry
    server.put("/projects.json", json.dumps(projects, indent=2).encode())
    server.put(f"/{slug}/index.html", project_menu(slug, entry).encode())
    server.put("/index.html", index(projects).encode())
    for path in [f"/{slug}/"] + [f"/{slug}/{name}/" for name in folders]:
        server.request("GET", path)
        print(f"{server.url}{path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
