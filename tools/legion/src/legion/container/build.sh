#!/usr/bin/env bash
# Build the worker image with the host user's ids, then a project's image on it. See Legion's README.
# Usage: tools/legion.sh build [../<project>]
set -euo pipefail
here="$(dirname "$(readlink -f "$0")")"
# The host's local CAs go into the image; an empty folder when there are none.
cas=/usr/local/share/ca-certificates
[ -d "$cas" ] || cas="$(mktemp -d)"
docker build --build-context host-ca="$cas" --build-arg UID="$(id -u)" --build-arg GID="$(id -g)" \
    -t legion-worker "$here"
[ $# -ge 1 ] || exit 0
project="$(readlink -f "$1")"
name="$(basename "$project")"
# The project's own recipe, else one kept here while prototyping.
recipe="$project/.agents/container/Dockerfile"
[ -f "$recipe" ] || recipe="$here/prototype/$name.Dockerfile"
[ -f "$recipe" ] || { echo "No image recipe for $name: it runs on legion-worker" >&2; exit 0; }
exec docker build --build-arg BASE=legion-worker -t "legion-$name" -f "$recipe" "$(dirname "$recipe")"
