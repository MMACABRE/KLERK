# KLERK «کلرک»: deployment release (new app)

Patient records for one private clinic: Persian, right to left, Jalali dates. Django, MySQL 8.4, Vue, Docker Compose
and Caddy (automatic HTTPS).

- `deploy/deploy.sh`: installs or updates the site on a server (`bash <release>/deploy/deploy.sh`). It backs up
  before an update and refuses a server that still holds the old app's database.
- `docs/DEPLOY-AGENT-CUTOVER.md`: the one-time move of a clinic from the old app (SQLite) to this one, and how to
  update, back up and restore afterwards. Only on the owner's word.
- `docs/DEPLOY-AGENT.md`, `docs/SETUP.md`, `docs/TROUBLESHOOTING.md`: a fresh install for the server agent and for
  a person, and symptom to exact command.
- `deploy/docker-compose.yml`: the services (mysql, backend, worker, caddy). Settings come from the clinic's
  `/opt/clinic-data/.env`.
