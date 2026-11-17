# Deployment runbook for the agent on the production server

This file is for the Claude Code session that runs **on the production VPS**. It installs, updates and repairs the
live site from the public GitHub repository `MMACABRE/KLERK` (branch `main`). This is the new app: Django, MySQL and
a Vue front end, in Docker behind Caddy. The site holds real patient records, so read the rules first.

A server that still runs the old app (Node and SQLite: `/opt/clinic-data/data/clinic.db` exists and
`/opt/clinic-data/dc ps` shows a service `app`) is moved only by `docs/DEPLOY-AGENT-CUTOVER.md`, and only when the
owner has said so for that server. Never run this release's `deploy.sh` on such a server before the cutover: it
would start an empty database.

## How the server is laid out

| Place | Holds | Who writes to it |
|---|---|---|
| `/opt/clinic` | A clone of the public repository: **code only**. Every release is a folder named with a date and time (for example `2026-11-20_14-30`) | Nobody. You only run `git pull --ff-only` here |
| `/opt/clinic-data` | `.env` (settings and the three secrets), `data/` (patient files, backups, trash, `sms.key`), and two files written by `deploy/deploy.sh`: `current-release` and `dc` | The app, and `deploy/deploy.sh` |
| Docker volume `clinic_mysql_data` | The MySQL database | MySQL |
| Docker volume `clinic_caddy_data` | HTTPS certificates | Caddy |

`/opt/clinic-data/dc` runs `docker compose` for the release that is deployed now. Use it for every routine command
(`dc ps`, `dc logs --tail 50 backend`, `dc restart`). It exists after the first successful deploy. The newest
release folder is:

```
newest=$(ls -d /opt/clinic/20*_*/ | sort | tail -1); newest=${newest%/}
```

The services are `mysql`, `backend` (the app, gunicorn), `worker` (SMS every minute, the 03:00 backup, temp file
cleanup) and `caddy` (HTTPS, the only service that listens on the internet).

## Rules

1. **Never touch patient data.** Do not read, print, copy, move or delete anything under
   `/opt/clinic-data/data/patients/` or `data/trash/`. Never open the database with `mysql`, a query or any tool
   that shows rows. The same goes for `data/sms.key` (it unlocks the clinic's SMS key): never print it, never delete
   or replace it; it must survive every update and restore. Backups move whole files only, through the app's `backup`
   command; a restore follows "Restore and rollback" below.
2. **The repository is read-only for you.** Only `git pull --ff-only`. Never commit, push, edit, create or delete
   anything inside `/opt/clinic`. Code changes are made on the owner's computer and published by the owner.
3. **Never print secrets.** `/opt/clinic-data/.env` holds `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD` and
   `DJANGO_SECRET_KEY`. Check them with `grep -c` or `grep -q` only. Never change them on a running server: the
   database and every session depend on them.
4. **Back up before every change.** `deploy/deploy.sh` does this for you.
5. **Do not run destructive commands** without the owner's yes: `docker compose down -v` (deletes the database
   volume), `docker volume rm`, `docker system prune -a`, `rm -rf /opt/clinic-data/data`, `git reset --hard`,
   `git clean`, a database restore, anything with `--force`. `/opt/clinic-data/data` and the volumes `clinic_mysql_data` and
   `clinic_caddy_data` must survive every operation.
6. **Do not change code or config to make a check pass.** If a step fails, report the exact error. Fixing the app
   is the developer's job; fixing the server (firewall, Docker, DNS, permissions) is yours.
7. When a step needs the owner, write `needs input:` and say exactly what they must do. Do not guess a domain, a
   password or an account name.

## What only the owner can supply

| Item | Why you cannot do it |
|---|---|
| The domain name, and its DNS **A record** pointing at this server's public IP | It lives at the registrar |
| The administrator username and password | The owner chooses and keeps them |
| The clinic's name, such as `KLERK \| کلرک` | It is the site's name and the letterhead of every printed form |
| A published release (a dated folder in the repository) | The owner decides when to publish. If `ls -d /opt/clinic/20*_*/` finds nothing, write `needs input:` |
| Off-server backup destination | The owner decides where copies go (questions in "Backups off the server") |

