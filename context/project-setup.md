# Setting up a project

What a game project provides so the cycle in `workflow.md` runs in it.
Projects sit beside this repo (`../<project>/`); every session and script
runs from the project's root.

## Links

- `.agents/skills` → `../../game-development/skills` (a symlink), so the
  skills are this repo's, never copies.
- `.claude` → `.agents`, and `CLAUDE.md` → `AGENTS.md` (symlinks), so
  Claude Code and Codex read the same files.
- The scripts are not linked: run `../game-development/tools/work.sh` and
  `../game-development/tools/next_issue.py` from the project's root.

## Files

- `AGENTS.md`: what the game is, where the workflow is
  (`../game-development/context/workflow.md` and `issue-tracker.md`),
  pointers to its own context, publishing, and its standing rules. Short:
  mostly navigation pointers.
- `.agents/context/domain.md`: where the domain model lives (the docs,
  the glossary) and where decisions go.
- `.agents/context/engineering.md`: Godot version, code map, the check
  command, tests and captures, build and packaging, gotchas.
- `.agents/context/decisions.md`: the iteration log of what the user
  asked for, liked and rejected, newest first.
- `.agents/context/status.md`: what's built, agreed and next.
- `.agents/context/publishing.md`: the outputs, their prepared files and
  destinations (once there is something to publish).
- `docs/`: the user's docs; `docs/README.md` says what's where.
- `CODING_STANDARDS.md` only when the project departs from
  `../game-development/CODING_STANDARDS.md`.
- `.gitignore` covering `.scratch/` and `artifacts/` (worker logs go to
  `artifacts/work/`).
