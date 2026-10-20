# Game development workflow: agent notes

The user's workspace for their Godot game projects. Every session starts
here. This repo holds the shared workflow (the cycle, the skills, the
worker loop); each game is its own independent repo beside it
(`../<game>/`), with its own `AGENTS.md` and context.

`CLAUDE.md` is a symlink to this file, and `.claude/` is a symlink to
`.agents/`.

## Current game

**`../03-prototype/`**

At the start of every session, read `../03-prototype/CLAUDE.md` and
follow its pointers to its own context. Work on that game unless the user
names another. Paths in a game's files are relative to that game's root.

## The workflow

- `.agents/context/workflow.md`: the cycle: review (brainstorming or QA),
  `/grill-me`, `/to-spec`, `/to-tickets`, implementation
  (`tools/work.sh`), build and publish, `/retro`, and back to review.
  Read it before any of those.
- `.agents/context/issue-tracker.md`: cycles, specs and issues as local
  Markdown in the game's `.scratch/`. Every ticket names its repo.
- `.agents/context/project-setup.md`: what a game repo provides.
- `.agents/skills/`: the skills, adapted from Matt Pocock's
  (https://github.com/mattpocock/skills).
- `tools/work.sh`: the worker loop; `tools/next_issue.py`: the next
  ready issue. Both take the current game unless given another.
- `CODING_STANDARDS.md`: the default standards (Clean Code for Godot),
  for a game without its own.

## Standing rules

- **Act in the game's repo.** Code, docs, checks and commits for a game
  happen in its repo (`git -C ../<game>`), never here. Commit here only
  changes to the workflow itself.
- **Keep the repos independent.** No symlinks or references from a game
  to this repo. A game's files describe only the game.
- **Changing the workflow:** a change here reaches every game. `/retro`
  proposes changes; the user picks. Project details belong in the game's
  `.agents/context/`. Write for agents: short, plain, one instruction per
  sentence.
