#!/usr/bin/env bash
# Run one worker at a time, with quota fallback. See .agents/context/workers.md.
set -uo pipefail
cd "$(dirname "$(readlink -f "$0")")/.." || exit 1
exec python3 -m tools.workers.work "$@"
