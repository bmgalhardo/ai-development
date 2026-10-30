#!/usr/bin/env bash
# Run a command in a worker container for a project. See README.md.
# Usage: tools/container/run.sh <claude|codex> <implement|review> ../<project> [command...]   (default: bash)
set -euo pipefail
usage="usage: run.sh <claude|codex> <implement|review> ../<project> [command...]"
[ $# -ge 3 ] || { echo "$usage" >&2; exit 2; }
provider="$1" role="$2"
project="$(readlink -f "$3")"
shift 3
workflow="$(readlink -f "$(dirname "$(readlink -f "$0")")/../..")"
name="$(basename "$project")"
scratch="$workflow/.scratch/$name"
logins="${WORK_LOGINS:-$workflow/.logins}"
sessions="$scratch/sessions/$provider"
mkdir -p "$scratch" "$sessions"

case "$role" in
    implement) access=rw ;;
    review) access=ro ;;
    *) echo "$usage" >&2; exit 2 ;;
esac

# Each container gets only its own provider's login.
case "$provider" in
    claude)
        CLAUDE_CODE_OAUTH_TOKEN="$(cat "$logins/.claude.login")"
        export CLAUDE_CODE_OAUTH_TOKEN
        login=(-e CLAUDE_CODE_OAUTH_TOKEN -v "$sessions:/home/worker/.claude/projects") ;;
    codex)
        [ -f "$logins/.codex.login" ] || { echo "No $logins/.codex.login" >&2; exit 1; }
        # Renewal replaces the refresh token, so one session at a time per login: take a free one
        # (.codex.login, .codex-2.login, ...), else wait for the first. The lock lasts as long as docker runs.
        codex_login=""
        for file in "$logins/.codex.login" "$logins"/.codex-*.login; do
            [ -f "$file" ] || continue
            exec 9<"$file"
            if flock -n 9; then codex_login="$file"; break; fi
        done
        if [ -z "$codex_login" ]; then
            codex_login="$logins/.codex.login"
            exec 9<"$codex_login"
            flock 9
        fi
        # Writable, so Codex can save renewed tokens; it rewrites the file in place.
        login=(-v "$codex_login:/home/worker/.codex/auth.json" -v "$sessions:/home/worker/.codex/sessions") ;;
    *) echo "$usage" >&2; exit 2 ;;
esac

# Only what a session reads from this repo: the agent notes, skills and context; .claude and CLAUDE.md are their links.
# The host's machine notes become the container's own; a read-only mount can't cover a missing file.
here="$(dirname "$(readlink -f "$0")")"
workflow_mounts=()
for link in AGENTS.md CLAUDE.md; do workflow_mounts+=(-v "$workflow/AGENTS.md:$workflow/$link:ro"); done
for link in .agents .claude; do
    workflow_mounts+=(-v "$workflow/.agents:$workflow/$link:ro")
    [ -f "$workflow/.agents/context/machine.local.md" ] \
        && workflow_mounts+=(-v "$here/machine.md:$workflow/$link/context/machine.local.md:ro")
done

export GIT_AUTHOR_NAME="${GIT_AUTHOR_NAME:-$(git config user.name || true)}"
export GIT_AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL:-$(git config user.email || true)}"
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME" GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"

tty=()
[ -t 0 ] && [ -t 1 ] && tty=(-it)

# The project's image when it has one (build.sh ../<project>), else the base.
image="${WORK_IMAGE:-work-$name}"
docker image inspect "$image" >/dev/null 2>&1 || image=workflow-worker

# Same absolute paths as the host. A reviewer gets the project and its scratch read-only.
exec docker run --rm "${tty[@]}" --init \
    --name "work-$name-$provider-$role-$$" \
    --label work.project="$name" --label work.provider="$provider" --label work.role="$role" --label work.pid="$$" \
    --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges \
    --memory "${WORK_CONTAINER_MEMORY:-1536m}" --pids-limit "${WORK_CONTAINER_PIDS:-512}" \
    "${workflow_mounts[@]}" \
    -v "$scratch:$scratch:$access" -v "$project:$project:$access" \
    "${login[@]}" \
    -e GIT_AUTHOR_NAME -e GIT_AUTHOR_EMAIL -e GIT_COMMITTER_NAME -e GIT_COMMITTER_EMAIL \
    -w "$workflow" "$image" "${@:-bash}"
