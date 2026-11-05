# Troubleshooting

Run every command on the server, in the data folder: `ssh root@YOUR-IP`, then `cd /opt/clinic-data`. The helper
`./dc` there works like `docker compose` for the version of the site that is running. The code lives separately in
`/opt/clinic` (one dated folder per version) and is never edited.

The site has four parts: `mysql` (the database), `backend` (the app), `worker` (text messages, the nightly backup)
and `caddy` (HTTPS).

## The site does not load
1. Is everything running? `./dc ps`. `mysql` and `backend` must say `healthy`, `worker` and `caddy` `running`.
   - Not running: `./dc up -d`
   - `backend` keeps restarting: `./dc logs --tail 50 backend` and read the last error.
   - `mysql` is not healthy: `./dc logs --tail 50 mysql`. A full disk is the usual reason (see below).
2. Does the domain point at this server? On your own computer: `nslookup clinic-name.com`. The IP must be the
   server's. If not, fix the A record at the registrar and wait.
3. Is the firewall open? `ufw status` must list 80 and 443.
4. Does the app answer inside the server? This prints `ok` (the app port is not reachable from outside by design):
   ```
   ./dc exec backend python -c "import os,urllib.request as u; print(u.urlopen(u.Request('http://127.0.0.1:8000/health', headers={'Host': os.environ['DOMAIN']})).read().decode())"
   ```

## The page opens but says «خطایی در سرور رخ داد» or «ارتباط با سرور برقرار نشد»
The pages load, but the app behind them does not answer. `./dc ps`, then `./dc logs --tail 50 backend`. A restart
often helps: `./dc restart backend`.

## Certificate error or "connection not private"
- Right after the first start, wait 1 to 2 minutes and refresh. The certificate is requested automatically.
- Still wrong: `./dc logs --tail 50 caddy`.
  - "no such host" or "NXDOMAIN": the domain does not point at the server yet.
  - "too many requests" or "rate limited": you restarted many times; wait an hour.
  - "connection refused" on port 80 or 443: the firewall or another program blocks the ports.
- The `DOMAIN=` line in `/opt/clinic-data/.env` must be only the name, for example `clinic-name.com`. After
  changing it: `./dc up -d`.

## The disk is full
1. See what is big: `df -h /`, `du -sh data/*` and `docker system df`.
2. Old backups: they are only 14 files. Old Docker leftovers: `docker system prune -f` (safe: it does not touch
   the data folder or the database volume). Never add `-a` or `--volumes`.
3. Logs are rotated automatically (10 MB x 5 files per service).
4. Patient files are in `data/patients/`. If they are the reason, move to a bigger disk (ask your provider to
   resize the server).

## I forgot the administrator password
- If another administrator exists: they open «مدیریت کاربران» and set a new password for you.
- If you are the only administrator, create a new one and use it to reset the old account:
  ```
  ./dc exec backend python manage.py create_user admin2 admin "مدیر"
  ```

## A user is locked out
After 5 wrong passwords the sign-in is blocked for 15 minutes. Wait 15 minutes and try again. Restarting the app
does not clear the block, because it is stored in the database.

## Restore yesterday's backup
See "Restore a backup" in `SETUP.md`. In short:
```
b=data/backups/klerk-YYYY-MM-DD.sql.gz
./dc exec -T backend python manage.py backup
./dc stop backend worker
gunzip -c "$b" | ./dc exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -u root klerk' 2>&1 | grep -oE '^ERROR [0-9]+'
./dc start backend worker
```
If the restore prints `ERROR` and a number, send that line to the developer.

## The server rebooted
Nothing to do. Every part starts again by itself. Check after two minutes: `./dc ps`. If they are not running:
`./dc up -d`.

## There is no backup from last night
- `ls -l data/backups` lists the backups. The newest should have today's or yesterday's date.
- `./dc logs worker | grep backup` shows "backup written" or "backup failed" with the reason (often a full disk).
- Make one now: `./dc exec backend python manage.py backup`
- The time zone matters: the job runs at 03:00 in the `TZ=` zone from `/opt/clinic-data/.env`.

## Text messages are not sent
- «پیامک» → «تنظیمات» must show the key as registered and sending switched on.
- `./dc logs --tail 200 worker` and look for lines starting `sms` (they hold a short code, never a number or text).
- Texts go out only between 08:00 and 21:00.
- After moving to a new server without `data/sms.key`, type the key again in the settings page.

## An upload fails
- Files must be PDF, JPG, PNG or DCM, and at most 30 MB. iPhone HEIC photos must be converted to JPG first.
- "413" or an error after a very large file: the file is over the 35 MB limit in Caddy.
- `./dc logs --tail 50 backend` shows "Permission denied" under `/data`: the data folder lost its owner. Run
  `chown -R 10001:10001 /opt/clinic-data/data`.

## After an update the site shows an error
1. `./dc logs --tail 50 backend`
2. Go back to the previous version: list the versions with `ls -d /opt/clinic/20*_*/`, then run
   `bash /opt/clinic/<older-folder>/deploy/deploy.sh`. Your data is unchanged; if a database change was applied,
   restore the backup made before the update.

## Everything is broken and I need help
Collect this and send it to the developer (it contains no patient data):
```
./dc ps
./dc logs --tail 100 backend
./dc logs --tail 50 worker
./dc logs --tail 50 caddy
df -h /
```
