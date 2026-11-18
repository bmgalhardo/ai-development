# Workflow tools

Keep each tool's implementation, tests and supporting assets in its own folder.

| Folder | Responsibility | Command from the repo root |
|---|---|---|
| `overmind/` | The worker loop, worker containers, issue tracker, dashboard and memory (the context store) | `tools/overmind.sh <run\|next\|status\|dashboard> ../<project>`, `tools/overmind.sh memory <command>` |
| `publish/` | Upload a build's outputs, or a review's mocks, to the publish server | `python3 tools/publish/publish.py ../<project> [mocks]` |
| `project/` | Check a project repo against the contract (`project-setup.md`) | `python3 tools/project/check_contract.py ../<project>` |

The dashboard runs independently of workers at http://127.0.0.1:8765.
The runner starts it for the run when it isn't already running.
See `overmind/README.md` for containers, the dashboard and remote access.

Inspect issue status without starting a worker:

```bash
tools/overmind.sh status ../<project>
tools/overmind.sh next ../<project>
```

Run the tests for the folder being changed:

```bash
uv run --project tools/overmind --group dashboard python -m unittest discover -s tools/overmind/tests
python3 -m unittest discover -s tools/publish -t .
python3 -m unittest discover -s tools/project -t .
```

Run all tool tests after changes spanning folders:

```bash
uv run --project tools/overmind --group dashboard python -m unittest discover -s tools/overmind/tests
python3 -m unittest discover -s tools -t .
```

The worker settings are in `.agents/context/workers.md`.
The implementation roadmap is in `.agents/context/roadmap.md`.
