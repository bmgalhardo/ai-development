# Setting up a game repo

What a game provides so the cycle in `workflow.md` runs on it. Each game
is an independent git repo beside this one (`../<game>/`): no symlinks to
this repo and no mention of it. A session here works on a game once the
user names it (`AGENTS.md`).

## Files

- `AGENTS.md`, with `CLAUDE.md` as a symlink to it: what the game is,
  pointers to its own docs and `.agents/context/` files, publishing, and
  its standing rules. Its cycles are kept outside the repo; it says so
  without naming where. Short: mostly
  navigation pointers. The workflow's session reads it first.
- `.agents/context/domain.md`: where the domain model lives (the docs,
  the glossary) and where decisions go.
- `.agents/context/engineering.md`: Godot version, code map, the check
  command, tests and captures, test boundaries, build and packaging,
  gotchas. Only what is true of this game: the machine's tools and how to
  publish on a host are the workflow's (`machine.md`, `publishing/`).
- `.agents/context/decisions.md`: the iteration log of what the user
  asked for, liked and rejected, newest first.
- `.agents/context/status.md`: what's built, agreed and next.
- `.agents/context/publishing.md`: the outputs, their prepared files and
  destinations on each host (once there is something to publish). The
  review board has no prepared files in the game; give its name and
  destinations.
- `docs/`: the user's docs; `docs/README.md` says what's where.
- `CODING_STANDARDS.md` only when the game departs from this repo's.
- `.gitignore` covering `artifacts/`.

The game's review board settings (its name, extra sections from the
game's repo, its own pages) are in the workflow's
`.scratch/<game>/exploration/page/board.json` (`tools/render_review.py`).
