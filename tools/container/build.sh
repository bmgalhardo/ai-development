#!/usr/bin/env bash
# Build the worker image with the host user's ids. See README.md.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
exec docker build --build-arg UID="$(id -u)" --build-arg GID="$(id -g)" -t workflow-worker "$@" .
