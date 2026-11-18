#!/usr/bin/env bash
# Open a shell, or run a command, in a worker container for a project, by hand. See Overmind's README.
# Usage: run.sh <provider> <implement|review|fix> ../<project> [command...]   (default: bash)
set -euo pipefail
[ $# -ge 3 ] || { echo "usage: run.sh <provider> <implement|review|fix> ../<project> [command...]" >&2; exit 2; }
provider="$1" role="$2" project="$(readlink -f "$3")"
shift 3
exec "$(dirname "$(readlink -f "$0")")/../../../../../overmind.sh" shell "$provider" "$role" "$project" "$@"