## First install

Run as a sudo-capable user. Stop at the first failure.

1. **Check the machine.** `lsb_release -d` (Ubuntu 24.04 expected), `nproc`, `free -h` (**at least 4 GB RAM**:
   MySQL needs it; the owner decided 2 GB servers move to 4 GB first), `df -h /` (at least 40 GB),
   `curl -s https://api.ipify.org` (public IP).
2. **Check DNS.** `getent hosts <domain>` must print this server's public IP. If not: `needs input:` ask the owner to
   fix the A record. Also confirm there is **no wrong AAAA record** (`getent ahostsv6 <domain>`).
3. **Update the OS.** `sudo apt update && sudo apt upgrade -y`. Reboot only if the kernel was updated and tell the
   owner first.
4. **Firewall.** Allow SSH *first*, so you do not lock out the owner:
   ```
   sudo ufw allow 22/tcp
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   sudo ufw allow 443/udp
   sudo ufw --force enable
   sudo ufw status
   ```
   If SSH runs on another port, allow that port instead. Recommended: `sudo apt install -y unattended-upgrades fail2ban`.
5. **Docker.** If `docker compose version` fails: `curl -fsSL https://get.docker.com | sudo sh`, then
   `sudo usermod -aG docker "$USER"` and start a new shell. Verify `docker --version` and `docker compose version`.
6. **Code (read-only clone).** `sudo mkdir -p /opt/clinic && sudo chown "$USER": /opt/clinic && git clone
   https://github.com/MMACABRE/KLERK.git /opt/clinic`, then set `newest` as above. If it is empty: `needs input:`.
7. **Data folder and settings.** These live outside the code:
   ```
   sudo mkdir -p /opt/clinic-data/data && sudo chown "$USER": /opt/clinic-data && sudo chown 10001:10001 /opt/clinic-data/data
   printf 'DOMAIN=%s\nDATA_PATH=/opt/clinic-data/data\nTZ=Asia/Tehran\n' '<domain>' > /opt/clinic-data/.env
   chmod 600 /opt/clinic-data/.env
   ```
   `DOMAIN` is the name only (no `https://`, no slash); change `TZ` only if the owner says so. Never copy
   `deploy/.env.example` here: it is the developer's template, and its `replace-me` values are refused by
   `deploy.sh`. Check: `grep -E '^(DOMAIN|DATA_PATH|TZ)=' /opt/clinic-data/.env`. The app runs as
   uid 10001; without the `chown` it cannot write.
8. **Check the server.** `bash "$newest/deploy/check-server.sh"`. It changes nothing and prints one `OK`, `WARN` or
   `FAIL` line per check (Docker, settings, data folder owner, disk, ports 80/443, DNS, where the images can come
   from). Fix every `FAIL` that is yours (rule 6); report the others as `needs input:`. Put its output in your report.
9. **Start.** `bash "$newest/deploy/deploy.sh"`. It creates the three secrets in `.env` (random, never shown), puts
   the release's finished images on the server (`deploy/fetch-images.sh`, see "Images" below; nothing is built
   here), starts MySQL, creates the tables, seeds the default payment methods and ends with
   `OK: https://<domain>/health answers`. If the certificate is not ready yet, the HTTPS check fails while the app
   is healthy: wait a minute, read `/opt/clinic-data/dc logs --tail 50 caddy` (or, before the first success,
   `docker logs --tail 50 clinic-caddy-1`), run the script again.
10. **Check the services.** `/opt/clinic-data/dc ps`: `mysql` and `backend` are `healthy`, `worker` and `caddy` are
   `running`.
