# Setting up a game repo

What a game provides so the cycle in `workflow.md` runs on it. Each game
is an independent git repo beside this one (`../<game>/`): no symlinks to
this repo and no mention of it. To work on a game, name it under
"Current game" in this repo's `AGENTS.md`.

## Files

- `AGENTS.md`, with `CLAUDE.md` as a symlink to it: what the game is,
  pointers to its own docs and `.agents/context/` files, where its cycles
  are (`.scratch/`), publishing, and its standing rules. Short: mostly
  navigation pointers. The workflow's session reads it first.
- `.agents/context/domain.md`: where the domain model lives (the docs,
  the glossary) and where decisions go.
- `.agents/context/engineering.md`: Godot version, code map, the check
  command, tests and captures, test boundaries, build and packaging,
  gotchas.
- `.agents/context/decisions.md`: the iteration log of what the user
  asked for, liked and rejected, newest first.
- `.agents/context/status.md`: what's built, agreed and next.
- `.agents/context/publishing.md`: the outputs, their prepared files and
  destinations (once there is something to publish).
- `docs/`: the user's docs; `docs/README.md` says what's where.
- `CODING_STANDARDS.md` only when the game departs from this repo's.
- `.gitignore` covering `.scratch/` and `artifacts/`.
