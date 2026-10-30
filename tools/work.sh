#!/usr/bin/env bash
# Run the worker loop on a project: tools/legion.sh run. See .agents/context/workers.md.
exec "$(dirname "$(readlink -f "$0")")/legion.sh" run "$@"