11. **Create the first administrator.** `needs input:` ask the owner for the username and a password of at least 10
    characters. If the owner asks you to generate one, make a long random passphrase, show it **once**, and tell them
    to store it in their password manager. Pass it through the environment only:
    ```
    read -rsp 'Password: ' P; echo
    /opt/clinic-data/dc exec -T -e NEW_USER_PASSWORD="$P" backend python manage.py create_user <username> owner "مدیر سیستم"; unset P
    ```
    Expect `Created owner "<username>"`. The owner always has every permission and cannot be restricted or deleted
    from the web pages.
12. **Clinic name.** The default is `KLERK | کلرک`. Change it only when the owner asks; repeat the name back, wait
    for a yes, then: `/opt/clinic-data/dc exec -T backend python manage.py set_clinic_name "<name>"`. Without a name
    the command prints the current one.
13. **Public check.** Run the acceptance tests below.

## Acceptance tests

Record each result in your report to the owner.

| # | Check | Expect |
|---|---|---|
| 1 | `curl -sI http://<domain>` | `308` redirect to `https://` |
| 2 | `curl -sI https://<domain>/login` | `200`, headers `strict-transport-security` and `content-security-policy`, no `server` |
| 3 | `curl -s -m 5 -o /dev/null -w '%{http_code}' http://<public-ip>:8000` | Fails (`000`): the app port is closed |
| 4 | `curl -s https://<domain>/health` | `ok` |
| 5 | `/opt/clinic-data/dc exec -T backend python manage.py backup` | `backup written: klerk-<today>.sql.gz` |
| 6 | `sudo ufw status` | Only SSH, 80, 443 (tcp), 443 (udp) allowed |
| 7 | `/opt/clinic-data/dc ps` after `sudo reboot` (ask the owner first) | All four services come back by themselves |
| 8 | Next morning: `sudo ls -l /opt/clinic-data/data/backups` | A file `klerk-<today>.sql.gz` written at 03:00 |

Ask the owner to do one pass in the browser: sign in, create a **test** patient, upload a small PDF, download it,
then delete the test patient. Do not do this with a real patient.

## Update to a new release

When the owner says a new release is published:

```
git -C /opt/clinic pull --ff-only
newest=$(ls -d /opt/clinic/20*_*/ | sort | tail -1); newest=${newest%/}; echo "$newest"
bash "$newest/deploy/check-server.sh"
bash "$newest/deploy/deploy.sh"
```

The script first puts the new release's images on the server (if that fails, nothing is changed and the old
release keeps running), then backs up the database, starts the new release with the **same** data folder and database
volume, applies database changes at start-up, waits for the backend to be healthy and checks
`https://<domain>/health`. Earlier release folders stay on disk. On failure it prints the command that restarts the
previous release. If `git pull --ff-only` refuses, do not force it: report `git status` to the owner.

Afterwards: `/opt/clinic-data/dc logs --tail 50 backend` and `... worker` show no errors.

### Migrations

A release's database changes only add: tables, columns, indexes. A rename or drop ships in a later release, once no
deployed release reads the old shape, so the previous release can still run on the new database during a rollback.
Each `RemoveField`, `DeleteModel`, `RenameField` or `RenameModel` carries a `# contract: <release>` comment naming
the release that stopped using the old shape; `backend/tests/test_migration_rule.py` fails without it.

## Images

Nothing is built on the server: no Docker Hub, PyPI, npm or Debian mirror is needed. The developer builds three
finished images and the release names them in `deploy/images.lock` (backend and worker share one image; web is
Caddy with the app; mysql is a copy of MySQL 8.4). `deploy/fetch-images.sh` (run by `deploy.sh`) gets them in this
order and stops at the first that works:

1. already on the server;
2. the offline file `/opt/clinic-data/images/<IMAGES_TAR>` (name in `images.lock`), if someone copied it there;
3. `ghcr.io/mmacabre/...`, pulled by digest (public: no login);
4. the same offline file, downloaded from the GitHub Release `images-<IMAGES_TAG>` of `MMACABRE/KLERK`.

