# Issue dashboard

A read-only FastAPI dashboard for every project's cycles. Run from the workflow repo root:

```bash
uv run --project tools/dashboard python -m tools.dashboard
```

Open http://127.0.0.1:8765 on the same machine. The server is a separate process.
It never starts, stops or imports the worker runner, edits tickets, or writes worker artifacts.
Stop it with Ctrl-C. Use `--port 8766` to choose another port.
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
its license is in `static/icons/DEVICONS-LICENSE.txt`.
Issue details scroll beneath a fixed header, keeping Close visible.
Opening issue details focuses the title. Tab moves to Close with a visible keyboard indicator.

## Account quotas

Quotas are optional. When the Moshi helper `moshi-hook` is installed, the separate `/api/quotas` endpoint runs
`moshi-hook usage` at most once per minute. It never uses `--sync` or reads credentials.
The helper provides the same type of account quota snapshots Moshi uses.
Only provider, quota windows, percentages and capture/reset times are served.
Account IDs, account labels and host identity are excluded.
Quota collection runs independently of issue refreshes and never invokes a model.
These quotas apply to the signed-in accounts across projects, not just the selected project.
Missing data is shown as unavailable. Each panel shows the time of the last quota reading.
Readings older than three minutes explain that Moshi has no newer reading available.
If collection fails, the last successful snapshot remains visible as stale.
The provider's capture time is preserved; a successful poll does not imply a new measurement.

## Worker status

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

Run the focused tests from the workflow repo root:

```bash
uv run --project tools/dashboard python -m unittest discover -s tools/dashboard -t .
```

`tools/work.sh` starts this server when nothing listens on its port (`WORK_DASHBOARD=0`
skips it) and stops it when the runner exits. Its log is `.scratch/<project>/runner/dashboard.log`.
