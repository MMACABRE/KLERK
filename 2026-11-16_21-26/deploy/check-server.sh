#!/usr/bin/env bash
# Checks a server before an install, update or cutover, and changes nothing. Prints one OK, WARN or FAIL line per
# check, then a summary. Exit code 0 when nothing failed.
#
#   bash <release>/deploy/check-server.sh
#
# Reads $CLINIC_DATA_ROOT/.env (default /opt/clinic-data/.env) only for DOMAIN, DATA_PATH and HTTPS_PORT, and only
# counts the secret lines; it never prints a secret.
set -uo pipefail
release=$(cd "$(dirname "$0")/.." && pwd)
root=${CLINIC_DATA_ROOT:-/opt/clinic-data}
env_file="$root/.env"
lock="$release/deploy/images.lock"
fails=0; warns=0
ok()   { echo "OK    $1"; }
warn() { echo "WARN  $1"; warns=$((warns + 1)); }
bad()  { echo "FAIL  $1"; fails=$((fails + 1)); }
setting() { grep -E "^$1=" "$env_file" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r"' | xargs || true; }
lockval() { grep -E "^$1=" "$lock" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r'; }

# Docker
if docker version --format '{{.Server.Version}}' >/dev/null 2>&1; then
  ok "docker $(docker version --format '{{.Server.Version}}')"
else
  bad "docker does not answer (not installed, not running, or this user is not in the docker group)"
fi
if docker compose version --short >/dev/null 2>&1; then
  ok "docker compose $(docker compose version --short)"
else
  bad "docker compose is missing (install the docker-compose-plugin package)"
fi

# Release folder
[ -f "$lock" ] && ok "release $(basename "$release"), images $(lockval IMAGES_TAG)" ||
  bad "$lock is missing: this release folder is incomplete"

# Settings
if [ -f "$env_file" ]; then
  ok "$env_file exists"
  domain=$(setting DOMAIN)
  [ -n "$domain" ] && ok "DOMAIN=$domain" || bad "DOMAIN is not set in $env_file"
  data=$(setting DATA_PATH)
  case "$data" in
    /*) ok "DATA_PATH=$data" ;;
    *) bad "DATA_PATH in $env_file must be an absolute path, e.g. $root/data" ;;
  esac
  n=$(grep -cE '^(MYSQL_PASSWORD|MYSQL_ROOT_PASSWORD|DJANGO_SECRET_KEY)=' "$env_file" || true)
  [ "$n" = 3 ] && ok "the three secrets are set" || ok "$n of 3 secrets set (deploy.sh adds the missing ones)"
  if [ -n "$data" ] && [ -d "$data" ]; then
    owner=$(stat -c %u "$data" 2>/dev/null || echo "?")
    [ "$owner" = 10001 ] && ok "$data is owned by uid 10001" ||
      bad "$data is owned by uid $owner; the app needs: sudo chown -R 10001:10001 $data"
    if [ -e "$data/clinic.db" ]; then
      [ -e "$root/cutover-done" ] && ok "old database present, cutover done" ||
        warn "$data/clinic.db exists: this server runs the old app. Only docs/DEPLOY-AGENT-CUTOVER.md, on the owner's word"
    fi
  fi
else
  bad "$env_file is missing (docs/DEPLOY-AGENT.md, fresh install step 7)"
  domain=""
fi

# Disk: the images need about 2 GB, the offline file about 0.5 GB more.
free=$(df -Pk "$root" 2>/dev/null | awk 'NR==2 {print int($4/1048576)}')
if [ -z "$free" ]; then warn "cannot read the free space of $root"
elif [ "$free" -ge 5 ]; then ok "${free} GB free on $root"
else bad "only ${free} GB free on $root (need at least 5 GB)"; fi

# Ports 80 and 443: free, or held by this clinic's own Caddy.
for port in 80 "${HTTPS_PORT:-443}"; do
  holder=$(docker ps --filter "publish=$port" --format '{{.Names}}' 2>/dev/null | head -1)
  if [ -n "$holder" ]; then
    case "$holder" in clinic-*) ok "port $port is used by $holder (this clinic)" ;; *) bad "port $port is used by container $holder" ;; esac
  elif command -v ss >/dev/null && ss -ltnH "( sport = :$port )" 2>/dev/null | grep -q .; then
    bad "port $port is used by another program: sudo ss -ltnp 'sport = :$port'"
  else
    ok "port $port is free"
  fi
done

# DNS: the domain must point at this server.
if [ -n "$domain" ] && [ "$domain" != localhost ]; then
  resolved=$(getent ahostsv4 "$domain" 2>/dev/null | awk 'NR==1 {print $1}')
  mine=$(hostname -I 2>/dev/null)
  if [ -z "$resolved" ]; then bad "$domain does not resolve (needs input: the owner sets the DNS A record)"
  elif echo " $mine " | grep -q " $resolved "; then ok "$domain points at this server ($resolved)"
  else warn "$domain points at $resolved; this server's addresses are: $mine (fine behind NAT, otherwise fix DNS)"; fi
fi

# Where the images can come from. One working source is enough.
src=0
if [ -n "$(lockval BACKEND_IMAGE)" ] && docker image inspect "$(lockval BACKEND_IMAGE)" >/dev/null 2>&1; then
  ok "the images are already on this server"; src=1
fi
[ -f "$root/images/$(lockval IMAGES_TAR)" ] && { ok "offline file present: $root/images/$(lockval IMAGES_TAR)"; src=1; }
if curl -s -m 10 -o /dev/null -w '%{http_code}' https://ghcr.io/v2/ | grep -qE '^(200|401)$'; then
  ok "ghcr.io answers"; src=1
else
  warn "ghcr.io does not answer"
fi
if curl -s -m 10 -o /dev/null -w '%{http_code}' https://github.com/ | grep -qE '^(200|301|302)$'; then
  ok "github.com answers (git pull and the offline file)"; src=1
else
  warn "github.com does not answer"
fi
[ "$src" = 1 ] || bad "no way to get the images: copy $(lockval IMAGES_TAR) to $root/images/ by scp or USB"

echo
echo "summary: $fails failed, $warns warnings"
[ "$fails" = 0 ]
