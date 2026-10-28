# Worker container

The image the worker sessions run in: Claude Code and Codex CLIs, git, Python, uv and Node, as a non-root user.
Roadmap step 1 (`.agents/context/roadmap.md`). The runner doesn't use it yet.

## Build

```bash
tools/container/build.sh
```

It tags `workflow-worker`, with the host user's uid and gid so files written to the mounts belong to them.
The CLI versions are pinned in the `Dockerfile`; bump them there.

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
| The project repo | Same path | Read-write | Read-only |

That is all a session reads from this repo: `tools/`, `.git`, `.env` and the other projects' scratch aren't there.
`machine.md` here replaces the host's `.agents/context/machine.local.md`, so a session reads the container's own notes.
It only can when the host has that file: a read-only mount can't cover a missing one.
The home, `/home/worker`, is temporary: nothing in it outlives the container.
Nothing else from the host is mounted: no `~/.ssh`, no personal `~/.claude` or `~/.codex`, no Docker socket.
It runs with `--cap-drop ALL`, `no-new-privileges`, and memory and process limits.

| Variable | Default | Meaning |
|---|---|---|
| `WORK_LOGINS` | `~/.config/ai-workers` | Folder with the login files |
| `WORK_IMAGE` | `workflow-worker` | Image to run |
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
  To create it, log in with `codex login --device-auth` in a throwaway `CODEX_HOME` and move its `auth.json` here.
  Codex renews when its access token expires, about every ten days; that a renewal reaches the file through the mount is not yet verified.

Never give one `.codex.login` to two workers at once: renewal replaces the refresh token.
The session can read its own login. Use logins made for the workers, never your own `~/.codex`.

## Treat the project as untrusted

The session can change anything in the project repo, `.git` included.
Don't run the project's code or git hooks on the host until the work is reviewed.
