# Implementation workers

Run `tools/legion.sh run ../<project>` from this repo.
The loop is Legion's runner (`tools/legion/`).
It also starts the dashboard on port 8765 unless something already listens there.
The dashboard stops with the runner; its log is `.scratch/<project>/runner/dashboard.log`.
It starts one fresh session per attempt: implement, then two reviews in parallel, then fix.
At startup it pins the current cycle: the oldest with an issue ready or under way, else the newest with issues.
A cycle ticketed while another is still being built waits for it.
It holds a per-project lock for the run, including quota waits.
Do not run standalone implementation sessions against that checkout while the loop owns it.
The loop never launches parallel implementations.

## Provider and model settings

Each setting can also sit in this repo's `.env` (not in git), as `KEY=value`; the environment wins.
Unknown `LEGION_` keys in `.env` are ignored; an invalid value stops the run, naming the variable.

| Variable | Default | Meaning |
|---|---|---|
| `LEGION_PREFERENCE` | Every installed provider, Claude first | The providers to use, in order: `claude,codex`, or `claude` alone |
| `LEGION_<PROVIDER>__<ROLE>__MODEL` | CLI configuration | The provider's model for a role: `implement`, `review` or `fix` (e.g. `LEGION_CLAUDE__IMPLEMENT__MODEL`) |
| `LEGION_<PROVIDER>__<ROLE>__EFFORT` | `medium` | The provider's effort for a role, one of its own values (Claude: low to max; Codex: minimal to xhigh) |
| `LEGION_AFTER_BUILD` | Empty | A command run once the build issue is done; `{project}` is the project's path; empty does nothing |
| `LEGION_WAIT` | `1800` | Fallback cooldown seconds when no reset time is understood |
| `LEGION_TIMEOUT` | `14400` | Seconds before an attempt is stopped; a stopped attempt whose issue isn't finished counts as a failure (`timeout`) |
| `LEGION_BUDGET_USD` | `15` | Claude CLI's per-attempt budget flag |
| `LEGION_CONTAINER` | `0` | `1` runs each session in a worker container (Legion's README: Containers) |
| `LEGION_DASHBOARD` | `1` | `0` skips starting the dashboard |
| `LEGION_DASHBOARD_PORT` | `8765` | Dashboard port |
| `LEGION_DASHBOARD_HOST` | `127.0.0.1` | Dashboard bind address; `0.0.0.0` opens it to the network (no login) |

A `fix` setting left unset falls back to the provider's `implement` setting.
Model names belong to their provider: each provider has its own settings.
An unset model preserves the CLI's configured default.
Every session gets its model and effort as CLI flags.
To publish the build when the loop ends, set `LEGION_AFTER_BUILD=python3 tools/publish/publish.py {project}`.

```bash
LEGION_CLAUDE__IMPLEMENT__MODEL=sonnet tools/legion.sh run ../<project>
LEGION_PREFERENCE=claude tools/legion.sh run ../<project>
```

## Review pipeline

With `LEGION_PREFERENCE=claude,codex`, Claude implements and Codex reviews.

1. **Implement:** the implementer commits, sets the issue `in review` and exits.
2. **Review:** the runner starts one reviewer session per axis (Standards, Spec), in parallel. Each runs `/code-review` on its axis against `Base:` and edits nothing. Codex reviewers run in a read-only sandbox; Claude reviewers run without edit tools.
3. **Save:** the runner writes each final report to the cycle's `reviews/NN-standards.md` and `reviews/NN-spec.md`, with the reviewer and the reviewed commit.
4. **Fix:** a fresh implementer session (the implement skill's Fix session) handles the saved findings, commits and closes the issue: `done` when every acceptance box is ticked, else `blocked` with a `Needs the user:` line per unmet box.

Every issue, the build included, gets two separate reviewer sessions and a fixer.
The loop never asks a session to review itself.
The runner picks the step from the files: a missing review runs again; with both saved, the fixer runs.
A saved review is never repeated.

Implement and fix take the first available provider in `LEGION_PREFERENCE`.
A review takes the first available provider other than the issue's implementer, else the implementer.
The issue's implementer is the provider of its last implement attempt in `attempts.jsonl`.
A review never waits for a cooling reviewer.
With one provider, it implements, reviews and fixes.

Every provider in the preference must already be authenticated for unattended fallback.
A provider whose CLI isn't installed is skipped.
An authentication failure sets that provider aside until the runner restarts; another provider continues the issue.
The runner stops only when no provider in the preference is signed in.
Authentication failures do not count toward the two implementation failures.
After a failure, the retry uses a different provider when one is ready.
Quota interruptions do not count toward the two implementation failures.
When every provider is cooling down, the runner waits for the earliest reset.
Cooldowns persist across runner restarts.
Time-only reset messages use their named timezone; unknown formats use `LEGION_WAIT`.
An attempt still running after `LEGION_TIMEOUT` is stopped with its process group; the issue's status decides its outcome.

## Recovery and observation

A cycle's attempts live with its issues, in `.scratch/<project>/<cycle>/work/`:

- `attempts.jsonl`: completed attempts with role (`implement`, `review` or `fix`), review axis, provider, requested model and effort, duration, exit code and outcome.
- `<attempt>.log`: native Codex JSONL or Claude JSON result plus CLI diagnostics.
- `<attempt>-recovery/`: HEAD, tracked binary patch, staged patch, untracked files and issue copy after an unfinished attempt.

The runner's own state lives in `.scratch/<project>/runner/`:

- `current.json`: the latest attempts (both reviewers when they run together), with outcomes when finished.
- `runner.lock`: held while a runner or its children are alive.
- `dashboard.log`: the dashboard's output.

`.scratch/runner/cooldowns.json` holds provider reset timestamps as Unix seconds, shared by every project's runner: a provider's quota is per account.

The JSON records retain provider-reported usage in native units when available.
Empty usage means the CLI did not report it; do not treat it as zero.
These are not subscription quota estimates or comparable weighted-token totals.

The runner snapshots unfinished work after quota errors, failures and graceful interruption.
It does not reset, clean, commit, push or restore the project's files.
The next worker inspects the existing checkout and the issue's Progress section.
The patch records all tracked changes against the saved HEAD; the staged patch separately records the index.
The untracked archive excludes ignored files.
Keep recovery artifacts private, like the checkout itself.
Hard termination may prevent a snapshot; edits remain in the checkout.
Ctrl-C or SIGTERM stops the worker process group before recovery and exit.

Check status without starting a worker:

```bash
tools/legion.sh status ../<project>
tail -n 5 .scratch/<project>/<cycle>/work/attempts.jsonl
cat .scratch/<project>/runner/current.json
```

## Deferred code debt

Workers record deferred findings in the cycle's `debt.md` and keep their source issue.
Relevant small prefactors can be committed before a feature.
Wider changes require their own approved ticket.
File size warnings require a recorded disposition, not an automatic refactor.
The build gathers unresolved debt into the project's `docs/review.md`.
Ticketing carries unresolved entries to the next cycle and assigns relevant work explicitly.
