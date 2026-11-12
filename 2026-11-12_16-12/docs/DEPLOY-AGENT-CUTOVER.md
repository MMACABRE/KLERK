# Cutover: move one clinic from the old app (SQLite) to the new app (MySQL)

For the server agent. Read all of it before you start. It adds to the rules in `docs/DEPLOY-AGENT.md` of the old
release; those rules still apply (never read or print patient data, the repository is read-only for you, ask before
any destructive command). Once the owner has said "cut over this server", this runbook is the owner's permission for
exactly the whole-file copy, the read-only mount, the marker file and the ownership change it lists in steps 3, 6 and
7, and nothing more.

Every command below was run end to end on a copy of a clinic with fake data (old app running, then cut over, then
checked, then rolled back) before this runbook was published.

## What changes and what stays

The old app (Node) keeps its data in one SQLite file, `/opt/clinic-data/data/clinic.db`. The new app (Django) keeps
it in MySQL, in the Docker volume `clinic_mysql_data`. Moving a clinic means copying that file's contents into MySQL
once, with the tool `backend/tools/migrate_sqlite.py` that ships inside the new backend image. After the cutover the
new app never reads `clinic.db` again.

These carry over untouched. They stay where they are, and the new app uses them as they are:

- `/opt/clinic-data/data/patients/` (patient files),
- `/opt/clinic-data/data/sms.key` (without it the clinic's SMS key cannot be opened),
- `/opt/clinic-data/data/trash/` and the old backups in `/opt/clinic-data/data/backups/`,
- the settings in `/opt/clinic-data/.env` (`DOMAIN`, `DATA_PATH`, `TZ`),
- the HTTPS certificate (Docker volume `clinic_caddy_data`; both apps use the Compose project name `clinic`).

## When to do it

Do the cutover only when **both** are true:

1. The newest release folder is a new-app release:
   `ls "$new/backend/tools/migrate_sqlite.py" "$new/deploy/docker-compose.yml" "$new/deploy/deploy.sh"` lists all
   three. (`new` is set under "Steps".)
2. The owner has told you, for this server, to do the cutover now.

Otherwise do nothing about it. An ordinary update of the old app never needs this file. The new release's
`deploy/deploy.sh` refuses to start on a server that still has `data/clinic.db` and has not been cut over, so an
ordinary update cannot start the new app with an empty database by mistake.

## The rules

1. **One server, one clinic at a time.** Do the next server only after the owner says this one works.
2. **A quiet evening, with the owner reachable.** Expect 15 to 30 minutes when nobody can use the app. Tell the
   owner when it starts and when it ends.
3. **Memory and disk.** Check `free -m` before the evening. Below 4 GB total: `needs input:` (the owner decided 2 GB
   servers move to 4 GB first). Free disk must be at least 3 times the size of `/opt/clinic-data/data`
   (`sudo du -sh /opt/clinic-data/data`, `df -h /opt`), plus 2 GB for the new images.
4. **Back up first, then stop the old app before copying.** Nobody may save anything while the data is copied.
5. **Never fix data by hand.** Never open `clinic.db` or MySQL with a query tool. If the migration tool reports a
   problem or a difference, stop and roll back. Report the tool's summary lines (table names, counts, error
   numbers), never row contents. The tool itself never prints row contents.
6. **Never print secrets.** The new app adds `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD` and `DJANGO_SECRET_KEY` to
   `/opt/clinic-data/.env`. Check them with `grep -c` or `grep -q`, never `cat` or `grep` without `-c`/`-q`.
7. **Never `docker compose down -v`** and never `docker volume rm`. The `-v` deletes the MySQL volume (the clinic's
   whole database after the cutover) and the certificate volume.
8. **Do not delete the old app.** Keep the old release folder, the old `clinic.db` and the pre-cutover copy for
   **14 days**. Delete them only after the owner says the clinic has worked normally for 14 days, and only with the
   owner's yes.
9. **The owner checks before the evening ends** (step 9 below). Without the owner's "works", the cutover is not
   finished.
10. **Rollback is always possible within 14 days.** After the first working day, anything entered in the new app is
    lost by a rollback, so from then on a rollback needs the owner's yes.

## Steps

Set these in your shell first (the old `/opt/clinic-data/dc` still points at the old release until step 8):

```
git -C /opt/clinic pull --ff-only
new=$(ls -d /opt/clinic/20*_*/ | sort | tail -1); new=${new%/}; echo "$new"
ndc() { docker compose --env-file /opt/clinic-data/.env --env-file "$new/deploy/images.lock" -f "$new/deploy/docker-compose.yml" "$@"; }
bash "$new/deploy/check-server.sh"   # changes nothing; the WARN about clinic.db is expected here
```

