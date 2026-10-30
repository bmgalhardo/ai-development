# Worker container

The image the worker sessions run in: Claude Code and Codex CLIs, git, Python, uv and Node, as a non-root user.
Roadmap step 1 (`.agents/context/roadmap.md`). The runner doesn't use it yet.

## Build

```bash
tools/container/build.sh
```

It tags `workflow-worker`, with the host user's uid and gid so files written to the mounts belong to them.
The CLI versions are pinned in the `Dockerfile`; bump them there.

A project with `.agents/container/Dockerfile` (`project-setup.md`) gets its own image on top:

```bash
tools/container/build.sh ../<project>
```

It builds the base, then `work-<project>`, passing `BASE=workflow-worker`.
While prototyping, a project's recipe can sit here instead, as `prototype/<project>.Dockerfile`.
Rebuild the project's image after rebuilding the base.

## Run

```bash
tools/container/run.sh <claude|codex> <implement|review> ../<project> [command...]
```

Without a command it opens a shell.
One container runs one provider in one role, and is removed when the command exits.

The container sees the same absolute paths as the host:

| Host | In the container | `implement` | `review` |
|---|---|---|---|
| `AGENTS.md` | Same path, and as `CLAUDE.md` | Read-only | Read-only |
| `.agents/` | Same path, and as `.claude/` | Read-only | Read-only |
| `.scratch/<project>/` | Same path | Read-write | Read-only |
| `.scratch/<project>/sessions/<provider>/` | The CLI's session folder: `~/.claude/projects/` or `~/.codex/sessions/` | Read-write | Read-write |
| The project repo | Same path | Read-write | Read-only |

That is all a session reads from this repo: `tools/`, `.git`, `.env` and the other projects' scratch aren't there.
`machine.md` here replaces the host's `.agents/context/machine.local.md`, so a session reads the container's own notes.
It only can when the host has that file: a read-only mount can't cover a missing one.
The session folders keep each CLI's full log on the host, for the retro's `digest.py`.
An implementer can also reach them through its scratch, so a session could edit an earlier log.
The home, `/home/worker`, is the image's own, in the container's writable layer: nothing in it outlives the container.
Nothing else from the host is mounted: no `~/.ssh`, no personal `~/.claude` or `~/.codex`, no Docker socket.
It runs with `--cap-drop ALL`, `no-new-privileges`, and memory and process limits.

| Variable | Default | Meaning |
|---|---|---|
| `WORK_LOGINS` | `.logins/` in this repo (git-ignored) | Folder with the login files |
| `WORK_IMAGE` | `work-<project>` if built, else `workflow-worker` | Image to run |
| `WORK_CONTAINER_MEMORY` | `1536m` | Memory limit |
| `WORK_CONTAINER_PIDS` | `512` | Process limit |

Codex's own `read-only` sandbox can't start in here: bubblewrap needs user namespaces, which the container doesn't allow.
A Codex reviewer runs with `danger-full-access`: the read-only mounts are the sandbox.

Don't mount anything under `/tmp/claude-<uid>`: Docker creates that path as root, and Claude refuses its temp directory.

## Logins

One file per provider, in `WORK_LOGINS`, mode `600`.
A container gets only its own provider's login.

- **`.claude.login`:** the token from `claude setup-token` on the host, alone in the file.
  `run.sh` passes it as `CLAUDE_CODE_OAUTH_TOKEN`; the file itself isn't mounted.
- **`.codex.login`:** Codex's `auth.json`, mounted writable as `~/.codex/auth.json` so Codex can save renewed tokens.
  To create it, in bash from this repo (keep the folder in a variable: a `VAR=... cmd` prefix lasts one command):

  ```bash
  dir=$(mktemp -d); CODEX_HOME=$dir codex login --device-auth && mv "$dir/auth.json" .logins/.codex.login && rm -rf "$dir"
  ```

  Codex renews about every eight days, and rewrites the file in place, so the renewal reaches the host through the mount.

Renewal replaces the refresh token, so one Codex session at a time uses a login (OpenAI's CI/CD auth guide: one `auth.json` per runner or serialized stream).
`run.sh` locks the login file for the container's life: a second Codex session takes `.codex-2.login` (then `-3`, ...) if it exists, else waits.
For the two reviewers to run in parallel, add `.codex-2.login` from a second device login.
The session can read its own login. Use logins made for the workers, never your own `~/.codex`.

## Treat the project as untrusted

The session can change anything in the project repo, `.git` included.
Don't run the project's code or git hooks on the host until the work is reviewed.
