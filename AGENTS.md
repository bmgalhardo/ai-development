# Development workflow: agent notes

The user's workspace for their projects. Every session starts
here. This repo holds the shared workflow (the cycle, the skills, the
worker loop); each project is its own independent repo beside it
(`../<project>/`), with its own `AGENTS.md` and context.

`CLAUDE.md` is a symlink to this file, and `.claude/` is a symlink to
`.agents/`.

## The session's project

At the start of a session, establish which project it is about: the user
names it, or ask them. The user's repos are listed in the L0 map, when the
session has one (below). Skip this only when the work is on the workflow
itself (this repo). Then read `../<project>/CLAUDE.md` (not cloned here: read it
from its remote with `overmind memory`, below) and follow its
pointers to that project's own context; from then on the session works on
that project. Paths in a project's files are relative to that project's root.

## Memory (`overmind memory`)

Overmind's memory is a private context store, read and written over its host's
API with no clone. Run it as `tools/overmind.sh memory …` (from a project:
`../ai-development/tools/overmind.sh memory …`), or `overmind memory …` where
Overmind is installed; docs write it as `overmind memory`. The machine's active
profile picks the store (`overmind memory use`); with none, memory is off.

- When a profile is on, a `SessionStart` hook adds the store's `L0.md` to the
  session: the user's repos, where they live, the infrastructure. It is
  private: never copy it, or anything else from the store, into a repo,
  a commit message or this file. This repo is public.
- No L0 in the session means memory is off here. Work without it: don't run
  it and don't ask to set it up.
- Read: `overmind memory ls [dir]`, `overmind memory get PATH`. Another repo
  without cloning it: `get -r OWNER/REPO PATH`, `ls -r OWNER/REPO`, with
  `-r github:OWNER/REPO` for public GitHub. `overmind memory repos` lists the
  repos the L0 names, as `-r` refs.
- Write: `overmind memory put PATH -m MSG < file`, `overmind memory rm PATH -m MSG`.
  Each write is one commit; say in the message what changed. Write when the
  user asks or a task closes an item the store tracks.
- `overmind memory --help` lists every command.

## The workflow

- `.agents/context/workflow.md`: the cycle: review (brainstorming or QA),
  `/grill-me`, `/to-spec`, `/to-tickets`, implementation
  (`tools/overmind.sh run`), build and publish, `/retro`, and back to review.
  Read it before any of those.
- `.agents/context/issue-tracker.md`: cycles, specs and issues as local
  Markdown in this repo's `.scratch/<project>/`. Every ticket names its repo.
- `.agents/context/project-setup.md`: what a project repo provides;
  `/new-project` sets one up.
- `.agents/context/engineering.md`: the engineering defaults (uv, the
  shell, worktrees). A project's engineering doc adds its stack and wins.
  This machine's tools are in `.agents/context/machine.local.md` (not in
  git), when it exists.
- `.agents/context/publish-server.md`: how to publish (the same for Claude
  and Codex). A project lists only its outputs and their prepared folders.
- `.agents/skills/`: the skills, adapted from Matt Pocock's
  (https://github.com/mattpocock/skills).
- `tools/overmind.sh run`: the worker loop; `tools/overmind.sh next` and `status`: the
  next ready issue and every issue's status (Overmind, `tools/overmind/`). They
  take the project as an argument (`../<project>`).
- `tools/README.md`: tool folders, entry points and focused test commands.
- `overmind memory get ai-development/roadmap.md` (private, when memory is on): worker
  improvements, completed steps and next increments. Plans live in the store, not here.

## Standing rules

- **Act in the project's repo.** Code, docs, checks and commits for a project
  happen in its repo (`git -C ../<project>`), never here. Commit here only
  changes to the workflow itself.
- **Keep the repos independent.** No symlinks or references from a project
  to this repo. A project's files describe only the project.
- **Changing the workflow:** a change here reaches every project. `/retro`
  proposes changes; the user picks. Project details belong in the project's
  `.agents/context/`. Write for agents: short, plain, one instruction per
  sentence.