1. **Before the evening.** Check rule 3 and "When to do it". Save which release runs now, because the new deploy
   overwrites `current-release`: `cp /opt/clinic-data/current-release /opt/clinic-data/pre-cutover-release`.
   Ask the owner to print today's daily finance report «گزارش روزانه» on the old app; they compare it in step 9.
   Add the new app's secrets (each only if it is missing, never printed; the old app ignores them), then put the
   new release's finished images on the server while the old app still runs, so the evening is shorter (nothing is
   built; see "Images" in `docs/DEPLOY-AGENT.md`):
   ```
   e=/opt/clinic-data/.env
   for k in MYSQL_PASSWORD MYSQL_ROOT_PASSWORD DJANGO_SECRET_KEY; do
     grep -q "^$k=" "$e" || echo "$k=$(openssl rand -hex 32)" >> "$e"
   done
   chmod 600 "$e"
   bash "$new/deploy/fetch-images.sh"     # must end with "OK: images ... are on this server"
   ```
2. **Backup while the old app runs.** `/opt/clinic-data/dc exec -T app node scripts/backup.js`, then
   `sudo ls -l /opt/clinic-data/data/backups` shows a file from today.
3. **Stop the old app.** `/opt/clinic-data/dc stop -t 60 app`. A clean stop writes every saved change into
   `clinic.db` and removes `clinic.db-wal`. Check: `sudo ls -l /opt/clinic-data/data/ | grep clinic.db`. If a
   `clinic.db-wal` larger than 0 bytes is still there, start the old app (`/opt/clinic-data/dc start app`), wait
   a minute, stop it again the same way; if it is still there, `needs input:` and do not go on. Never delete a
   `clinic.db-wal` file by hand: it can hold saved changes. Then copy whole files, never open them:
   ```
   d=/opt/clinic-data/pre-cutover-$(date +%F); sudo mkdir -m 700 "$d"; sudo cp -a /opt/clinic-data/data "$d/"
   sudo ls -l "$d/data/clinic.db"
   ```
   The copy keeps owners and modes. From here on the tool reads only this copy, and the rollback restores it.
4. **Check the secrets** from step 1, without printing them:
   `grep -cE '^(MYSQL_PASSWORD|MYSQL_ROOT_PASSWORD|DJANGO_SECRET_KEY)=' /opt/clinic-data/.env` must print `3`.
   If not, run the loop from step 1 again.
5. **Start MySQL and create the empty schema.**
   ```
   bash "$new/deploy/fetch-images.sh"   # instant if step 1 already did it
   ndc up -d mysql
   ndc ps mysql             # repeat until it shows "healthy" (about 30 s on first start)
   ndc run --rm backend python manage.py migrate
   ```
   `migrate` must end without an error. It creates the tables; it does not copy data.
6. **Migrate the data** with the tool, in three runs. Each run mounts the copy from step 3 read-only. The old
   files belong to uid 1000 with mode 700, so this one-off container runs as root (`-u 0`) with the one capability
   that lets root read files it does not own (`DAC_READ_SEARCH`: the backend service drops every capability, so
   plain root is refused on a Linux server). Its scratch folder (`DATA_DIR`) stays inside the container, so nothing
   it creates lands in the clinic's data:
   ```
   mig() { ndc run --rm -u 0 --cap-add DAC_READ_SEARCH -e DATA_DIR=/tmp/migrate-data -v "$d/data:/migrate:ro" \
     backend python tools/migrate_sqlite.py --sqlite /migrate/clinic.db --patients-dir /migrate/patients "$@"; }
   mig --verify-only    # checks everything and rehearses the copy, then rolls it back; writes nothing
   mig                  # the copy: one transaction, all or nothing
   mig --check          # compares MySQL with the copy: rows, money totals, bills, folders
   ```
   - `--verify-only` must exit 0 and print `0 problem(s)` and `verified: the whole copy holds inside one
     transaction, which was rolled back`. Warnings are allowed; put their count in your report.
   - The copy must exit 0 and print `written: users=..., patients=..., ...` with the row counts.
   - `--check` must exit 0 and print `differences: 0`.
   - `target has N unapplied migration(s)`: step 5 did not finish; run its `migrate` again, then repeat step 6.
   - `refused: the target is not empty`: this MySQL already holds data. Stop and write `needs input:`. Use
     `--replace` only when the owner says so, because it clears the MySQL tables first.
   - `refused: clinic.db-wal is not empty`: the old app did not stop cleanly. Go back to step 3 (start, stop,
     copy again into a new folder `d`).
   - Any other refusal, problem or difference: rule 5, roll back.

   When `--check` passed, record it. The new `deploy.sh` starts only on a server that has this marker:
   ```
   date -u +%FT%TZ > /opt/clinic-data/cutover-done
   ```
