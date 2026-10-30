#!/usr/bin/env bash
# Legion's commands, run from the workflow root. See tools/legion/README.md.
set -uo pipefail
cd "$(dirname "$(readlink -f "$0")")/.." || exit 1
groups=()
[ "${1:-}" = dashboard ] && groups=(--group dashboard)
exec uv run --quiet --project tools/legion "${groups[@]}" legion "$@"
