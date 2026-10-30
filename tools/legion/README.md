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
- its container login (variables and mounts) and its session folder inside the container;
- how model and effort are passed;
- how to read its log events: messages, usage (in the CLI's own units) and the final report.
- how to read its quota from its usage endpoint.

The base class holds what both CLIs share: the quota and login patterns, and the reset-time formats.
A provider may add its own.

## Containers

With `WORK_CONTAINER=1`, the runner runs each session in a worker container: Claude Code and Codex CLIs, git, Python, uv and Node, as a non-root user.
The image recipes, the build script and the container's machine notes are in `src/legion/container/`, beside the `Container` class.
The `Container` class names no provider: each provider gives its own login and session folder.

### Build

```bash
tools/legion.sh build
```

It tags `legion-worker`, with the host user's uid and gid so files written to the mounts belong to them.
The CLI versions are pinned in the `Dockerfile`; bump them there.

A project with `.agents/container/Dockerfile` (`project-setup.md`) gets its own image on top:

```bash
tools/legion.sh build ../<project>
```

It builds the base, then `legion-<project>`, passing `BASE=legion-worker`.
While prototyping, a project's recipe can sit in `src/legion/container/prototype/<project>.Dockerfile` instead.
Rebuild the project's image after rebuilding the base.

### Run

The runner starts one container per session, with its provider and role.
To open a shell, or run a command, in one by hand:

```bash
tools/legion.sh shell <provider> <implement|review|fix> ../<project> [command...]
```

`src/legion/container/run.sh` takes the same arguments, with the project's path relative to the current folder.
Without a command it opens a shell.
One container runs one provider in one role, and is removed when the command exits.
The runner also removes a stopped session's container (a timeout or Ctrl-C), and, at startup, every container left over from a killed run of the project.

Each container is named `legion-<project>-<provider>-<role>-<id>` and labelled `legion.project`, `legion.provider`, `legion.role` and `legion.pid` (the Legion process that started it).

The container sees the same absolute paths as the host:

| Host | In the container | `implement`, `fix` | `review` |
|---|---|---|---|
| `AGENTS.md` | Same path, and as `CLAUDE.md` | Read-only | Read-only |
| `.agents/` | Same path, and as `.claude/` | Read-only | Read-only |
| `.scratch/<project>/` | Same path | Read-write | Read-only |
| `.scratch/<project>/sessions/<provider>/` | The CLI's session folder: `~/.claude/projects/` or `~/.codex/sessions/` | Read-write | Read-write |
| The project repo | Same path | Read-write | Read-only |

The links are the workflow root's own symbolic links to `AGENTS.md` and `.agents/`.
That is all a session reads from this repo: `tools/`, `.git`, `.env` and the other projects' scratch aren't there.
`src/legion/container/machine.md` replaces the host's `.agents/context/machine.local.md`, so a session reads the container's own notes.
It only can when the host has that file: a read-only mount can't cover a missing one.
The session folders keep each CLI's full log on the host, for the retro's `digest.py`.
An implementer can also reach them through its scratch, so a session could edit an earlier log.
The home, `/home/worker`, is the image's own, in the container's writable layer: nothing in it outlives the container.
Nothing else from the host is mounted: no `~/.ssh`, no personal `~/.claude` or `~/.codex`, no Docker socket.
It runs with `--cap-drop ALL`, `no-new-privileges`, and memory and process limits.
The host's git author (its `GIT_AUTHOR_*` variables, else its git config) is the container's author and committer.

| Variable | Default | Meaning |
|---|---|---|
| `WORK_CONTAINER` | `0` | `1` runs each session in a worker container |
| `WORK_LOGINS` | `.logins/` in this repo (git-ignored) | Folder with the login files |
| `WORK_IMAGE` | `legion-<project>` if built, else `legion-worker` | Image to run |
| `WORK_CONTAINER_MEMORY` | `1536m` | Memory limit |
| `WORK_CONTAINER_PIDS` | `512` | Process limit |

Codex's own `read-only` sandbox can't start in here: bubblewrap needs user namespaces, which the container doesn't allow.
A Codex reviewer runs with `danger-full-access`: the read-only mounts are the sandbox.
Codex skips its git repo check: the workflow folder has no `.git` in the container.

Don't mount anything under `/tmp/claude-<uid>`: Docker creates that path as root, and Claude refuses its temp directory.

### Logins

One file per provider, in `WORK_LOGINS`, mode `600`.
A container gets only its own provider's login.

- **`.claude.login`:** the token from `claude setup-token` on the host, alone in the file.
  The container gets it as `CLAUDE_CODE_OAUTH_TOKEN`; the file itself isn't mounted.
- **`.codex.login`:** Codex's `auth.json`, mounted writable as `~/.codex/auth.json` so Codex can save renewed tokens.
  To create it, in bash from this repo (keep the folder in a variable: a `VAR=... cmd` prefix lasts one command):

  ```bash
  dir=$(mktemp -d); CODEX_HOME=$dir codex login --device-auth && mv "$dir/auth.json" .logins/.codex.login && rm -rf "$dir"
  ```

  Codex renews about every eight days, and rewrites the file in place, so the renewal reaches the host through the mount.

Renewal replaces the refresh token, so one Codex session at a time uses a login (OpenAI's CI/CD auth guide: one `auth.json` per runner or serialized stream).
The Codex provider locks the login file for the container's life: a second Codex session takes `.codex-2.login` (then `-3`, ...) if it exists, else waits.
For the two reviewers to run in parallel, add `.codex-2.login` from a second device login.
The session can read its own login. Use logins made for the workers, never your own `~/.codex`.

### Treat the project as untrusted

The session can change anything in the project repo, `.git` included.
Don't run the project's code or git hooks on the host until the work is reviewed.

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

The quota panel reads each provider's usage endpoint at most once a minute.
Claude's uses the host's Claude Code login; Codex's uses the worker's first login file.
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
