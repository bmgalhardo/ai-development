# Issue tracker: local Markdown

Specs and issues for each project live as Markdown files in its `.scratch/`,
one folder per cycle. Written for the skills in `skills/`; the cycle itself
is in `workflow.md`.

## Conventions

- One cycle per folder: `.scratch/<YYYY-MM-DD>-<slug>/`, dated the day the
  spec is written, the slug naming the change. Folders sort by date, and
  the latest is the current cycle.
- `/to-spec` publishes the spec to `.scratch/<cycle>/spec.md` from the
  live conversation. This filename is our local tracker's convention, not
  a prerequisite or a filename imposed by the skill. Review records
  feedback and accepted choices in `review.md`; `/grill-me` writes
  nothing. There is no persisted interview handoff between them.
- Issues are one file per issue at `.scratch/<cycle>/issues/<NN>-<slug>.md`,
  numbered from `01` in dependency order, never one combined file.
- The last issue of every cycle is the build: it writes the cycle's
  `review.md` (see `workflow.md`). The review session then adds a
  `## Feedback` section to it, which the next `/grill-me` starts from.
- Each issue file has a `Status:` line near the top: `open`, then
  `in progress` (a worker claimed it), then `done`; or `blocked` (it
  couldn't go green; its commits are reverted and `## Comments` says why).
  An issue left `in progress` means its worker died: the next worker
  resets to its `Base:` and starts it again.
- An issue is **ready** when it's `open` and every issue in its `Blocked by`
  is `done`. The build issue is ready when every other issue is `done` or
  `blocked`.
- `Base:` (written by the implementer) is the commit the issue started from,
  for its review. `Touches:` (written by `/to-tickets`) names the main
  modules and docs it changes, so issues that don't overlap can run at once.
- Comments and history go at the bottom of the file under `## Comments`.
- Link to the user's docs by relative path
  (`../../docs/design/<topic>.md`, `../../docs/img/<name>.jpg`), and to
  the spec as `../spec.md`; the docs page turns them into links to its
  pages and images.
- `.scratch/` is not in git: it is working material. What lasts goes to
  `docs/` (when built), the project's `.agents/context/decisions.md` and
  the code.

## When a skill says "publish to the issue tracker"

Create a new file under `.scratch/<cycle>/`, creating the folder if needed.

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path
or the issue number directly; a bare number means the current cycle.
