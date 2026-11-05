#!/usr/bin/env bash
# Deploys the new app (Django + MySQL) from the release folder this script lives in. The release folder is only
# ever READ: settings, the database volume, patient files and backups live elsewhere, so a new release can start
# without touching them.
#
#   bash <release-folder>/deploy/deploy.sh
#
# Layout (same as the old app's):
#   $CLINIC_DATA_ROOT/.env   settings: DOMAIN, TZ, DATA_PATH=$CLINIC_DATA_ROOT/data, and the three secrets below
#   $CLINIC_DATA_ROOT/data/  patients/, backups/, trash/, sms.key (owned by uid 10001, the backend user)
# Secrets: MYSQL_PASSWORD, MYSQL_ROOT_PASSWORD and DJANGO_SECRET_KEY are created in .env when missing (never printed,
# existing values are kept). It writes `current-release` and the wrapper `dc` into $CLINIC_DATA_ROOT:
#   $CLINIC_DATA_ROOT/dc ps        dc logs --tail 50 backend        dc exec -T backend python manage.py backup
#
# Refuses to start on a server that still holds the old app's SQLite database (data/clinic.db) unless the cutover
# finished (docs/DEPLOY-AGENT-CUTOVER.md writes $CLINIC_DATA_ROOT/cutover-done): otherwise the clinic would get an
# empty new database.
#
# Steps: check settings, back up the running database, build and start this release, wait until backend and
# worker are healthy, check the public HTTPS address. On failure it prints how to restart the previous release.
set -euo pipefail

release=$(cd "$(dirname "$0")/.." && pwd)
root=$(cd "${CLINIC_DATA_ROOT:-/opt/clinic-data}" && pwd)
env_file="$root/.env"
cd "$release"
fail() { echo "FAILED: $1" >&2; exit 1; }
setting() { grep -E "^$1=" "$env_file" | head -1 | cut -d= -f2- | tr -d '\r"' | xargs || true; }

[ -f "$env_file" ] || fail "$env_file is missing (it needs DOMAIN, DATA_PATH and TZ; see docs/DEPLOY-AGENT-CUTOVER.md)"
data=$(setting DATA_PATH)
case "$data" in
  /* | [A-Za-z]:*) ;;
  *) fail "DATA_PATH in $env_file must be an absolute path outside the release folder, e.g. $root/data" ;;
esac
[ -n "$(setting DOMAIN)" ] || fail "DOMAIN is not set in $env_file"

if [ -e "$data/clinic.db" ] && [ ! -e "$root/cutover-done" ]; then
  fail "$data/clinic.db is the old app's database and this server has not been cut over. Do not deploy this
release as an update: follow docs/DEPLOY-AGENT-CUTOVER.md, and only on the owner's word."
fi

# Secrets: add each one only if missing. Values are random and never printed. An existing value is never changed (a
# running database depends on it), so a placeholder copied from deploy/.env.example (the dev template) or an empty
# value is refused here instead of becoming the clinic's real password.
for key in MYSQL_PASSWORD MYSQL_ROOT_PASSWORD DJANGO_SECRET_KEY; do
  if grep -q "^$key=" "$env_file"; then
    value=$(setting "$key")
    if [ -z "$value" ] || [ "$value" = replace-me ]; then
      fail "$key in $env_file is empty or the placeholder 'replace-me'. On a new server delete that line and run
again: this script then writes a random value. Never change it on a server whose database already runs."
    fi
  else
    echo "$key=$(openssl rand -hex 32)" >> "$env_file"
  fi
done
chmod 600 "$env_file"

mkdir -p "$data"
if [ "$(uname)" = Linux ] && [ "$(stat -c %u "$data")" != 10001 ]; then
  fail "the backend runs as user 10001; run: sudo chown -R 10001:10001 $data"
fi

previous=""
[ -f "$root/current-release" ] && previous=$(cat "$root/current-release")

compose() { docker compose --env-file "$env_file" -f "$release/deploy/docker-compose.yml" "$@"; }

running=$(docker ps -q --filter label=com.docker.compose.project=clinic --filter label=com.docker.compose.service=backend)
if [ -n "$running" ]; then
  docker exec "$running" python manage.py backup || fail "the backup before the update failed; nothing was changed"
fi

compose build
compose up -d --remove-orphans

rollback_hint() {
  echo "FAILED: $1" >&2
  if [ -n "$previous" ] && [ "$previous" != "$release" ]; then
    echo "Restart the previous release with:  bash $previous/deploy/deploy.sh" >&2
    echo "(If that folder has no deploy/deploy.sh, it is the old app: see the rollback in docs/DEPLOY-AGENT-CUTOVER.md.)" >&2
  else
    echo "Read the logs: docker compose --env-file $env_file -f $release/deploy/docker-compose.yml logs --tail 50" >&2
  fi
  exit 1
}

wait_healthy() {
  local status=starting
  for _ in $(seq 1 "$2"); do
    status=$(docker inspect --format '{{.State.Health.Status}}' "$(compose ps -q "$1")" 2>/dev/null || echo starting)
    [ "$status" = healthy ] && return 0
    sleep 2
  done
  rollback_hint "$1 is '$status' after $(( $2 * 2 )) s (check: compose logs --tail 50 $1)"
}
wait_healthy backend 90
# Fresh install only: the default accounts, payment methods and the «ویزیت» service. It does nothing on a database
# that already has them (an update, or a clinic copied over by tools/migrate_sqlite.py).
compose exec -T backend python manage.py seed_defaults || rollback_hint "seeding the default payment methods failed"
# One backup with the new release proves the dump works and the data folder is writable (owner 10001).
compose exec -T backend python manage.py backup || rollback_hint "the backup with the new release failed (owner of $data and its subfolders must be 10001)"
wait_healthy worker 450

domain=$(setting DOMAIN)
port=$(setting HTTPS_PORT)
url="https://$domain${port:+:$port}/health"
curl_opts=(-s -m 5)
[ "$domain" = localhost ] && curl_opts+=(-k)   # a local test uses a self-signed certificate
for _ in $(seq 1 30); do
  if [ "$(curl "${curl_opts[@]}" "$url" || true)" = ok ]; then
    echo "$release" > "$root/current-release"
    cat > "$root/dc" <<EOF
#!/bin/sh
# Runs docker compose for the release that is currently deployed. Written by deploy/deploy.sh.
root=\$(cd "\$(dirname "\$0")" && pwd)
exec docker compose --env-file "\$root/.env" -f "\$(cat "\$root/current-release")/deploy/docker-compose.yml" "\$@"
EOF
    chmod +x "$root/dc"
    echo "OK: $url answers; running release $release"
    exit 0
  fi
  sleep 2
done
rollback_hint "$url does not answer (the certificate may still be pending: check the caddy logs)"
