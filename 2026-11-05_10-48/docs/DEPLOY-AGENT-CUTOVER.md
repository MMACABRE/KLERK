# Cutover: move one clinic from the old app (SQLite) to the new app (MySQL)

For the server agent. Read all of it before you start. It adds to the rules in `docs/DEPLOY-AGENT.md`; those rules
still apply (never read or print patient data, the repository is read-only for you, ask before any destructive
command). Once the owner has said "cut over this server", this runbook is the owner's permission for exactly the
whole-file copy, the read-only mount and the ownership change it lists in steps 3, 6 and 7, and nothing more.

## When to do it

The old app keeps its data in one SQLite file, `/opt/clinic-data/data/clinic.db`. The new app (Django, MySQL) keeps
it in a MySQL database. Moving a clinic means copying that file's contents into MySQL once, with the tool
`backend/tools/migrate_sqlite.py` that ships with the new app. Patient files, the SMS key and the settings stay
where they are.

Do the cutover only when **both** are true:

1. The newest release folder is a new-app release: `ls "$new/backend/tools/migrate_sqlite.py" "$new/docker-compose.yml"`
   both exist and `grep -q '^  mysql:' "$new/docker-compose.yml"` succeeds. (`new` is defined under "Steps".)
2. The owner has told you, for this server, to do the cutover now.

Otherwise do nothing about it. An ordinary update of the old app never needs this file. If the new release's own
`docs/DEPLOY-AGENT.md` gives different commands for a step below, follow the release and tell the owner which step
changed.

## The rules

1. **One server, one clinic at a time.** Do the next server only after the owner says this one works.
2. **A quiet evening, with the owner reachable.** Expect 15 to 30 minutes when nobody can use the app. Tell the
   owner when it starts and when it ends.
3. **Memory and disk.** Check `free -m` before the evening. Below 4 GB total: `needs input:` (the owner decided 2 GB
   servers move to 4 GB first). Free disk must be at least 3 times the size of `/opt/clinic-data/data`
   (`du -sh /opt/clinic-data/data`, `df -h /opt`).
4. **Back up first, then stop the old app before copying.** Nobody may save anything while the data is copied.
5. **Never fix data by hand.** Never open `clinic.db` or MySQL with a query tool. If the migration tool reports a
   problem or a difference, stop and roll back. Report the tool's summary lines (table names, counts, error
   numbers), never row contents. The tool itself never prints row contents.
