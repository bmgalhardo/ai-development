# Development workflow: agent notes

The user's workspace for their projects (Godot games so far). Every session starts
here. This repo holds the shared workflow (the cycle, the skills, the
worker loop); each project is its own independent repo beside it
(`../<project>/`), with its own `AGENTS.md` and context.

`CLAUDE.md` is a symlink to this file, and `.claude/` is a symlink to
`.agents/`.

## The session's project

At the start of a session, establish which project it is about: the user
names it, or ask them. Skip this only when the work is on the workflow
itself (this repo). Then read `../<project>/CLAUDE.md` and follow its
pointers to that project's own context; from then on the session works on
that project. Paths in a project's files are relative to that project's root.

## The workflow

- `.agents/context/workflow.md`: the cycle: review (brainstorming or QA),
  `/grill-me`, `/to-spec`, `/to-tickets`, implementation
  (`tools/work.sh`), build and publish, `/retro`, and back to review.
  Read it before any of those.
- `.agents/context/issue-tracker.md`: cycles, specs and issues as local
  Markdown in this repo's `.scratch/<project>/`. Every ticket names its repo.
- `.agents/context/project-setup.md`: what a project repo provides.
- `.agents/context/machine.md`: the tools on this machine (uv, the shell,
  worktrees, display, Blender on hephaestus) and their gotchas. A project's
  own toolchain (such as Godot) is in its engineering doc.
- `.agents/context/publish-server.md`: how to publish (the same for Claude
  and Codex). A project lists only its outputs and their prepared folders.
- `.agents/skills/`: the skills, adapted from Matt Pocock's
  (https://github.com/mattpocock/skills).
- `tools/work.sh`: the worker loop; `tools/workers/next_issue.py`: the next
  ready issue. Both take the project as an argument (`../<project>`).
- `tools/README.md`: tool folders, entry points and focused test commands.
- `.agents/context/roadmap.md`: worker improvements, completed steps and next increments.

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
