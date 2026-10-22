# The development cycle

How a change goes from review to a new build, in every game project that
uses this workflow. It follows the main flow of Matt Pocock's skills
(https://github.com/mattpocock/skills), adapted in `skills/`: review,
grill, spec, tickets, implement, retro, and back to review. They are ours
to change over time, mostly through `/retro`.

This repo holds what every game shares: this cycle, the issue tracker
(`issue-tracker.md`), the skills, the worker loop (`tools/work.sh`), the
publisher (`tools/publish/publish.py`), the machine's tools
(`machine.md`), how to publish (`games-server.md`) and the
default coding standards. It also holds each game's cycles and
explorations, in `.scratch/<game>/` (not in git). Every session and
worker runs here. Each game is an independent repo beside this one
(`../<game>/`) with its own `AGENTS.md` and context (`project-setup.md`);
each session establishes which game it works on (`AGENTS.md`). All of a
game's work on the game itself, commits included, happens in its repo.

## Where things live

| What | Where | Owner |
|---|---|---|
| The user's docs | the game's `docs/` | Each issue (grilling's glossary terms: to-spec) |
| Screenshots the docs show | the game's `docs/img/` | The build issue |
| The current build's review | the game's `docs/review.md` | The build issue |
| Direction: art direction, references, research | the game's `docs/direction/` | Review |
| A cycle: feedback, mocks, assets, spec, issues | `.scratch/<game>/<YYYY-MM-DD>-<slug>/` here | See below |
| The game | the game's code folders (its engineering doc) | Implementation |
| The game's agent context | the game's `.agents/context/` | See `project-setup.md` |

So `docs/` describes what's built, the cycle's spec holds the design
choices agreed and not built yet, and the published game is the build.
Three things in `docs/` aren't built, by design: the glossary (terms
settled in grilling go in at `/to-spec`), `docs/direction/` (written in
review) and the user's direction and ideas elsewhere, labelled as such
("direction, not built", "liked, not built", "parked").
An agreed design choice is never written there as "(agreed, not built)".
Each issue writes the docs for what it builds, in the same commit, so the
docs never run ahead of the game.

## Publication

Publishing updates the persistent, user-accessible version, verifies
success, and returns its link. Generating local files is preparation.
The game's publishing doc (`.agents/context/publishing.md`) lists its
outputs (the game, a docs page) and their prepared folders. Every host
publishes them, with the cycle's mocks, to the games server with
`python3 tools/publish/publish.py ../<game>` (`games-server.md`).

## 1. Review session (brainstorming or QA)

The cycle starts with the user talking freely, in one of two modes. No
skill.

- **Brainstorming:** a new game, or a new direction. Research the
  competition, interview the user in rounds of a few multiple-choice
  questions, recommend rather than survey, and let ideas be dropped.
- **QA:** the user plays the published build and reads the Review page
  of its docs (`docs/review.md`), which says what changed and lists open
  questions. They
  say what they saw, what to change, and new features.

Build mocks for the user to see while the feedback is fresh: when a
point changes how something looks or behaves, make a simple UI mock of
just that part, without the game, with the open choices as variants to
switch between. When there is a game, show its current UI around it at
its real places, as flat stand-ins, so the mock shows what the change
bumps into. A mock lives in
the cycle's `mocks/<YYYY-MM-DD>-<slug>/` (its
`index.html`, images, the scripts that made them, a README), labelled as a
mockup. Publishing puts it on the game's Mocks page. The user
lands the design on the mock, and the refinement starts from what they
chose.

Make the assets in the review too, with the user, so each round is
minutes, not a cycle: textures, sprites, icons, sounds and other art.
They live in the cycle's `assets/`, with their source
scripts, for the user to iterate on. What the user agrees is what the
implementation brings into the game; the spec names each asset.

Never change the game or the docs in a review: points that change them go
into the Feedback, for the refinement and the implementation. The one
exception is `docs/direction/`: what lasts beyond the cycle (the art
direction, the type, references, research) goes there as the user agrees
it, labelled direction, and is committed in the game's repo. Keep its
pages in the docs nav. A mock or an asset in the making stays in the
cycle; the direction page links nothing in `.scratch/`, so copy any image
it shows into `docs/direction/img/`.

Each review starts the next cycle: create its folder in
`.scratch/<game>/` (dated today, the slug naming the change) as soon as
the review begins. As it goes, write the user's points into its
`feedback.md`: their notes in their words, the ideas, the research, and
anything explored, agreed or dropped. Review records
feedback and accepted choices only in `feedback.md`; it never creates or
updates `spec.md`, even when a design is approved. Before the session
ends, read the Feedback back to the user and confirm it's complete. The
next grill session may start fresh or continue this conversation: the
Feedback carries the review either way.

## 2. Refinement session

Keep the live conversation from grilling through `/to-spec` and
`/to-tickets`; do not intentionally clear it between these steps. There
is no persisted file carrying the interview into `/to-spec`.

1. `/grill-me` interviews the user in rounds. Its primary input is the
   latest `feedback.md`, with the game's `docs/review.md` and the domain docs as
   context. It works whether or not the review conversation is still
   present. Keep the design tree, terms, decisions and open questions in
   chat. **Write nothing:** no spec, review updates, glossary, decision
   log, scratch notes or mocks. Fact-finding and delegated exploration are
   read-only. If a decision needs a new mock or asset, identify the needed
   review work in chat; create it in review, not during grilling.
   If workflow, terminology or tool questions interrupt the interview,
   answer them and return to the unresolved product-decision frontier.
   Neither `/to-spec` nor `/to-tickets` proceeds until the frontier is empty
   and the user confirms shared understanding.