6. **These carry over untouched.** They stay where they are, and the new app uses them as they are:
   - `/opt/clinic-data/data/patients/` (patient files),
   - `/opt/clinic-data/data/sms.key` (without it the clinic's SMS key cannot be opened),
   - `/opt/clinic-data/data/trash/`,
   - the settings in `/opt/clinic-data/.env` (`DOMAIN`, `DATA_PATH`, `TZ`).
7. **Never print secrets.** The new app adds `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD` and `DJANGO_SECRET_KEY` to
   `/opt/clinic-data/.env`. Check them with `grep -c` or `grep -q`, never `cat` or `grep` without `-c`/`-q`.
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
ndc() { docker compose --env-file /opt/clinic-data/.env -f "$new/docker-compose.yml" "$@"; }
```

1. **Before the evening.** Check rule 3 and "When to do it". Save which release runs now, because the new deploy
   overwrites `current-release`: `cp /opt/clinic-data/current-release /opt/clinic-data/pre-cutover-release`.
   Ask the owner to print today's daily finance report «گزارش روزانه» on the old app; they compare it in step 9.
2. **Backup while the old app runs.** `/opt/clinic-data/dc exec -T app node scripts/backup.js`, then
   `ls -l /opt/clinic-data/data/backups` shows a file from today.
3. **Stop the old app.** `/opt/clinic-data/dc stop -t 60 app`. A clean stop writes every saved change into
   `clinic.db` and removes `clinic.db-wal`. Check: `sudo ls -l /opt/clinic-data/data/ | grep clinic.db`. If a
   `clinic.db-wal` larger than 0 bytes is still there, start the old app (`/opt/clinic-data/dc start app`), wait
   a minute, stop it again the same way; if it is still there, `needs input:` and do not go on. Then copy whole
   files, never open them:
   ```
   d=/opt/clinic-data/pre-cutover-$(date +%F); sudo mkdir -m 700 "$d"; sudo cp -a /opt/clinic-data/data "$d/"
   sudo ls -l "$d/data/clinic.db"
   ```
   The copy keeps owners and modes. From here on the tool reads only this copy, and the rollback restores it.
4. **Secrets for the new app.** Add each one only if it is missing, without printing it:
   ```
   e=/opt/clinic-data/.env
   for k in MYSQL_PASSWORD MYSQL_ROOT_PASSWORD DJANGO_SECRET_KEY; do
     grep -q "^$k=" "$e" || echo "$k=$(openssl rand -hex 32)" >> "$e"
   done
   chmod 600 "$e"; grep -cE '^(MYSQL_PASSWORD|MYSQL_ROOT_PASSWORD|DJANGO_SECRET_KEY)=' "$e"   # must print 3
   ```
5. **Build, then start MySQL with an empty schema.**
   ```
   ndc build
   ndc up -d mysql
   ndc ps mysql            # repeat until it shows "healthy" (about 30 s on first start)
   ndc run --rm -e DJANGO_SETTINGS_MODULE=klerk.settings.prod backend python manage.py migrate
   ```
   `migrate` must end without an error. It creates the tables; it does not copy data.
6. **Migrate the data** with the tool, in three runs. Each run mounts the copy from step 3 read-only. The old
   files belong to uid 1000 with mode 700, so this one-off container runs as root (`-u 0`) to read them; its
   scratch folder (`DATA_DIR`) stays inside the container, so nothing it creates lands in the clinic's data:
   ```
   mig() { ndc run --rm -u 0 -e DJANGO_SETTINGS_MODULE=klerk.settings.prod -e DATA_DIR=/tmp/migrate-data \
     -v "$d/data:/migrate:ro" \
     backend python tools/migrate_sqlite.py --sqlite /migrate/clinic.db --patients-dir /migrate/patients "$@"; }
   mig --verify-only    # checks everything and rehearses the copy, then rolls it back; writes nothing
   mig                  # the copy: one transaction, all or nothing
   mig --check          # compares MySQL with the copy: rows, money totals, bills, folders
   ```
   - `--verify-only` must exit 0 and print `0 problem(s)` and `verified: ...`. Warnings are allowed; put their
     count in your report.
   - The copy must exit 0 and print `written: ...` with the row counts.
   - `--check` must exit 0 with no difference lines.
   - `target has N unapplied migration(s)`: step 5 did not finish; run its `migrate` again, then repeat step 6.
   - `refused: the target is not empty`: this MySQL already holds data. Stop and write `needs input:`. Use
     `--replace` only when the owner says so, because it clears the MySQL tables first.
   - Any other refusal, problem or difference: rule 5, roll back.
   Never delete a `clinic.db-wal` file by hand: it can hold saved changes (see step 3).
7. **Give the data folder to the new app.** The new backend runs as a different user (uid 10001; the old app
   used 1000), and it writes uploads and the SMS key file there:
   ```
   uid=$(ndc run --rm --no-deps backend id -u); echo "$uid"
   sudo chown -R "$uid:$uid" /opt/clinic-data/data
   ```
   This changes only who owns the files, never their contents.
8. **Start the new app.** `bash "$new/scripts/deploy.sh"`. It must end with the `/health` check answering `ok`
   over HTTPS. `/opt/clinic-data/dc ps` (now pointing at the new release) shows `backend`, `worker` and `mysql`
   healthy and `caddy` running.
9. **The owner checks, with you on the line:**
   - the site opens with a valid HTTPS certificate;
   - the owner signs in with their **old password** (old passwords are kept and upgraded at sign-in);
   - a patient the owner picks opens, with their documents;
   - today's visits show;
   - the finance overview totals match the report printed in step 1;
   - the dashboard layout editor «چیدمان» works;
   - the worker log shows it is running and sent **no SMS** that was not due
     (`/opt/clinic-data/dc logs --tail 50 worker`).
   Anything wrong: roll back (below), unless the owner decides otherwise.
10. **After the evening.** Watch for 14 days: errors in the logs, the nightly backup at 03:00 (now a MySQL dump plus
    the files), next-day SMS reminders. Then rule 8.

## Report to the owner

One message: the release folder used, the times the app went down and came back, the summary lines of the three
tool runs (problem and warning counts, `written:` counts, the `--check` result), the `/health` answer, and the
owner's checks. No row contents, no secrets.

## Rollback

1. Stop the new stack: `ndc down` (never `-v`: it would delete the MySQL volume, which you may still need).
2. Put the pre-cutover copy back. It keeps the old owner (uid 1000):
   ```
   sudo mv /opt/clinic-data/data "/opt/clinic-data/data.new-$(date +%F-%H%M)"
   sudo cp -a "$d/data" /opt/clinic-data/
   ```
3. Start the old release with its own script:
   `bash "$(cat /opt/clinic-data/pre-cutover-release)/scripts/deploy.sh"`.
4. Check `/health` and that the owner can sign in. Tell the owner what failed, with the tool's summary lines
   (counts and table names only).
