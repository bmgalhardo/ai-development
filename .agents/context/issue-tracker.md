# Issue tracker: local Markdown

Specs and issues for each game live as Markdown files in the game's own
`.scratch/` (`../<game>/.scratch/`), one folder per cycle. Written for the
skills in `.agents/skills/`; the cycle itself is in `workflow.md`. The
game is the current one in `AGENTS.md` unless the user names another.

## Conventions

- One cycle per folder: `../<game>/.scratch/<YYYY-MM-DD>-<slug>/`, dated
  the day it starts, the slug naming the change. Folders sort by date, and
  the latest is the current cycle.
- `/to-spec` publishes the spec to `<cycle>/spec.md` from the live
  conversation. This filename is our local tracker's convention, not a
  prerequisite or a filename imposed by the skill. Review records feedback
  and accepted choices in `review.md`; `/grill-me` writes nothing. There
  is no persisted interview handoff between them.
- Issues are one file per issue at `<cycle>/issues/<NN>-<slug>.md`,
  numbered from `01` in dependency order, never one combined file.
- **Every spec and issue names its repo** on a `Repo:` line near the top
  (`**Repo:** ../03-prototype`, relative to this workflow repo). Workers
  run here, where the skills are, and do all the issue's work in that
  repo: code, docs, checks and commits (`git -C <repo>`).
- The last issue of every cycle is the build: it writes the cycle's
  `review.md` (see `workflow.md`). The review session then adds a
  `## Feedback` section to it, which the next `/grill-me` starts from.
- Each issue file has a `Status:` line near the top: `open`, then
  `in progress` (a worker claimed it), then `done`; or `blocked` (it
  couldn't go green; its commits are reverted and `## Comments` says why).
  An issue left `in progress` means its worker died: the next worker
  resets its repo to its `Base:` and starts it again.
- An issue is **ready** when it's `open` and every issue in its `Blocked by`
  is `done`. The build issue is ready when every other issue is `done` or
  `blocked`.
- `Base:` (written by the implementer) is the commit of the issue's repo
  the issue started from, for its review. `Touches:` (written by
  `/to-tickets`) names the main modules and docs it changes, so issues
  that don't overlap can run at once.
- Comments and history go at the bottom of the file under `## Comments`.
- Link to the game's docs by path relative to the issue file
  (`../../docs/design/<topic>.md`, `../../docs/img/<name>.jpg`), and to
  the spec as `../spec.md`.
- `.scratch/` is not in git: it is working material. What lasts goes to
  the game's `docs/` (when built), its `.agents/context/decisions.md` and
  its code.

## When a skill says "publish to the issue tracker"

Create a new file under the game's `.scratch/<cycle>/`, creating the
folder if needed, with its `Repo:` line.

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path
or the issue number directly; a bare number means the current game's
current cycle. `python3 tools/next_issue.py` finds the next ready one.
