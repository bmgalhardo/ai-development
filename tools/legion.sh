#!/usr/bin/env bash
# Legion's commands, run from the workflow root. See tools/legion/README.md.
set -uo pipefail
cd "$(dirname "$(readlink -f "$0")")/.." || exit 1
exec uv run --quiet --project tools/legion legion "$@"
