#!/usr/bin/env bash
# Puts this release's finished images (backend, web, mysql) on the server. Nothing is built here: the images are
# built on the developer's computer by tools/build-images.sh and pinned in deploy/images.lock.
#
#   bash <release>/deploy/fetch-images.sh          (deploy/deploy.sh runs it for you)
#
# Tries, in order, and stops at the first that works:
#   1. the images are already on this server
#   2. the offline file in $CLINIC_DATA_ROOT/images/ (default /opt/clinic-data/images/), if someone copied it there
#   3. ghcr.io, pulled by digest
#   4. download the offline file from the GitHub Release named in images.lock
# The offline file is loaded only when its SHA-256 matches images.lock, and pulls are by digest, so a changed image
# is refused. If all four fail it says exactly which file to copy to the server by other means.
set -euo pipefail
release=$(cd "$(dirname "$0")/.." && pwd)
root=${CLINIC_DATA_ROOT:-/opt/clinic-data}
lock="$release/deploy/images.lock"
fail() { echo "FAILED: $1" >&2; exit 1; }
[ -f "$lock" ] || fail "$lock is missing: this release folder is incomplete"
get() { grep -E "^$1=" "$lock" | head -1 | cut -d= -f2- | tr -d '\r'; }
names=(BACKEND WEB MYSQL)

have_all() {
  local n
  for n in "${names[@]}"; do docker image inspect "$(get "${n}_IMAGE")" >/dev/null 2>&1 || return 1; done
}

load_file() {
  local got want
  want=$(get IMAGES_TAR_SHA256)
  got=$(sha256sum "$1" | cut -d' ' -f1)
  if [ "$got" != "$want" ]; then
    echo "  $1 does not match images.lock (SHA-256 $got, expected $want): not loaded" >&2
    return 1
  fi
  docker load -i "$1"
}

pull_all() {
  local n img dig
  for n in "${names[@]}"; do
    img=$(get "${n}_IMAGE"); dig=$(get "${n}_DIGEST")
    docker pull -q "${img%:*}@$dig" >/dev/null || return 1
    docker tag "${img%:*}@$dig" "$img"
  done
}

ok() { echo "OK: images $(get IMAGES_TAG) are on this server ($1)"; exit 0; }

have_all && ok "already here"

file="$root/images/$(get IMAGES_TAR)"
if [ -f "$file" ]; then
  echo "loading $file"
  load_file "$file" && have_all && ok "loaded from the offline file"
fi

echo "pulling from ghcr.io"
pull_all 2>/dev/null && have_all && ok "pulled from ghcr.io"

url=$(get IMAGES_TAR_URL)
echo "ghcr.io did not answer; downloading $url"
mkdir -p "$root/images"
if curl -fL --retry 3 --retry-delay 5 -C - -o "$file.part" "$url"; then
  mv "$file.part" "$file"
  load_file "$file" && have_all && ok "downloaded the offline file"
fi

fail "could not get the images. needs input: copy the file $(get IMAGES_TAR) (from $url) to $file on this
server by any other way (scp, USB), then run this again. Its SHA-256 must be $(get IMAGES_TAR_SHA256)."
