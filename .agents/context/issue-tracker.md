# Issue tracker: local Markdown

Specs and issues for each game live as Markdown files in this repo's
`.scratch/<game>/`, one folder per cycle, named by the game's folder
(`.scratch/02-prototype/` for `../02-prototype`). `.scratch/` is not in
git. Written for the
skills in `.agents/skills/`; the cycle itself is in `workflow.md`. The
game is the session's game (`AGENTS.md`).

## Conventions

- One cycle per folder: `.scratch/<game>/<YYYY-MM-DD>-<slug>/`, dated
  the day it starts, the slug naming the change. Folders sort by date, and
  the latest is the current cycle.
- A cycle runs from the review that starts it to its build. The review
  session creates the folder and writes `feedback.md`, `mocks/` and
  `assets/` in it; the refinement adds `spec.md` and `issues/`.
- `/to-spec` publishes the spec to `<cycle>/spec.md` from the live
  conversation. This filename is our local tracker's convention, not a
  prerequisite or a filename imposed by the skill. Review records feedback
  and accepted choices in `feedback.md`; `/grill-me` writes nothing. There
  is no persisted interview handoff between them.
- Issues are one file per issue at `<cycle>/issues/<NN>-<slug>.md`,
  numbered from `01` in dependency order, never one combined file.
- **Every spec and issue names its repo** on a `Repo:` line near the top
  (`**Repo:** ../<game>`, relative to this workflow repo). Workers
  run here, where the skills are, and do all the issue's work in that
  repo: code, docs, checks and commits (`git -C <repo>`).
- The last issue of every cycle is the build: it writes the game's
  `docs/review.md` (see `workflow.md`), published with the docs. The
  review session then writes the cycle's `feedback.md`, which the next
  `/grill-me` starts from.
- Each issue file has a `Status:` line near the top: `open`, then
  `in progress` (a worker claimed it), then `in review` (implemented and
  committed, waiting for its review session), then `done`; or `blocked`
  (it couldn't go green, so its commits are reverted; or it met its
  `Stop if`, so its commits stay; `## Comments` says why). An issue `in review` is not `done`: its dependents wait for it.
  An issue left `in progress` means its worker died: the next worker
  preserves its commits and unfinished changes, reads `## Progress`,
  and repairs failing checks before continuing.
- An issue is **ready** when it's `open` and every issue in its `Blocked by`
  is `done`. The build issue is ready when every other issue is `done` or
  `blocked`.
- `Base:` (written by the implementer) is the commit of the issue's repo
  the issue started from, for its review. `Touches:` (written by
  `/to-tickets`) names the main modules and docs it changes, so issues
  that don't overlap can run at once.
- `## Progress` records the last completed implementation step, commit, checks,
  reviewed commit and remaining work for recovery.
- A cycle's `reviews/NN-standards.md` and `reviews/NN-spec.md` are an
  issue's saved review reports, written by the worker loop for the fixer.
- A cycle's `debt.md` carries deferred review findings: affected files,
  suggested change, source issue and disposition (`open`, `assigned`,
  `resolved` with commit, or `accepted` with reason). Carry unresolved
  entries into the next cycle during ticketing.
- Comments and history go at the bottom of the file under `## Comments`.
- Link to the game's files by path relative to the linking file: from a
  cycle's `feedback.md` or `spec.md`, `../../../../<game>/docs/<file>.md`;
  from an issue, `../../../../../<game>/docs/img/<name>.jpg`. Link to the
  spec as `../spec.md`. The game's `docs/review.md` links only inside
  `docs/` (never to `.scratch/`): the docs build fails on any other link.
- `.scratch/` is working material. What lasts goes to the game's `docs/`
  (when built), its `.agents/context/decisions.md` and its code.

## When a skill says "publish to the issue tracker"

Create a new file under `.scratch/<game>/<cycle>/`, creating the folder
if needed, with its `Repo:` line.

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path
or the issue number directly; a bare number means the session's game's
current cycle. `python3 tools/workers/next_issue.py ../<game>` finds the next ready one.
