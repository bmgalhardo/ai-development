# Agentic queues roadmap

Updated: 2026-10-24.
This roadmap concerns the shared workflow, not a project feature cycle.
The previous project cycle is complete.
Future increments below are proposed work, not instructions to implement them automatically.

## Direction

Keep review, grill, spec, tickets, implementation, build and publication.
Evolve worker execution beneath that cycle.
Keep Markdown as the human-readable requirements and review record.
Eventually let independent container workers claim dependency-ready jobs from a durable queue.
Use subscription-authenticated Claude Code and Codex workers.
Treat provider quota exhaustion as an interrupted attempt, not a blocked issue.

## Current implementation: quick wins complete

- Keep `tools/work.sh ../<project>` as the worker entry point.
- Run one implementation at a time per project, with a per-project runner lock.
- Prefer `WORK_AGENT` (Claude); fall back to the other installed provider on quota exhaustion.
- Review each issue in two parallel read-only sessions by `WORK_REVIEW_AGENT` (Codex), one per axis, then fix in a fresh implementer session.
- Save review reports in the cycle's `reviews/`; never repeat a saved review.
- Persist provider cooldowns and wait when both configured providers are unavailable.
- Configure implementation models and request review models separately per provider.
- Preserve commits and unfinished edits, including work whose checks fail.
- Snapshot tracked edits, the index, untracked files, HEAD and the issue after unfinished attempts.
- Record attempt outcomes, durations and available provider-native usage.
- Hand work to the other provider on authentication failures; retry a failure with the other provider; stop after two implementation failures.
- Record completed implementation and review steps in each issue's Progress section.
- Keep deferred findings in each cycle's `debt.md` with source and disposition.
- Carry unresolved debt into the next cycle during ticketing.
- Assign small relevant prefactors explicitly; propose separate tickets for wider refactors.
- Render the debt register in the review and as its own board page.

Code is grouped by responsibility:

- `tools/workers/`: readiness, execution, provider handling, recovery and tests.
- `tools/review/`: board rendering, template and tests.
- `tools/README.md`: entry points and focused test commands.
- `workers.md`: current configuration and artifact formats.

These quick wins remain sequential and use the project's existing checkout and branch.
There are no container workers, isolated attempt branches, queue service or progress dashboard yet.
Recovery snapshots occur after an attempt ends, not periodically during execution.
A self-review's subagent model depends on the host's selector and must be reported honestly.
Usage records are not estimates of remaining subscription quota.

## 1. Container workers

Package the coding CLIs and each project's toolchain.
Retain the existing worker command.
Start with one active implementation per project.
Inject credentials at runtime and preserve authentication state outside images.
Keep provider credentials, Git credentials and generated artifacts out of images and commits.
Use a dedicated authentication state per worker stream.
Do not share a Codex auth cache between concurrent workers.
Verify current provider authentication guidance before implementation.

Done when recreating a worker preserves login and unfinished work, and it can complete an issue through the existing command.

## 2. Isolated attempts and durable checkpoints

Give each issue attempt an isolated checkout and its own branch.
Save progress at meaningful boundaries and push checkpoints to the Git remote.
Preserve failing work as a checkpoint without calling the issue complete.
Record completed steps, checks, reviewed commit and remaining work for handoff.
A replacement uses a new attempt branch so an old worker cannot overwrite it.
Keep completed review findings and avoid repeating reviews of unchanged implementation.

Done when a killed worker's replacement recovers a pushed checkpoint and finishes without changing another attempt's files.

## 3. Durable queue and ownership

Add one coordinator with a transactional database; SQLite is sufficient for an initial single-host coordinator.
Import requirements and dependencies from existing Markdown tickets.
Make the coordinator authoritative for execution state and mirror status back into issue files.
Claim jobs atomically with leases, attempt IDs and heartbeats.
Reject stale attempts after ownership changes.
Release quota-interrupted work and cool down that provider.
Separate infrastructure interruptions from implementation failures.
Bound retries that repeat the same failure without progress.
Persist handoffs and provider state across restarts.

Done when two workers cannot claim the same issue, expired leases are recoverable, and a stale worker cannot complete a reassigned job.

## 4. Progress UI

Start with a read-only dashboard over the coordinator.
Show dependencies, ready jobs, active attempts, provider cooldowns and authentication failures.
Show logs, checkpoints, review stage, integration state and unresolved debt.
Show attempt duration and provider-reported usage without inventing quota estimates.
Add retry, cancel and provider switching only after ownership and cancellation semantics are reliable.

Done when the user can understand what is running or waiting without watching worker terminals.

## 5. Parallel execution and integration

Run one Claude worker and one Codex worker concurrently on independent ready issues.
Use dependencies and declared touched modules to avoid obvious overlap.
Serialize integration into the project's main development branch.
Check each result against the latest integrated state before pushing it.
Mark an issue done only after integration succeeds.
Start dependents from that integrated state.
Return conflicts or failed combined checks for repair.
Run the final build after all integrations finish.
Prefer this integration rule to stacked PRs initially.

Done when two independent issues integrate successfully and their dependent issue starts with both changes present.

## 6. Always-on remote hosting

Move the coordinator and workers to an always-on host.
Keep the worker protocol independent of where containers run.
Use a remote database only if the deployment needs one.
Verify that credential renewal, artifact persistence and provider cooldowns survive host restarts.

Done when work continues after the local terminal closes and progress remains accessible.

## 7. Generic projects: deploy and review

Proposed at the 03-prototype retro (2026-10-26), for making the workflow project-agnostic.
Split today's build issue into a project deploy and a workflow review.
The project declares a deploy command in its context, like its check command.
The project picks when it deploys: per issue (like CI after a merge) or per cycle.
The review stops being a ticket: when the loop ends, however it ends, a review step writes `review.md`.
That review lists blocked issues and the issues they kept from running, with their reasons.
Done at that retro: the build ticket only prepares the outputs; the worker loop publishes them when the build is done; the review publishes its own mocks; a project without a publishing doc deploys nothing.
This removes the build issue's special readiness rule in `next_issue.py`.
Today a blocked issue with a dependent chain leaves the build issue never ready, so nothing is published.

Done when a cycle with a blocked issue still deploys its finished work and its review names the block.

## Evidence and evaluation

The last retrospective reported two quota interruptions involving about 14% of the cycle's weighted usage.
Committed work and uncommitted work were discarded under the previous restart rule.
Large starting context and running every worker on the largest model increased consumption.
Deferred structural findings never reached the next worker or became assigned refactor work.

Measure elapsed time, quota waiting, repeated work, successful completion and usage per accepted issue.
Compare quality and total accepted-issue cost before changing default models.
Do not equate interrupted-attempt usage with wholly wasted tokens.
A fresh quota window can reduce early interruptions but cannot eliminate multi-window cycle demand.

Ralph implementations are references for handoffs, bounded continuation, metrics and circuit breakers.
The current workflow already uses fresh workers, persisted tickets, checks and commits.
Do not replace it solely to adopt a Ralph task-file format or a same-session stop hook.
