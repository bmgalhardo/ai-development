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

`WORK_PREFERENCE` lists the providers to use, in order (default: every installed provider, in the registry's order).
Each provider has a model and an effort per role: `WORK_<PROVIDER>__<ROLE>__MODEL` and `__EFFORT`, for the roles `implement`, `review` and `fix`.
An unset model keeps the CLI's default.
Effort defaults to `medium`.
`fix` falls back to `implement` for each unset value.
Effort must be one of the provider's own values.

## Providers

Each provider is one file in `src/legion/providers/`: a subclass of `Provider`.
The registry is the subclasses present: deleting a provider's file removes it.
No other code names a provider.
A provider defines:

- its CLI and its flags;
- its flags per role and in a container;
- how model and effort are passed;
- how to read its log events: messages, usage (in the CLI's own units) and the final report.

The base class holds what both CLIs share: the quota and login patterns, and the reset-time formats.
A provider may add its own.

Run the tests from the workflow root:

```bash
uv run --project tools/legion python -m unittest discover -s tools/legion/tests
```