7. **Give the data folder to the new app.** The new backend runs as a different user (uid 10001; the old app
   used 1000), and it writes uploads, backups and the heartbeat there:
   ```
   uid=$(ndc run --rm --no-deps backend id -u); echo "$uid"      # prints 10001
   sudo chown -R "$uid:$uid" /opt/clinic-data/data
   ```
   This changes only who owns the files, never their contents.
8. **Start the new app.** `bash "$new/deploy/deploy.sh"`. It writes one backup with the new release (a MySQL dump,
   `backup written: klerk-<date>.sql.gz`) and must end with `OK: https://<domain>/health answers; running release
   ...`. Then `/opt/clinic-data/dc ps` (now pointing at the new release) shows `mysql`, `backend` and `worker`
   healthy and `caddy` running. If it stops with `FAILED:`, read the line: it names the cause (a missing setting,
   the data folder owner, a service that is not healthy). Fix only settings and ownership; anything else, roll back.
9. **The owner checks, with you on the line:**
   - the site opens with a valid HTTPS certificate;
   - the owner signs in with their **old password** (old passwords are kept and upgraded at sign-in);
   - a patient the owner picks opens, with their documents;
   - today's visits show;
   - the finance overview totals match the report printed in step 1;
   - the dashboard layout editor «چیدمان» works;
   - the worker runs and sent **no SMS** that was not due:
     `/opt/clinic-data/dc logs --tail 50 worker` shows `worker started` and `sms tick sent=...` lines.
   Anything wrong: roll back (below), unless the owner decides otherwise.
10. **After the evening.** Watch for 14 days: errors in `dc logs --tail 100 backend`, the nightly backup at 03:00
    (`sudo ls -l /opt/clinic-data/data/backups` shows a new `klerk-<date>.sql.gz` each day; the newest 14 are
    kept), next-day SMS reminders. Then rule 8.

## Report to the owner

One message: the release folder used, the times the app went down and came back, the summary lines of the three
tool runs (problem and warning counts, `written:` counts, `differences: 0`), the `OK:` line of `deploy.sh`, and the
owner's checks. No row contents, no secrets.

## Rollback

1. Stop the new stack: `ndc down` (never `-v`, rule 7: the MySQL volume stays, so a later retry can compare).
2. Take the marker away, so the new `deploy.sh` does not start on the old data:
   `mv /opt/clinic-data/cutover-done "/opt/clinic-data/cutover-rolled-back-$(date +%F-%H%M)"`.
3. Put the pre-cutover copy back. It keeps the old owner (uid 1000):
   ```
   sudo mv /opt/clinic-data/data "/opt/clinic-data/data.new-$(date +%F-%H%M)"
   sudo cp -a "$d/data" /opt/clinic-data/
   ```
4. Start the old release with its own script:
   `bash "$(cat /opt/clinic-data/pre-cutover-release)/scripts/deploy.sh"`.
5. Check `/health` and that the owner can sign in. Tell the owner what failed, with the tool's summary lines
   (counts and table names only). A second attempt later finds MySQL not empty (step 6 refuses): that needs the
   owner's yes for `--replace`.

## After the cutover: updates

The new app is updated like the old one, with its own script. It backs up before it changes anything:

```
git -C /opt/clinic pull --ff-only
new=$(ls -d /opt/clinic/20*_*/ | sort | tail -1); new=${new%/}
bash "$new/deploy/deploy.sh"
```

Useful commands (all through the wrapper `deploy.sh` writes): `/opt/clinic-data/dc ps`,
`dc logs --tail 50 backend`, `dc logs --tail 50 worker`, and a backup now:
`/opt/clinic-data/dc exec -T backend python manage.py backup`.

## Restoring a MySQL backup (only with the owner's yes)

A restore replaces the whole database with the state of one backup; everything entered after it is lost. Ask the
owner which day, then:

```
b=/opt/clinic-data/data/backups/klerk-YYYY-MM-DD.sql.gz      # the day the owner chose
/opt/clinic-data/dc exec -T backend python manage.py backup  # a backup of the current state first
/opt/clinic-data/dc stop backend worker
sudo gunzip -c "$b" | /opt/clinic-data/dc exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -u root klerk' 2>&1 | grep -oE '^ERROR [0-9]+'
echo "restore exit ${PIPESTATUS[1]}"                          # must print 0
/opt/clinic-data/dc start backend worker
```

The `grep` keeps only an error number: when a statement fails, the `mysql` client prints that statement, which can
contain patient data. Never run the restore without that `grep`. A non-zero exit: restore the backup made in the
second line the same way, and write `needs input:` with the error number.