2. `/to-spec` reads the live conversation and publishes an
   implementation-ready spec to
   `.scratch/<game>/<YYYY-MM-DD>-<slug>/spec.md`, with its `Repo:` line; an
   earlier interview draft is neither expected nor required. If revising a
   spec already published for this work, update it from the live
   conversation. Preserve agreed choices and words and remove superseded
   choices. Make scope, implementation boundaries, affected docs and
   testing seams explicit (the game's engineering doc lists its tests
   and captures). Check the testing seams with the user as the skill
   requires. This is synthesis, not another design round: unresolved
   choices stay explicit and are not silently approved. At publication,
   record settled glossary terms and the refinement's decision-log entry
   as the game's domain doc specifies.
3. `/to-tickets` first verifies that grilling reached an empty frontier and
   the user explicitly confirmed shared understanding. It splits the spec
   into `issues/NN-slug.md`, in dependency order. Each issue names its
   repo and the docs it updates for what it builds. If ticketing exposes a missing product
   decision, return to `/grill-me`, settle it, update the spec and only then
   resume ticketing. The user approves the breakdown. The last issue is
   always **Build and publish**, blocked by all the others.

## 3. Implementation (without the user)

After `/to-tickets`, the user runs `tools/work.sh` here (for the current
game, or `tools/work.sh ../<game>`) and leaves. Nobody asks the user anything until
the build is published: choices, open questions and declined review
findings go into the issues' `## Comments`, and the build issue collects
them into the game's `docs/review.md` for the next review.

`work.sh` runs independent workers: for each ready issue
(`next_issue.py`), one fresh worker at a time, until no issue is ready.
The default is `codex exec` running the implementation skill;
`WORK_AGENT=claude` selects Claude Code with the implementation skill.
Claude's per-attempt budget is `WORK_BUDGET_USD` (default 15). Codex uses
its CLI configuration. Model settings, quota fallback, recovery artifacts
and attempt metrics are documented in `workers.md`. There is no queue
service. Each worker:
- runs here, with the issue's repo added to its workspace, and does all
  the issue's work in that repo;
- claims its issue (`in progress`, with its `Base:`) and touches no other
  issue;
- builds to the issue, the spec and the mock it names (the mock is the
  agreed design), bringing in the agreed assets the issue names from
  the cycle's `assets/` (copied into the game, with their
  scripts into the game's tools), not making new ones;
- writes the issue's `Docs to write` in the same commit as the code;
- runs `/code-review` once and fixes once (`implement`, step 10);
- sets the issue `done`, or `blocked` with its commits reverted.

The state lives in the issue files (`issue-tracker.md`), so the loop can
be stopped and started again. An issue left `in progress` is resumed: its
commits and unfinished edits are preserved, including failing work
(`implement`, step 1). A usage limit cools down that provider and tries the
other; the loop waits when no configured provider is available. An issue
that fails twice stops the loop. Authentication failures stop for repair.
Each worker's log is in this repo's `artifacts/work/<game>/`, ignored in git.

`/implement` also works alone, in a top-level session.

## 4. Build and publish (the last issue, then automatic publication)

A worker does the build issue like any other:
1. Run the checks, including the build (the engineering doc).
2. Render the project's captures into the scratchpad and look at the
   screenshots. Copy the ones that show the change to `docs/img/` as JPEGs.
3. Package the game for publishing (the engineering doc).
4. Write the game's `docs/review.md`, replacing the last cycle's: the game version and date, what changed
   to try (with the screenshots), the implementer's choices, open
   questions, and **Code debt**: files beyond the coding standards'
   size warnings, with their size, and the review findings deferred as a later
   refactor. Read every issue's Comments and the cycle's `debt.md`, including
   unresolved findings carried from earlier cycles. The next refinement
   can ticket a refactor from it. Its links stay inside `docs/`: name
   issues by number, never link into `.scratch/`.
5. Update `.agents/context/status.md` (where things stand).
6. Commit, and close the build issue.

As soon as the worker loop finishes, the active host session runs
`/publish` automatically. The cycle is complete only after every
output is on the games server and its link returned. That published
build is the next review.

## 5. Retro

Soon after the build (the session logs are kept about 30 days), run
`/retro` in a new session here. It reads the cycle (spec,
issues and their comments, `feedback.md`, the game's `docs/review.md` and commits) and a digest
of the cycle's sessions, and suggests changes to the skills, this
workflow, the game's context and its checks. The user picks which to
make. A change to a skill or to this workflow is committed here and
reaches every game; one that suits only this game goes in its own
context, committed in its repo.

## Rules that hold in every step

- The game's standing rules (its `AGENTS.md`) hold in every step.
- A game's repo never links to or names this one.
- Assets are made in the review and only brought in by the
  implementation. Nothing in `.scratch/` is referenced from the game: an
  agreed asset is copied into the game (its script into the tools), and
  nothing the game builds or checks reads `.scratch/`.
- Docs-only work (a refinement with no build) republishes the docs page,
  if the game has one, not the game itself.
