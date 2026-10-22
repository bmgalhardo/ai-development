# Workflow tools

Keep each tool's implementation, tests and supporting assets in its own folder.
Keep the root `work.sh` as the stable worker entry point.

| Folder | Responsibility | Command from the repo root |
|---|---|---|
| `workers/` | Provider selection, issue readiness, cooldowns, recovery and attempt records | `tools/work.sh ../<game>` |
| `review/` | Review-board rendering, debt inclusion and the HTML template | `python3 tools/review/render_review.py ../<game>` |

Inspect issue status without starting a worker:

```bash
python3 tools/workers/next_issue.py ../<game> --status
```

Run the tests for the folder being changed:

```bash
python3 -m unittest discover -s tools/workers -t .
python3 -m unittest discover -s tools/review -t .
```

Run all tool tests after changes spanning folders:

```bash
python3 -m unittest discover -s tools -t .
```

The worker settings are in `.agents/context/workers.md`.
The implementation roadmap is in `.agents/context/roadmap.md`.
