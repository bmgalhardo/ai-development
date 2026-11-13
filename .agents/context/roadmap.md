# Agentic queues roadmap

Updated: 2026-11-12.
This roadmap concerns the shared workflow, not a project feature cycle.
The previous project cycle is complete.
Future increments below are proposed work, not instructions to implement them automatically.

## Agreed direction: GitHub-backed epics and worker queue

Agreed with the user on 2026-11-10. This is the next direction for the
shared workflow. GitHub is the default platform for repos, epics/tickets,
pull requests, checks, builds and deployments. Use GitHub-hosted runners
where they fit; add homelab self-hosted runners only for hardware or private
network needs (for example Blender on `hephaestus`). Do not self-host a Git
platform without a concrete need.

Keep two ways to prepare work, converging on the same epic and ticket model:

- PM-led: review, `/grill-me`, `/to-spec`, `/to-tickets`; user approves
  product decisions and ticket breakdown.
- Delegated: an explicitly authorized coordinator resolves decisions within
  stated scope and constraints, then produces the same spec and tickets.
  Escalate decisions outside its authority to the user.

One review becomes one epic. Several epics may be refined at once and then
released independently into a shared ready-ticket queue. Each epic closes
only after its tickets, integration/build and deployment succeed. Blocked
work goes to a coordinator with evidence and attempted approaches; continue
unrelated work. Escalate unresolved product decisions or disagreements to
the user. Treat consensus as meeting acceptance criteria with evidence, not
as agents agreeing with one another.

Parallelize independent implementer tickets and independent research avenues.
During cycle review, a research skill proposes a bounded number of agents and
usage budget for the user's approval; an approved allocation covers that
research batch. Record conclusions and unresolved questions in the cycle.
Asset production (including Blender) is a later worker type with explicit
inputs, output ownership and validation.

Git flow: workers use isolated worktrees/branches and open PRs. Ticket PRs
target their epic branch; reviewed changes must merge before dependents start.
After implementation tickets and the epic's integration/docs work complete,
the epic PR targets `main`. GitHub Actions runs checks/build/deploy and
records the deployed commit. Serialize deployments to the shared destination.
An epic closes only after successful deployment; failed builds/deploys remain
retryable. Overmind schedules work and observes GitHub state rather than owning
PR, build or deployment state itself.

