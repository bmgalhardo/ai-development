#!/usr/bin/env python3
"""Build a game's review board: the page the user reviews a cycle on.

The board is made from this repo's `.scratch/<game>/` (gitignored):

- the latest cycle (`<YYYY-MM-DD>-<slug>/`): review.md (the board opens on
  it), spec.md and issues/;
- exploration/cycle/mocks/<YYYY-MM-DD>-<slug>/: each mock's index.html, the
  images it shows, the scripts that made them and a README;
- exploration/page/: the board's own settings (board.json), its pages as
  one-line HTML fragments, their styles (board.css) and assets/.

board.json (all optional):

    {"name": "Sky Time Review",
     "title_prefix": "A Little Sky Time: ",
     "sections": [{"label": "Story", "folder": "story"}],
     "pages": [["Art studies", "art-studies.html"]]}

`sections` are folders of Markdown in the game's repo (relative to its
root), shown after the cycle: their README first, then their files in name
order. `pages` are the fragments in exploration/page/, shown last.

The tree: This cycle (Review, Spec, Issues), Mocks (each mock's README
under a button that opens the mock), the sections, then the pages. Images
the pages link to are copied under img/. Writes
artifacts/review/<game>/index.html. Publish that folder as the game's
review board (.agents/context/publishing/).

    python3 tools/render_review.py ../<game>
"""

import argparse
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import shutil
import sys

WORKFLOW = Path(__file__).resolve().parents[1]
TEMPLATE = WORKFLOW / "tools/review_page.html"
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
LINK = re.compile(r"(!?\[[^\]]*\]\()([^)\s]+)((?:\s+\"[^\"]*\")?\))")
EXTERNAL = re.compile(r"^([a-z]+:|#|/)")
CODE_SPAN = re.compile(r"(`+[^`]*`+)")
IMAGES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
# What a mock folder keeps to itself: the scripts and notes that made it,
# and kept/ (things set aside, such as a replaced model).
MOCK_SOURCES = ("*.gd", "*.py", "*.md", "*.json", "*.uid", "*.template.html", "kept")
# A mock's page on the board opens the mock with a clear button; the mock
# links back to it.
MOCK_LINK = """<style>
#doc a.open-mock { display: inline-flex; align-items: center; min-height: 44px; padding: 0 18px; margin: 4px 0 8px;
  border: 1px solid var(--gold); border-radius: 999px; text-decoration: none; }
</style>
"""
# A mock is a page of its own, served as written: it needs its own head.
HEAD = '<!doctype html>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'


@dataclass
class Page:
    key: str
    label: str
    path: Path
    text: str

    @property
    def source(self):
        return os.path.relpath(self.path, WORKFLOW)


@dataclass
class Link:
    """A relative link in a page: where it goes, or None if nowhere on the board."""
    line: int
    href: str
    kind: str = None  # "page" or "img"
    value: str = None  # A page key or an image's name under img/.
    anchor: str = ""
    anchor_ok: bool = True

    @property
    def site_href(self):
        if self.kind == "img":
            return "img/" + self.value
        return "#" + self.value + (":" + self.anchor if self.anchor else "")


def outside_fences(text):
    """(line number, row) for each row not in a fenced code block."""
    fenced = False
    for number, row in enumerate(text.splitlines(), 1):
        if row.strip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            yield number, row


def outside_code(row, replace):
    """Apply replace to the parts of a row outside inline code spans."""
    return "".join(part if CODE_SPAN.fullmatch(part) else replace(part) for part in CODE_SPAN.split(row))


def slug(title):
    """A heading's id, as the page gives it (GitHub's rule): kept in step with review_page.html."""
    title = re.sub(r"[`*]|\[([^\]]*)\]\([^)]*\)", r"\1", title)
    return re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")


def heading_ids(text):
    ids, seen = set(), {}
    for _, row in outside_fences(text):
        match = HEADING.match(row)
        if match:
            base = slug(match.group(2))
            count = seen.get(base, 0)
            seen[base] = count + 1
            ids.add(base if count == 0 else f"{base}-{count}")
    return ids


