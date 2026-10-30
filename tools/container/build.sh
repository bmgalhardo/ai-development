#!/usr/bin/env bash
# Build the worker image with the host user's ids, then a project's image on it. See README.md.
# Usage: tools/container/build.sh [../<project>]
set -euo pipefail
here="$(dirname "$(readlink -f "$0")")"
docker build --build-arg UID="$(id -u)" --build-arg GID="$(id -g)" -t workflow-worker "$here"
[ $# -ge 1 ] || exit 0
project="$(readlink -f "$1")"
name="$(basename "$project")"
# The project's own recipe, else one kept here while prototyping.
recipe="$project/.agents/container/Dockerfile"
[ -f "$recipe" ] || recipe="$here/prototype/$name.Dockerfile"
[ -f "$recipe" ] || { echo "No image recipe for $name: it runs on workflow-worker" >&2; exit 0; }
exec docker build --build-arg BASE=workflow-worker -t "work-$name" -f "$recipe" "$(dirname "$recipe")"