The offline file is loaded only when its SHA-256 matches `images.lock`; pulls are by digest. If all four fail the
script prints `needs input:` with the file name, URL and SHA-256: the owner then copies that one file to
`/opt/clinic-data/images/` by any way (scp, USB) and you run `deploy.sh` again. Never build an image on the server,
never edit `images.lock` or the compose file, never pull an image by tag from anywhere else.

## Routine care

| Task | Command |
|---|---|
| Status | `/opt/clinic-data/dc ps` |
| App logs | `/opt/clinic-data/dc logs --tail 100 backend` |
| Worker logs (SMS, backups) | `/opt/clinic-data/dc logs --tail 100 worker` |
| Proxy and certificate logs | `/opt/clinic-data/dc logs --tail 100 caddy` |
| Restart | `/opt/clinic-data/dc restart` |
| Backup now | `/opt/clinic-data/dc exec -T backend python manage.py backup` |
| List backups | `sudo ls -l /opt/clinic-data/data/backups` (names and sizes only) |
| Disk | `df -h /`, `du -sh /opt/clinic-data/data/*` and `docker system df` (sizes only) |
| OS security updates | `sudo apt update && sudo apt upgrade -y`, reboot with the owner's yes |

The nightly backup keeps 14 database dumps in `/opt/clinic-data/data/backups/` **on this server only**; remind the
owner that a copy must also leave the server.

## Backups off the server

The database backup and the patient files together are the clinic's data: copy the whole `/opt/clinic-data/data`
folder (it holds both) to another place at least weekly.

- From the owner's computer: `scp -r <user>@<server-ip>:/opt/clinic-data/data <destination>`. The folder belongs to
  uid 10001 with mode 700, so an ordinary account is blocked; this is intended. If permissions block it, run
  `sudo chown -R <user> /opt/clinic-data/data`, copy, then give it back with
  `sudo chown -R 10001:10001 /opt/clinic-data/data`.
- An admin downloads the full ZIP from «ورود و خروج داده» in the app.

### Automatic off-server copy: ask the owner first

Nothing leaves the server until the owner has answered these questions. Ask them in one message, word for word,
and wait. Do not choose a tool, open an account or copy data before the answers.

1. "Where may a copy of this clinic's backups go: (a) a second server you rent, (b) a disk or computer at the
   clinic, or (c) cloud storage you already pay for (name it)?"
2. "May the copy include patient files (`data/patients`, can be several GB), or only the database dumps
   (`data/backups`, a few MB each)?"
3. "Should the copy be encrypted with a password only you hold? If you lose that password, the copy cannot be read
   by anyone, including you."
4. "How often: every night after the 03:00 backup (recommended), or weekly?"
5. "How many copies to keep at the destination (recommended: 14 daily and 8 weekly)?"
6. For (a): "The address, SSH port and a user name on that server, and may I put a key there that can only write
   into one backup folder?" For (b): "Which computer, its operating system, and is it on and online at night?"
   For (c): "The account's access key; send it to me privately, never in a shared chat."

Record the answers (without any password or key) in your report to the owner.

### Automatic off-server copy: setting it up after the answers

Rules that hold for every answer:
- The copy must always include `data/backups/` **and** `data/sms.key` (without that key the clinic's stored SMS
  provider key cannot be read after a restore). Include `data/patients/` only if the owner said yes to question 2.
  Never copy `deploy/.env` files to a place the owner did not name.
- Run the copy from the clinic server's root cron at 03:30 (after the 03:00 dump), as root, because
  `/opt/clinic-data/data` belongs to uid 10001 with mode 700. Never `chmod` or `chown` the data folder for it.
- Install tools on the host only (`apt`), never inside the app's containers or images.
- After each good run, write the time: `date -u +%FT%TZ > /opt/clinic-data/data/offsite.ok` (the app will read this
  file for its owner warning; until then it is for you and the owner). A failed run must exit non-zero and leave
  `offsite.ok` untouched, so its age shows the problem.
- Prove the copy once: restore it on a throwaway folder (or the destination), check the newest dump unpacks with
  `gunzip -t`, and report the sizes and dates only. Never open a dump's contents.

