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
logins="${WORK_LOGINS:-$HOME/.config/ai-workers}"
ids="uid=$(id -u),gid=$(id -g),mode=700"
mkdir -p "$scratch"

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
        login=(-e CLAUDE_CODE_OAUTH_TOKEN) ;;
    codex)
        [ -f "$logins/.codex.login" ] || { echo "No $logins/.codex.login" >&2; exit 1; }
        # Writable, so Codex can save renewed tokens.
        login=(--tmpfs "/home/worker/.codex:$ids" -v "$logins/.codex.login:/home/worker/.codex/auth.json") ;;
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

# Same absolute paths as the host. A reviewer gets the project and its scratch read-only.
exec docker run --rm "${tty[@]}" --init \
    --name "work-$name-$provider-$role-$$" \
    --label work.project="$name" --label work.provider="$provider" --label work.role="$role" \
    --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges \
    --memory "${WORK_CONTAINER_MEMORY:-1536m}" --pids-limit "${WORK_CONTAINER_PIDS:-512}" \
    "${workflow_mounts[@]}" \
    -v "$scratch:$scratch:$access" -v "$project:$project:$access" \
    --tmpfs "/home/worker:$ids" -e HOME=/home/worker "${login[@]}" \
    -e GIT_AUTHOR_NAME -e GIT_AUTHOR_EMAIL -e GIT_COMMITTER_NAME -e GIT_COMMITTER_EMAIL \
    -w "$workflow" "${WORK_IMAGE:-workflow-worker}" "${@:-bash}"
