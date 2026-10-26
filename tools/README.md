# Workflow tools

Keep each tool's implementation, tests and supporting assets in its own folder.
Keep the root `work.sh` as the stable worker entry point.

| Folder | Responsibility | Command from the repo root |
|---|---|---|
| `workers/` | Provider selection, issue readiness, cooldowns, recovery and attempt records | `tools/work.sh ../<project>` |
| `publish/` | Upload to the games server and its menu pages | `python3 tools/publish/publish.py ../<project>` |
| `dashboard/` | Read-only Kanban board and worker activity | `uv run --project tools/dashboard python -m tools.dashboard` |

The dashboard runs independently of workers at `http://<host-ip>:8765`.
`work.sh` starts it for the run when it isn't already running.
See `dashboard/README.md` for setup, status semantics and remote access.

Inspect issue status without starting a worker:

```bash
python3 tools/workers/next_issue.py ../<project> --status
```

Run the tests for the folder being changed:

```bash
python3 -m unittest discover -s tools/workers -t .
python3 -m unittest discover -s tools/publish -t .
uv run --project tools/dashboard python -m unittest discover -s tools/dashboard -t .
```

Run all tool tests after changes spanning folders:

```bash
uv run --project tools/dashboard python -m unittest discover -s tools -t .
```

The worker settings are in `.agents/context/workers.md`.
The implementation roadmap is in `.agents/context/roadmap.md`.
