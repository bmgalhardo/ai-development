#!/usr/bin/env bash
# Build the worker image with the host user's ids, then a project's image on it. See Overmind's README.
# Usage: tools/overmind.sh build [../<project>]
set -euo pipefail
here="$(dirname "$(readlink -f "$0")")"
# The host's local CAs go into the image; an empty folder when there are none.
cas=/usr/local/share/ca-certificates
[ -d "$cas" ] || cas="$(mktemp -d)"
docker build --build-context host-ca="$cas" --build-arg UID="$(id -u)" --build-arg GID="$(id -g)" \
    -t overmind-worker "$here"
[ $# -ge 1 ] || exit 0
project="$(readlink -f "$1")"
name="$(basename "$project")"
# The project's own recipe, in its repo.
recipe="$project/.agents/container/Dockerfile"
[ -f "$recipe" ] || { echo "No image recipe for $name: it runs on overmind-worker" >&2; exit 0; }
exec docker build --build-arg BASE=overmind-worker -t "overmind-$name" -f "$recipe" "$(dirname "$recipe")"
