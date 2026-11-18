#!/usr/bin/env bash
# Overmind's commands, run from the workflow root. See tools/overmind/README.md.
set -uo pipefail
cd "$(dirname "$(readlink -f "$0")")/.." || exit 1
groups=()
# The runner starts the dashboard beside it, so both need the dashboard's dependencies.
case "${1:-}" in run | dashboard) groups=(--extra dashboard) ;; esac
exec uv run --quiet --project tools/overmind "${groups[@]}" overmind "$@"
