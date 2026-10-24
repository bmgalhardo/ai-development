# Implementation workers

Run `tools/work.sh ../<game>` from this repo.
It starts one fresh session per attempt: implement, then two reviews in parallel, then fix.
It pins the latest cycle at startup.
It holds a per-game lock for the run, including quota waits.
Do not run standalone implementation sessions against that checkout while the loop owns it.
The loop never launches parallel implementations.

## Provider and model settings

| Variable | Default | Meaning |
|---|---|---|
| `WORK_AGENT` | `claude` | Preferred implementer: `codex` or `claude` |
| `WORK_FALLBACK_AGENT` | The other provider | Fallback implementer on quota exhaustion; `none` disables it |
| `WORK_REVIEW_AGENT` | The other provider | Reviewer sessions' provider; `none` keeps the review in the implementation session |
| `WORK_MODEL` | CLI configuration | Model for the preferred provider only |
| `WORK_REVIEW_MODEL` | CLI configuration | Model for the reviewer's sessions (the implementer's subagents when it reviews itself) |
| `WORK_CODEX_MODEL` / `WORK_CLAUDE_MODEL` | CLI configuration | Provider-specific model; overrides `WORK_MODEL` |
| `WORK_CODEX_REVIEW_MODEL` / `WORK_CLAUDE_REVIEW_MODEL` | CLI configuration | Provider-specific review model; overrides `WORK_REVIEW_MODEL` |
| `WORK_WAIT` | `1800` | Fallback cooldown seconds when no reset time is understood |
| `WORK_BUDGET_USD` | `15` | Claude CLI's per-attempt budget flag |

Model names belong to their provider.
The generic model settings never carry a Claude alias into Codex or vice versa.
An unset model preserves the CLI's configured default.
Reviewer sessions get their model as a CLI flag.
Only a self-review uses subagents; their model depends on the host's subagent model selector.
That review must report an unavailable selector and the actual model used.

```bash
WORK_MODEL=sonnet tools/work.sh ../<game>
WORK_REVIEW_AGENT=none tools/work.sh ../<game>
WORK_FALLBACK_AGENT=none tools/work.sh ../<game>
```

## Review pipeline

By default Claude implements and Codex reviews.

1. **Implement:** the implementer commits, sets the issue `in review` and exits.
2. **Review:** the runner starts one reviewer session per axis (Standards, Spec), in parallel. Each runs `/code-review` on its axis against `Base:` and edits nothing. Codex reviewers run in a read-only sandbox; Claude reviewers run without edit tools.
3. **Save:** the runner writes each final report to the cycle's `reviews/NN-standards.md` and `reviews/NN-spec.md`, with the reviewer and the reviewed commit.
4. **Fix:** a fresh implementer session (the implement skill's Fix session) handles the saved findings, commits and closes the issue.

The runner picks the step from the files: a missing review runs again; with both saved, the fixer runs.
A saved review is never repeated.
When the reviewer is cooling down, an available implementer reviews instead; the runner never waits for the reviewer.
The build issue keeps its review in the implementation session.

Both providers must already be authenticated for unattended fallback.
The preferred provider runs whenever its cooldown has expired.
An unavailable fallback executable is skipped.
Authentication failures stop the runner rather than consuming implementation retries.
Quota interruptions do not count toward the two implementation failures.
When every configured provider is cooling down, the runner waits for the earliest reset.
Cooldowns persist across runner restarts.
Time-only reset messages use their named timezone; unknown formats use `WORK_WAIT`.

## Recovery and observation

Artifacts live in `artifacts/work/<game>/`, ignored by Git.

- `current.json`: the latest attempts (both reviewers when they run together), with outcomes when finished.
- `attempts.jsonl`: completed attempts with role (`implement`, `review` or `fix`), review axis, provider, requested models, duration, exit code and outcome.
- `<attempt>.log`: native Codex JSONL or Claude JSON result plus CLI diagnostics.
- `<attempt>-recovery/`: HEAD, tracked binary patch, staged patch, untracked files and issue copy after an unfinished attempt.
- `cooldowns.json`: provider reset timestamps as Unix seconds.

The JSON records retain provider-reported usage in native units when available.
Empty usage means the CLI did not report it; do not treat it as zero.
These are not subscription quota estimates or comparable weighted-token totals.

The runner snapshots unfinished work after quota errors, failures and graceful interruption.
It does not reset, clean, commit, push or restore the game's files.
The next worker inspects the existing checkout and the issue's Progress section.
The patch records all tracked changes against the saved HEAD; the staged patch separately records the index.
The untracked archive excludes ignored files.
Keep recovery artifacts private, like the checkout itself.
Hard termination may prevent a snapshot; edits remain in the checkout.
Ctrl-C or SIGTERM stops the worker process group before recovery and exit.

Check status without starting a worker:

```bash
python3 tools/workers/next_issue.py ../<game> --status
tail -n 5 artifacts/work/<game>/attempts.jsonl
cat artifacts/work/<game>/current.json
```

## Deferred code debt

Workers record deferred findings in the cycle's `debt.md` and keep their source issue.
Relevant small prefactors can be committed before a feature.
Wider changes require their own approved ticket.
File size warnings require a recorded disposition, not an automatic refactor.
The build gathers unresolved debt into the game's `docs/review.md`.
Ticketing carries unresolved entries to the next cycle and assigns relevant work explicitly.