@dataclass
class Board:
    game: Path
    scratch: Path
    settings: dict
    pages: dict = field(default_factory=dict)  # key -> Page, in reading order.
    tree: list = field(default_factory=list)  # Nodes: {label, key?, children?}.
    images: dict = field(default_factory=dict)  # Path -> name under img/.
    start: str = "review"

    @property
    def page_dir(self):
        return self.scratch / "exploration/page"

    @property
    def mocks_dir(self):
        return self.scratch / "exploration/cycle/mocks"

    def label_for(self, path, text):
        """A page's label in the tree: its first heading, short."""
        title = next((m.group(2) for _, row in outside_fences(text) if (m := HEADING.match(row))), path.stem)
        prefix = self.settings.get("title_prefix", "")
        if prefix and title.startswith(prefix):
            title = title[len(prefix):]
        for cut in (" · ", " ("):
            title = title.split(cut)[0]
        title = re.sub(r"^\d+:\s*", "", title)  # Issues: "01: Title".
        return title[:1].upper() + title[1:]

    def add(self, path, key, label=None):
        text = path.read_text(encoding="utf-8")
        self.pages[key] = Page(key, label or self.label_for(path, text), path, text)
        return {"key": key, "label": self.pages[key].label}

    def build(self):
        cycles = sorted(p for p in self.scratch.iterdir() if re.match(r"\d{4}-\d{2}-\d{2}-", p.name) and p.is_dir())
        if cycles:
            cycle, node = cycles[-1], {"label": "This cycle", "children": []}
            for label, name in [("Review", "review.md"), ("Spec", "spec.md")]:
                if (cycle / name).exists():
                    node["children"].append(self.add(cycle / name, name[:-3], label))
            issues = [self.add(issue, "issues/" + issue.stem) for issue in sorted((cycle / "issues").glob("*.md"))]
            if issues:
                node["children"].append({"label": "Issues", "children": issues})
            if node["children"]:
                self.tree.append(node)
        mocks = []
        for index in sorted(self.mocks_dir.glob("*/index.html"), reverse=True):
            name = index.parent.name
            readme = index.parent / "README.md"
            if not readme.exists():
                continue
            mocks.append(self.add(readme, "mocks/" + name))
            page = self.pages["mocks/" + name]
            # Under the README's title, a button that opens the mock (inline
            # HTML, past the Markdown links), then the README's notes.
            title, _, rest = page.text.partition("\n")
            page.text = f'{title}\n\n<p><a class="open-mock" href="mocks/{name}/index.html">Open the mock</a></p>\n{rest}'
        if mocks:
            self.tree.append({"label": "Mocks", "children": mocks})
        for section in self.settings.get("sections", []):
            folder = self.game / section["folder"]
            key = section["label"].lower().replace(" ", "-")
            files = [self.add(path, f"{key}/{path.stem}") for path in sorted(folder.glob("*.md")) if path.name != "README.md"]
            node = {"label": section["label"], "children": files}
            if (folder / "README.md").exists():
                node.update(self.add(folder / "README.md", key + "/README", section["label"]))
            if files or "key" in node:
                self.tree.append(node)
        for label, name in self.settings.get("pages", []):
            # A fragment on one line is one HTML block to the Markdown renderer.
            self.tree.append(self.add(self.page_dir / name, name.rsplit(".", 1)[0], label))
        if self.start not in self.pages and self.pages:
            self.start = next(iter(self.pages))

    def image_name(self, path):
        """The image's name under img/: its own, or prefixed with its folder's if taken."""
        if path not in self.images:
            name = path.name
            if name in self.images.values():
                name = f"{path.parent.name}-{name}"
            self.images[path] = name
        return self.images[path]

    def resolve(self, page, number, href):
        """Where a relative link from a page goes."""
        where, _, anchor = href.partition("#")
        link = Link(number, href, anchor=anchor)
        path = Path(os.path.normpath(page.path.parent / where))
        if path.is_dir():
            path = path / "README.md"
        target = next((other for other in self.pages.values() if other.path == path), None)
        if target:
            link.kind, link.value = "page", target.key
            link.anchor_ok = not anchor or anchor in heading_ids(target.text)
        elif path.suffix.lower() in IMAGES and path.is_file() and not anchor:
            link.kind, link.value = "img", self.image_name(path)
        return link

    def links(self, page):
        for number, row in outside_fences(page.text):
            found = []
            outside_code(row, lambda part: found.extend(LINK.finditer(part)) or part)
            for match in found:
                if not EXTERNAL.match(match.group(2)):
                    yield self.resolve(page, number, match.group(2))

    def warnings(self):
        """Links that go nowhere on the board: work in progress, so only warned about."""
        for page in self.pages.values():
            for link in self.links(page):
                if not link.kind:
                    yield f"{page.source}:{link.line}: `{link.href}` points nowhere on the board"
                elif not link.anchor_ok:
                    yield f"{page.source}:{link.line}: `{link.href}` has no such heading"

    def rewritten(self, page):
        """The page's text with its relative links pointing at pages and images on the board."""
        def replace(match, number):
            if EXTERNAL.match(match.group(2)):
                return match.group(0)
            link = self.resolve(page, number, match.group(2))
            return match.group(1) + link.site_href + match.group(3) if link.kind else match.group(0)

        rows = page.text.splitlines()
        for number, row in outside_fences(page.text):
            rows[number - 1] = outside_code(
                row, lambda part: LINK.sub(lambda match: replace(match, number), part))
        return "\n".join(rows) + "\n"

    def render(self, name, head):
        pages = {key: {"label": page.label, "source": page.source, "text": self.rewritten(page)}
                 for key, page in self.pages.items()}
        data = json.dumps({"tree": self.tree, "order": list(self.pages), "pages": pages,
                           "start": self.start}, ensure_ascii=False)
        data = data.replace("</", "<\\/")  # Safe inside a <script> tag.
        return (TEMPLATE.read_text(encoding="utf-8").replace("__SITE_NAME__", name)
                .replace("__BRAND_HREF__", "#" + self.start).replace("__EXTRA_HEAD__", head)
                .replace("__BOARD_JSON__", data))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("game", help="the game's repo, relative to this one (../<game>)")
    args = parser.parse_args()
    game = (WORKFLOW / args.game).resolve()
    scratch = WORKFLOW / ".scratch" / game.name
    if not scratch.is_dir():
        print(f"Missing {os.path.relpath(scratch, WORKFLOW)}/: the game's cycles", file=sys.stderr)
        return 1
    settings_file = scratch / "exploration/page/board.json"
    settings = json.loads(settings_file.read_text(encoding="utf-8")) if settings_file.exists() else {}
    board = Board(game, scratch, settings)
    board.build()
    out = WORKFLOW / "artifacts/review" / game.name
    style = (board.page_dir / "board.css").read_text(encoding="utf-8") if (board.page_dir / "board.css").exists() else ""
    page = board.render(settings.get("name", f"{game.name} review"), f"<style>\n{style}</style>\n{MOCK_LINK}")
    for warning in board.warnings():
        print("warning: " + warning)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    if (board.page_dir / "assets").is_dir():
        shutil.copytree(board.page_dir / "assets", out / "assets")
    for index in sorted(board.mocks_dir.glob("*/index.html")):
        target = out / "mocks" / index.parent.name
        shutil.copytree(index.parent, target, ignore=shutil.ignore_patterns(*MOCK_SOURCES))
        text = (target / "index.html").read_text(encoding="utf-8")
        if not text.lstrip().lower().startswith("<!doctype"):
            (target / "index.html").write_text(HEAD + text, encoding="utf-8")
    (out / "index.html").write_text(page, encoding="utf-8")
    if board.images:
        (out / "img").mkdir()
    for path, name in board.images.items():
        shutil.copy(path, out / "img" / name)
    print(f"wrote {os.path.relpath(out, WORKFLOW)}/index.html ({len(board.pages)} pages, {len(board.images)} images)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
