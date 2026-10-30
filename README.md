# ai-development

A shared development workflow for AI coding agents (Claude Code and Codex).
This repo holds the cycle, the skills and the tools. Each project is its own
independent git repo beside it (`../<project>/`) and never refers back here.

## The cycle

1. **Review:** brainstorm a new direction, or QA the published build. Mocks
   and assets are made with the user while the feedback is fresh.
2. **Refinement:** `/grill-me`, then `/to-spec`, then `/to-tickets`.
3. **Implementation:** `tools/work.sh ../<project>` runs workers on the
   ready issues, without the user.
4. **Build and publish:** the last issue gathers the evidence, writes the
   project's `docs/review.md` and prepares the outputs. The loop publishes
   them, if a publish server is set up.
5. **Retro:** `/retro` proposes changes to the workflow; the user picks.

The details are in [`.agents/context/workflow.md`](.agents/context/workflow.md).
The skills are adapted from [Matt Pocock's](https://github.com/mattpocock/skills).

## Layout

| Path | What |
|---|---|
| `AGENTS.md` | The agents' entry point (`CLAUDE.md` links to it) |
| `.agents/context/` | The workflow, issue tracker, project contract, engineering defaults, publishing, roadmap |
| `.agents/skills/` | The skills (`.claude/` links to `.agents/`) |
| `tools/` | The worker loop, publisher, contract check and dashboard ([`tools/README.md`](tools/README.md)) |
| `.scratch/<project>/` | Each project's cycles: feedback, mocks, specs, issues (not in git) |

## Getting started

Clone this repo next to your projects:

```
projects/
  ai-development/   this repo; start every session here
  <project>/        a project repo with its own AGENTS.md and context
```

- Start a session here and name the project.
- Set up a new project, or adopt an existing repo, with `/new-project`.
  Check one with `python3 tools/project/check_contract.py ../<project>`.
- Local settings go in `.env` (not in git): `PUBLISH_URL` for the publish
  server, `WORK_DASHBOARD_HOST` for the dashboard. Both are optional.
- This machine's tools go in `.agents/context/machine.local.md` (not in git).

## Requirements

Python 3 and [uv](https://docs.astral.sh/uv/), plus the agent CLIs the
workers use (Claude Code, Codex). The tool test commands are in
`tools/README.md`.