Worker guard (from 03-prototype's boss-balance retro, 2026-11-11): workers
still poll with `until`/`while … sleep` loops and `Monitor` despite
`engineering.md`; one loop never matched and held the run. Give Claude
workers a `PreToolUse` hook that denies `Monitor` and Bash sleep loops, as
part of increment 2.

### Proposed increments

1. **GitHub workflow contract and pilot.** Choose GitHub Issues/Projects
   representation for epics and tickets, PR branch rules, required checks,
   credentials and event/status mapping. Pilot one epic manually end to end
   with GitHub Actions before changing Overmind. Define how cycle specs/assets
   are made available to workers without creating duplicate sources of truth.
2. **Isolated ticket PRs.** Give each worker an isolated checkout and branch;
   push checkpoints, open/update its ticket PR, and resume safely. Merge a
   reviewed ticket PR into the epic branch before marking it done or starting
   dependents. Repair conflicts and combined-check failures against the
   latest epic branch.
3. **Epic release lifecycle.** Track epic states from review/released through
   implementation, release, deployment and closed. Run integration/docs work
   after all ticket PRs merge, then the epic PR and deployment. Record commit,
   artifact and deployment result; retry failures without duplicate deploys.
4. **Queue scheduler and coordinator.** Poll or receive GitHub events; claim
   ready tickets across released epics with leases and ownership. Dispatch
   independent work concurrently, retain dependency ordering, and route
   blocked tickets to a coordinator. Escalate unresolved decisions to the
   user; continue unrelated tickets.
5. **Research skill and budgeted parallel research.** During review, identify
   unknowns and independent avenues, propose agent count and a usage bound,
   wait for user approval, run researchers, reconcile findings, and write
   evidence into the cycle. Do not spawn research agents outside the approved
   batch allocation.
6. **Homelab runners and asset workers.** Add self-hosted GitHub runners only
   where hosted runners cannot meet a concrete need. First candidate:
   Blender work on `hephaestus`; define queueing, power lifecycle, artifact
   return and validation before scheduling it.

Keep the current local Markdown workflow usable during migration. Pilot and
measure one epic before moving the queue authority; migrate existing cycles
only after the GitHub contract and recovery behavior are proven. Preserve the
homelab repo's existing uncommitted changes while assessing runner placement.

## Open alternative: Overmind as the home base, in the homelab

Discussed with the user on 2026-11-13. Not decided; keep every option open.
It would replace GitHub Issues and PRs in the direction above; git hosting stays.

- **Session context.** A `SessionStart` hook fetches an L0 map from Overmind: projects, active epics, ticket counts, pending decisions, latest build.
  An L1 report per project (decisions, blocked tickets, the build to play) is fetched on demand; L2 is the files.
  If Overmind is down, the hook says so and sessions work from files.
- **Decisions queue.** Collect `Needs the user:` lines, manual tickets and coordinator escalations, each with question, options, evidence and the tickets it holds.
- **Hosting.** Overmind as a Deployment on elysium (Apollo), managed by Flux from the homelab repo, with an HTTPRoute, a Vault certificate and secrets through VSO.
  Reached from daedalus and through the VPN. Reads unauthenticated; writes take a token.
- **Records.** Specs, tickets, reviews, debt and decisions in a private git repo (`overmind-records`, on GitHub for off-site backup).
  Overmind clones it at start, is its only writer, and commits in batches. Session logs go to stdout and Argus.
  Runtime state (leases, attempts, cooldowns) is rebuilt on restart, so no volume is needed.
- **No PRs.** Parallel work needs branches and isolated checkouts, not PRs.
  Reviewers read `git diff epic...ticket`; Overmind merges reviewed tickets into the epic branch one at a time and re-runs checks.
  A PR could mirror a diff for reading later.
- **Workers as Jobs.** One Kubernetes Job per attempt in `overmind-workers`: clone, check out the ticket branch, run the CLI, push.
  Overmind's ServiceAccount may only create, watch and delete Jobs there. Concurrency is an Overmind setting plus resource requests.
  Claude authenticates with `claude setup-token`; Codex rewrites `auth.json` on renewal, so it needs a writable login per worker (open problem).
- **Images.** GitHub Actions builds the base image (on change and nightly) and each project image (on Dockerfile or lockfile change) into GHCR.
  Tag project images by a hash of their recipe files; Overmind picks the tag from the ticket branch and triggers a missing build.
  An in-cluster registry and builder is the alternative if GHCR limits bite.
- **Telegram.** Done: send-only notifications from the runner (blocked issue, run end; `workers.md`).
  Later: buttons that answer a decision; a text reply that starts a headless coordinator Job; a direction that starts the delegated path, released with one tap.
  Use long polling (`getUpdates`), so nothing is exposed; accept only the user's ID.

Possible order: L0/L1 API with the hook and decisions queue; images on Actions; workers as Jobs; scheduler across released epics; Telegram answers.

## Direction

Keep review, grill, spec, tickets, implementation, build and publication.
Evolve worker execution beneath that cycle.
Keep Markdown as the human-readable requirements and review record.
Eventually let independent container workers claim dependency-ready jobs from a durable queue.
Use subscription-authenticated Claude Code and Codex workers.
Treat provider quota exhaustion as an interrupted attempt, not a blocked issue.

## Current implementation: quick wins complete

- Overmind (`tools/overmind/`) is the worker loop, the worker containers, the issue tracker and the dashboard, in one uv package.
- Run it with `tools/overmind.sh <run|next|status|dashboard> ../<project>`.
- Run one implementation at a time per project, with a per-project runner lock.
- Take providers in `OVERMIND_PREFERENCE` order.
- Hand work to the next provider when one is cooling down or fails.
- Review each issue in two parallel read-only sessions, one per axis, by a provider other than the implementer when one is available, then fix in a fresh implementer session.
- Save review reports in the cycle's `reviews/`; never repeat a saved review.
- Persist provider cooldowns and wait when both configured providers are unavailable.
- Configure a model and an effort per provider and role (`workers.md`).
- Preserve commits and unfinished edits, including work whose checks fail.
- Snapshot tracked edits, the index, untracked files, HEAD and the issue after unfinished attempts.
- Record attempt outcomes, durations and available provider-native usage.
- Hand work to the other provider on authentication failures; retry a failure with the other provider; stop after two implementation failures.
- Record completed implementation and review steps in each issue's Progress section.
- Keep deferred findings in each cycle's `debt.md` with source and disposition.
- Carry unresolved debt into the next cycle during ticketing.
- Assign small relevant prefactors explicitly; propose separate tickets for wider refactors.
- Render the debt register in the review and as its own board page.

Code is grouped by responsibility.
Overmind's package is `tools/overmind/src/overmind/`:

- `settings.py`: the `OVERMIND_` settings.
- `tracker.py`: issue readiness and status.
- `providers/`: Claude and Codex commands, log parsing and logins.
- `runner/`: the loop, the router, sessions, attempts, recovery with the safe git, and cooldowns.
- `container/`: the `Container` arguments, image recipes, build and shell wrapper.
- `dashboard/`: the board, quotas and its API.

Around it:

- `tools/overmind/tests/`: the loop end to end, the router, provider parsing, the dashboard API and the small checks.
- `tools/README.md`: entry points and focused test commands.
- `workers.md`: current configuration and artifact formats.

These quick wins remain sequential and use the project's existing checkout and branch.
Containers are the default; `OVERMIND_CONTAINER=0` runs sessions on the host.
There are no isolated attempt branches or queue service yet.
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

Progress (2026-10-28):

- Done: the base image (`overmind-worker`) and Overmind's shell wrapper (`tools/overmind/README.md`: Containers).
  One provider and one role per container; each gets only its own login file, from `.logins/` (git-ignored).
  A reviewer gets the project read-only: Codex's own sandbox can't start in a container.
- Done: a project image (`overmind-<project>`, from the project's `.agents/container/Dockerfile`); 03-prototype's check, captures and Web export pass in it.
- Done: `OVERMIND_CONTAINER=1` in the runner; a stopped attempt's container is removed, and leftovers at startup.
- Done: each CLI's session files in `.scratch/<project>/sessions/`, read by the retro digest.
- Done: the runner's git refuses a project `.git` that can run commands; publishing refuses symlinks.
- Done: one Codex session per login file at a time; `.codex-2.login` lets reviewers run in parallel.
- Done: issue 01 of 03-prototype's cycle through implement, review and fix in containers, resumed after its container was killed.
- Open: a Codex renewal through the single-file mount is unobserved; Codex rewrites the file in place, so it should reach the host.

## 2. Isolated attempts and durable checkpoints

Folded into increment 2 of the agreed direction (2026-11-12).
A checkpoint is a push to the ticket's PR branch.
The done criterion below still applies.

Give each issue attempt an isolated checkout and its own branch.
Save progress at meaningful boundaries and push checkpoints to the Git remote.
Preserve failing work as a checkpoint without calling the issue complete.
Record completed steps, checks, reviewed commit and remaining work for handoff.
A replacement uses a new attempt branch so an old worker cannot overwrite it.
Keep completed review findings and avoid repeating reviews of unchanged implementation.

Done when a killed worker's replacement recovers a pushed checkpoint and finishes without changing another attempt's files.

## 3. Durable queue and ownership

Folded into increment 4 of the agreed direction (2026-11-12).
GitHub owns ticket, PR, build and deployment state.
The coordinator's database holds only leases, attempts, heartbeats and provider state.

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

Folded into increments 2 and 4 of the agreed direction (2026-11-12).
Integration targets the epic branch through ticket PRs, not `main` directly.

Run one Claude worker and one Codex worker concurrently on independent ready issues.
Use dependencies and declared touched modules to avoid obvious overlap.
Serialize ticket PR merges into the epic branch.
Check each result against the latest integrated state before pushing it.
Mark an issue done only after integration succeeds.
Start dependents from that integrated state.
Return conflicts or failed combined checks for repair.
Run the final build after all integrations finish.
Do not stack ticket PRs on one another; each targets the epic branch.

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
This removes the build issue's special readiness rule in Overmind's tracker.
Today a blocked issue with a dependent chain leaves the build issue never ready, so nothing is published.

Done when a cycle with a blocked issue still deploys its finished work and its review names the block.

## 8. Usage limits from the session files

An idea from the 03-prototype retro (2026-10-27), not planned.
The loop recognises usage limits by parsing each CLI's message, which broke once on a changed apostrophe.
Both CLIs also write the limit to their session files: Claude's transcript has `rate_limit_info.resetsAt`; Codex's rollout has `rate_limits.primary` and `secondary`, with `used_percent` and `resets_at`, on every turn.
Read the reset time from there first, and keep the message parsing as the fallback, since the formats are undocumented.
Codex's `used_percent` would also let the loop skip Codex before starting when it is near its limit.

Done when a quota stop waits until the reset time the session file gives, and a near-limit Codex is skipped before it starts.

## 9. End-of-run report

Proposed at the Overmind retro (2026-10-30).
A run ended on 03-prototype with its build issue unpublished, and only the terminal said so; the dashboard stops with the run.
When the loop ends, however it ends, print a report as its last lines.
It lists each issue's status, every `blocked` issue with its `Needs the user:` lines, the run's failures and the after-build result.
At the failure limit, set the issue `blocked` instead of leaving it `in progress`.

Done when a run that ends with an issue needing the user says so in its last lines.

## 10. Manual tickets

Proposed at the Overmind retro (2026-10-30), after the Overmind cycle's switch-over ticket had to ask the user while `/implement` says never to.
A manual ticket is work done with the user: approvals, settings, merges, images, a run checked by hand.
It is an ordinary issue with a `**Manual:** yes` line, and keeps its blocking edges, acceptance boxes and Progress.
It stays `open` until its blockers are done, then it is ready like any other.
The dashboard shows a ready manual ticket with its own mark.
The runner never starts a session on a manual ticket.
When a manual ticket is the next ready issue, the runner launches nothing else, prints that the user must act (`/implement <NN>`, by hand), and waits.
While it waits it reads the issue file, as during a quota wait. It goes on once the ticket is `done`, and stops with its report when the ticket is `blocked`.
`/implement` on a manual ticket asks the user at the steps the ticket names, and closes it with step 11 as usual.
`/to-tickets` marks a ticket manual when its work needs the user.

Done when a cycle with a manual ticket in the middle runs to its build, waiting once for the user's hand-run `/implement`.

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