By answer:
- **Encrypted (question 3 = yes), any destination:** `restic` (`apt install restic`). Repository on the
  destination (`sftp:` for a second server, a mounted disk path, or the cloud service's backend). The owner types
  the password into `/root/.config/klerk-restic.pass` (mode 600) himself or sends it privately; you never repeat it.
  Nightly: `restic backup /opt/clinic-data/data/backups /opt/clinic-data/data/sms.key [/opt/clinic-data/data/patients]`
  then `restic forget --keep-daily 14 --keep-weekly 8 --prune`. Tell the owner plainly that a lost password means
  a lost copy.
- **Not encrypted, second server:** a dedicated SSH key in `/root/.ssh/klerk_offsite` whose `authorized_keys` line
  on the destination is limited (`restrict,command="rrsync -wo /srv/klerk/<clinic>"`), then
  `rsync -a --delete-after` of the same paths. Daily dumps rotate on the server (14 kept), so the destination keeps
  the same 14.
- **Clinic computer:** the copy is pulled by that computer, not pushed (the server must not reach into the clinic):
  give the owner a scheduled task for that computer (Windows Task Scheduler with `scp`, or `rsync` on Linux/macOS)
  that runs at 04:00 with a read-only SSH key, and a server-side `offsite.ok` cannot be written; instead ask the
  owner to check the destination folder's newest date weekly.
- **Cloud storage:** `rclone` with the owner's key, `rclone copy` of the same paths; encrypt with `restic` (above)
  if question 3 was yes.

Report: destination type, what is copied, encrypted yes/no, schedule, retention, the first run's size and duration,
and the result of the restore proof.

## Restore and rollback

- **Database from a backup** (only when the owner asks, and only after they name the day):
  ```
  b=/opt/clinic-data/data/backups/klerk-YYYY-MM-DD.sql.gz      # the day the owner chose
  /opt/clinic-data/dc exec -T backend python manage.py backup --before-restore  # the current state first
  /opt/clinic-data/dc stop backend worker
  sudo gunzip -c "$b" | /opt/clinic-data/dc exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -u root klerk' 2>&1 | grep -oE '^ERROR [0-9]+'
  echo "restore exit ${PIPESTATUS[1]}"                          # must print 0
  /opt/clinic-data/dc start backend worker
  ```
  The restore replaces every table with the backup's copy; anything entered after that backup is lost. The `grep`
  keeps only an error number: a failing statement is printed by the `mysql` client and can contain patient data.
  Never run the restore without it. A non-zero exit: restore the backup made in the second line the same way and
  report the error number. The safety copy has its own name (`klerk-<date>-<time>-before-restore.sql.gz`), so it
  never replaces the dump being restored. A release built before 2026-11-14 has no `--before-restore`: there, run
  `sudo cp "$b" /tmp/restore.sql.gz` and `b=/tmp/restore.sql.gz` first, then plain `manage.py backup`.
- **Previous release:** `bash <older-release-folder>/deploy/deploy.sh`. If a database change already ran in the
  newer release, restore the backup made by the failed update first (the line above). A release folder without
  `deploy/images.lock` (`2026-11-06_01-26` and older) builds its images on the server, which needs Docker Hub,
  PyPI and npm; if that fails, `needs input:`.
- Patient files are not inside the database backup. After restoring an old database, newer files appear as
  "unclassified" until someone classifies them. That is expected.

## Report format

End every session with a short report to the owner: what you did, each acceptance result (pass or fail with the
exact error), anything marked `needs input:`, and the release now deployed (`cat /opt/clinic-data/current-release`).
Never include patient data or secrets.

## Known state of the project

The production stack passed a local test on the developer's computer (build, HTTPS with a self-signed certificate,
headers, sign-in, lockout, backup, and a restore after deleting the database volume). A Let's Encrypt certificate,
the reboot test and the 03:00 backup have **not** yet been proven on a real server. The first install is that proof,
so report faithfully, including every error.
