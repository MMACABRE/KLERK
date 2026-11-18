# KLERK «کلرک»: deployment release (new app)

Patient records for one private clinic: Persian, right to left, Jalali dates. Django, MySQL 8.4, Vue, Docker Compose
and Caddy (automatic HTTPS).

Start here:

| Who | Read |
|---|---|
| A person installing a new server | `docs/SETUP.md` |
| A Claude Code session on the server | `docs/DEPLOY-AGENT.md` (rules first) |
| A server that still runs the old app (`/opt/clinic-data/data/clinic.db`) | `docs/DEPLOY-AGENT-CUTOVER.md`, only on the owner's word |
| Something is wrong | `docs/TROUBLESHOOTING.md` |

Files:

- `deploy/check-server.sh`: checks the server and changes nothing (Docker, settings, disk, ports, DNS, image
  sources). Run it first.
- `deploy/deploy.sh`: installs or updates the site (`bash <release>/deploy/deploy.sh`). It gets the images first
  (nothing changes if that fails), backs up before an update and refuses a server that still holds the old app's
  database.
- `deploy/fetch-images.sh` and `deploy/images.lock`: nothing is built on the server. The finished images come from
  ghcr.io (by digest) or from one offline file (`klerk-images-<tag>.tar.gz`, SHA-256 in `images.lock`) that can be
  copied to `/opt/clinic-data/images/` by hand.
- `deploy/docker-compose.yml`: the services (mysql, backend, worker, caddy). Settings come from the clinic's
  `/opt/clinic-data/.env`.
- `backend/`, `frontend/`: the source the images were built from, for reference. The server does not build them.
