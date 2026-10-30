# Legion

Runs and observes the implementation of tickets by coding agents: the worker loop, its containers, the tracker reader and the dashboard, as one package.
It reads the tracker as `.agents/context/issue-tracker.md` defines it, in the workflow repo's `.scratch/`.

Legion is a uv project with its own dependencies, and imports nothing from the rest of `tools/`.
Run its commands from the workflow root through the wrapper, which runs them there:

```bash
tools/legion.sh next ../<project>     # the next issue a worker should take, or nothing
tools/legion.sh status ../<project>   # every issue's status in the current cycle
```

The current cycle is the oldest with an issue ready or under way, else the newest.
An issue left `in progress` comes first, then one `in review`, then the first `open` issue whose `Blocked by` issues are all `done`.
The last issue (the build) is ready once every other issue is `done` or `blocked`.
Paths print relative to the workflow root.

## Settings

`settings.py` is the only code that reads the environment and the workflow root's `.env`.
Every setting is a `WORK_` variable; the environment wins over `.env`.
Unknown `WORK_` keys in `.env` are ignored. An invalid value stops the command, naming the variable.
`WORK_ROOT` is the workflow repo (default: the current folder, which the wrapper sets).

Run the tests from the workflow root:

```bash
uv run --project tools/legion python -m unittest discover -s tools/legion/tests
```
