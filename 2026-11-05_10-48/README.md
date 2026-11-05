# Patient manager: deployment repository

A Persian (right-to-left, Jalali calendar) patient-records web app for one private clinic. Node.js, Express, SQLite, Docker Compose and Caddy (automatic HTTPS).

This repository contains what is needed to run the site on a Linux server.

- `docs/DEPLOY-AGENT.md`: runbook for a Claude Code session that installs and updates the site on the server.
- `docs/SETUP.md`: the same install in plain steps for a person.
- `docs/TROUBLESHOOTING.md`: symptom to exact command.
- `scripts/deploy.sh`: updates a running server to the latest version.
- `docs/DEPLOY-AGENT-CUTOVER.md`: the one-time move of a clinic from this app (SQLite) to the new app (MySQL), when the owner says so.

Quick start on a server with Docker: copy `.env.example` to `.env`, set `DOMAIN`, run `mkdir -p data && sudo chown 1000:1000 data`, then `docker compose up -d --build`.
