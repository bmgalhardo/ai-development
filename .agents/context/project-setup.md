# Setting up a project repo

What a project provides so the cycle in `workflow.md` runs on it. Each project
is an independent git repo beside this one (`../<project>/`): no symlinks to
this repo and no mention of it. A session here works on a project once the
user names it (`AGENTS.md`).

## Files

- `AGENTS.md`, with `CLAUDE.md` as a symlink to it: what the project is,
  pointers to its own docs and `.agents/context/` files, publishing, and
  its standing rules. Its cycles are kept outside the repo; it says so
  without naming where. Short: mostly
  navigation pointers. The workflow's session reads it first.
- `.agents/context/domain.md`: where the domain model lives (the docs,
  the glossary) and where decisions go.
- `.agents/context/engineering.md`: Godot version, code map, the check
  command, tests and captures, test boundaries, build and packaging,
  gotchas. Only what is true of this project: the machine's tools and how to
  publish are the workflow's (`machine.md`, `games-server.md`).
- `.agents/context/decisions.md`: the iteration log of what the user
  asked for, liked and rejected, newest first.
- `.agents/context/status.md`: what's built, agreed and next.
- `.agents/context/publishing.md`: the outputs and their prepared folders
  (once there is something to publish), as a table whose rows start
  `| game | \`<folder>/\`` or `| docs | \`<folder>/\``. The mocks are
  published from outside the project; don't list them.
- `docs/`: the user's docs; `docs/README.md` says what's where.
  `docs/review.md` is the current build's review (written by the build
  issue), second in the nav. `docs/direction/` holds what the review
  agrees beyond a cycle: art direction, type, references, research
  (direction, not built; `README.md` first, images in `img/`).
- `mkdocs.yml`: the docs page, built with MkDocs and the Material theme
  into `artifacts/docs-site/`, the `docs` output. It names the site, sets
  `site_dir: artifacts/docs-site`, lists every doc in `nav` and turns on
  `validation` (omitted files, links, anchors) as warnings. The check
  command builds it with `uvx --from mkdocs==1.6.1 --with
  mkdocs-material==9.7.7 mkdocs build --strict`, so a broken link or a doc
  missing from the nav fails the check.
- `CODING_STANDARDS.md` only when the project departs from this repo's.
- `.gitignore` covering `artifacts/`.
