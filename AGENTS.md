# Game development workflow: agent notes

The shared workflow for the user's Godot game projects. Each project sits
beside this repo (`../<project>/`) and links the skills in; nothing here
is project-specific.

`CLAUDE.md` is a symlink to this file.

- `context/workflow.md`: the cycle: review (brainstorming or QA),
  `/grill-me`, `/to-spec`, `/to-tickets`, implementation
  (`tools/work.sh`), build and publish, `/retro`, and back to review.
- `context/issue-tracker.md`: cycles, specs and issues as local Markdown
  in each project's `.scratch/`.
- `context/project-setup.md`: what a project provides and how it links
  the skills.
- `skills/`: the skills, adapted from Matt Pocock's
  (https://github.com/mattpocock/skills).
- `tools/`: `work.sh` (the worker loop) and `next_issue.py`. They act on
  the git repo of the current directory: run them from a project's root.
- `CODING_STANDARDS.md`: the default standards (Clean Code for Godot).

## Changing it

A change here reaches every project. `/retro` proposes changes from a
project's cycle; the user picks. Keep project details out: they belong in
the project's `.agents/context/`. Write for agents: short, plain, one
instruction per sentence.
