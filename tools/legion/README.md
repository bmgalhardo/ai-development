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
- how to read its quota from its usage endpoint.

The base class holds what both CLIs share: the quota and login patterns, and the reset-time formats.
A provider may add its own.

## Dashboard

A read-only FastAPI board for every project's cycles:

```bash
tools/legion.sh dashboard
```

Open http://127.0.0.1:8765 on the same machine. The server is a separate process.
It never starts, stops or imports the worker runner, edits tickets, or writes worker artifacts.
Stop it with Ctrl-C. Use `--port 8766` to choose another port (default: `WORK_DASHBOARD_PORT`, else 8765).
It listens on this machine only by default. It has no login: to open it from another
device on your network, set `WORK_DASHBOARD_HOST=0.0.0.0` (in the environment or `.env`)
or pass `--host 0.0.0.0`, then open `http://<host-ip>:8765`. For access through SSH instead:

```bash
ssh -L 8765:127.0.0.1:8765 <worker-host>
```

The board refreshes every four seconds. Project and cycle selections are shareable URL parameters.
Click an issue to read its saved Standards and Spec review reports, full text and attempt history.
The reports come from the cycle's `reviews/NN-standards.md` and `reviews/NN-spec.md`.
Missing reports are shown as not yet saved. Review text is displayed as plain text.
Escape closes the details.
Waiting and Ready use the worker selector's dependency rules, including the final build exception.
Reviewing includes reviews and fixes; the active attempt gives the exact phase.
Stage colors fill column and card headers. Agent icons identify providers in the cards,
attempts and worker strip. Implementing and Reviewing headers show the active providers.
Codex uses the white OpenAI knot on green.
The knot comes from Devicons (`vorillaz/devicons`, `packages/core/export-files/icons/openai-icon.svg`);
its license is in `src/legion/dashboard/static/icons/DEVICONS-LICENSE.txt`.
Issue details scroll beneath a fixed header, keeping Close visible.
Opening issue details focuses the title. Tab moves to Close with a visible keyboard indicator.

### Account quotas

The quota panel reads each provider's usage endpoint at most once a minute: Claude with the host's Claude Code login, Codex with the worker's first login file.
It reads the tokens only: it never renews them and never serves them.
When an endpoint refuses or a login is missing, the panel says unavailable.
Each panel shows when its reading was taken, marked stale after three minutes.
Only provider, windows, percentages and reset times are served.
The runner doesn't use these readings.

### Worker status

The server reads `.scratch/<project>/<cycle>/issues/` and `work/` (the attempts), and `.scratch/<project>/runner/` (the runner).
The existing runner lock indicates that a runner or its children are alive.
Detection reads Linux's `/proc/locks` without acquiring the worker's lock.
It does not prove that an agent is making progress. Last log output age is shown separately.
An unfinished attempt with a released lock is stopped; its unknown duration is excluded from totals.
Recorded time sums attempts, including parallel review sessions, and is not wall-clock cycle duration.
No timestamps are invented for issue transitions. Provider cooldowns are displayed independently;
a cooldown for one provider does not imply that every provider is waiting.
A runner may be processing an older cycle than the latest selected cycle.

Partial JSON writes are retried on the next refresh with a visible warning.
An unreadable issue snapshot returns a retryable error and leaves the last board visible.
Native logs and recovery archives are not served. No database or frontend build is required.

## Tests

Run the tests from the workflow root, with the dashboard's dependencies:

```bash
uv run --project tools/legion --group dashboard python -m unittest discover -s tools/legion/tests
```
