# Setup guide: put the clinic site on a server

This guide takes you from nothing to a live, HTTPS site. You do not need to be a server expert. Copy each command
exactly, one at a time, and read the "You should see" line after it. If something does not match, stop and see
`TROUBLESHOOTING.md`.

If a Claude Code session runs on the server, it follows `DEPLOY-AGENT.md` instead of this page, and you only supply
what it asks for (domain and administrator password).

A server that already runs the **old** version of the app (with a `clinic.db` file in `/opt/clinic-data/data`) is
not set up with this page. It is moved once with `DEPLOY-AGENT-CUTOVER.md`.

You will need about one hour, a credit card for the server and the domain, and a computer with a terminal (Windows:
PowerShell. Mac and Linux: Terminal).

## Part 1. Buy the pieces

1. **A server (VPS).** Any provider works (Hetzner, DigitalOcean, Contabo, ...). Choose:
   - Ubuntu **24.04** LTS
   - at least **4 GB RAM** (the database needs it) and **40 GB disk** (patient files take space; choose more if
     the clinic scans a lot)
   - a location close to the clinic

   When it is created you get an **IP address** (like `203.0.113.10`) and a way to log in as `root`.
2. **A domain name** (like `clinic-name.com`). Any registrar works.
3. **Point the domain at the server.** In the registrar's DNS settings, add an **A record**: name `@` (or a
   subdomain such as `records`), value = the server's IP address. It can take from a few minutes to a few hours.

   You can check from your own computer: `nslookup clinic-name.com` should show the server's IP.

> The site address used below is `clinic-name.com`. Replace it with yours every time.

## Part 2. Prepare the server

4. **Log in.** In your terminal (replace the IP):

   ```
   ssh root@203.0.113.10
   ```

   Type `yes` if asked about authenticity, then the password the provider gave you. You should see a prompt ending
   in `#`.
5. **Update the system:**

   ```
   apt update && apt upgrade -y
   ```
6. **Install Docker:**

   ```
   curl -fsSL https://get.docker.com | sh
   ```

   Check: `docker --version` prints a version number, and `docker compose version` does too.
7. **Turn on the firewall.** This allows only SSH (22) and the website (80, 443). **Do the first line before the
   second**, or you lock yourself out.

   ```
   ufw allow 22/tcp
   ufw allow 80,443/tcp
   ufw enable
   ```

   Type `y` when asked. Also run `ufw allow 443/udp` (faster connections).

## Part 3. Install the app

8. **Get the code** (read-only; you never edit anything in this folder):

   ```
   git clone https://github.com/MMACABRE/KLERK.git /opt/clinic
   newest=$(ls -d /opt/clinic/20*_*/ | sort | tail -1); newest=${newest%/}; echo "$newest"
   ```

   Each published version is a folder named with a date and time. The last line prints the newest one. If it prints
   nothing, no version has been published yet.
9. **Create the data folder and the settings file.** They live in `/opt/clinic-data`, **outside** the code folder,
   so a new version of the code never touches your patients:

   ```
   mkdir -p /opt/clinic-data/data && chown 10001:10001 /opt/clinic-data/data
   printf 'DOMAIN=clinic-name.com\nDATA_PATH=/opt/clinic-data/data\nTZ=Asia/Tehran\n' > /opt/clinic-data/.env
   chmod 600 /opt/clinic-data/.env
   ```

   Put your domain in place of `clinic-name.com` (no `https://`). Change `TZ=Asia/Tehran` only if the clinic is not
   in Tehran time (`nano /opt/clinic-data/.env`, save with `Ctrl+O`, `Enter`, leave with `Ctrl+X`). Do not copy
   `deploy/.env.example`: it is a template for the developer's computer. (The data folder belongs to
   user id 10001 because the app runs as that ordinary user.)
10. **Check the server, then start everything:**

    ```
    bash "$newest/deploy/check-server.sh"
    bash "$newest/deploy/deploy.sh"
    ```

    The first line changes nothing. It prints one line per check (`OK`, `WARN` or `FAIL`) and ends with
    `summary: 0 failed`. Fix every `FAIL` before the second line; each one says what to do.

    The app comes as finished pieces ("images") that `deploy.sh` downloads from GitHub. If the server cannot reach
    GitHub, it stops without changing anything and names one file (`klerk-images-....tar.gz`). Download that file on
    a computer that can reach GitHub, copy it to the server with
    `scp klerk-images-*.tar.gz root@203.0.113.10:/opt/clinic-data/images/` (run `mkdir -p /opt/clinic-data/images`
    on the server first), and run `deploy.sh` again.

    The first time this takes several minutes. It adds three random passwords to the settings file (for the
    database and the sessions; you never need to see or type them), downloads the finished app (nothing is built
    on the server) and ends with
    `OK: https://clinic-name.com/health answers`. If it says the HTTPS check failed, wait a minute (the certificate
    is still being issued) and run the same command again.
11. **Check it runs:**

    ```
    /opt/clinic-data/dc ps
    ```

    `mysql` and `backend` should say `healthy`, `worker` and `caddy` `running`. `/opt/clinic-data/dc` is a helper
    that works like `docker compose` for the version that is running; use it for every command in this guide.
12. **Create the first administrator:**

    ```
    /opt/clinic-data/dc exec backend python manage.py create_user admin owner "مدیر سیستم"
    ```

    It asks for a password twice (nothing shows while you type). Use at least 10 characters and keep it safe. This
    first account is the **owner**: it always has every permission and nobody can restrict or delete it.
13. **Open the site.** In your browser go to `https://clinic-name.com`. You should see the sign-in page with a
    padlock. If the page does not load, wait a minute and refresh.
14. **Sign in as `admin`, then create the staff accounts** under «مدیریت کاربران». The «کارمند» preset can view and
    edit patients, documents and visits. Only users with the right permissions can delete, import, download
    everything, see money or read the activity log.

## Part 4. Daily life

### Backups
- The app writes a database backup **every night at 03:00** into `/opt/clinic-data/data/backups/` and keeps the
  last 14.
- The patient files are stored as ordinary files in `/opt/clinic-data/data/patients/`.
- The data folder is private: only its owner (user id 10001) and root can open it. Copy it as `root`, as in the
  command below, or with `sudo`; an ordinary account gets "Permission denied".
- **A backup that stays on the same server is not enough.** If the server dies, both are lost. **Once a week, copy
  the whole data folder to your own computer.** From your computer (replace the IP and the destination):

  ```
  scp -r root@203.0.113.10:/opt/clinic-data/data "D:\clinic-backups\2026-11-20"
  ```

  Another way: sign in as admin, open «ورود و خروج داده» and download the full ZIP. It contains a spreadsheet and
  every patient's files.
- To make a backup right now: `/opt/clinic-data/dc exec backend python manage.py backup`
- To list the backups: `ls -l /opt/clinic-data/data/backups`

### Update to a newer version
```
git -C /opt/clinic pull --ff-only
newest=$(ls -d /opt/clinic/20*_*/ | sort | tail -1); newest=${newest%/}; echo "$newest"
bash "$newest/deploy/check-server.sh"
bash "$newest/deploy/deploy.sh"
```
Each new version arrives as a new dated folder in `/opt/clinic`. The script makes a backup, starts the new version
with the same data folder and database, and checks that the site answers. If it fails it prints the command that
restarts the previous version (its folder is still there). Your patients and files are never touched.

### Restore a backup
This puts the whole database back to the day you choose. Everything entered after that backup is lost.

Choose the day from `ls -l /opt/clinic-data/data/backups`, then run these lines one by one (put the file name of
that day in the first line):

```
b=/opt/clinic-data/data/backups/klerk-2026-11-15.sql.gz
/opt/clinic-data/dc exec -T backend python manage.py backup --before-restore
/opt/clinic-data/dc stop backend worker
gunzip -c "$b" | /opt/clinic-data/dc exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -u root klerk' 2>&1 | grep -oE '^ERROR [0-9]+'
/opt/clinic-data/dc start backend worker
```

The second line keeps today's state as a backup first, under its own name (`...-before-restore.sql.gz`), so
it never replaces the backup you are restoring. If the fourth line prints `ERROR` and a number, send that
line to the developer and restore the backup made in the second line the same way. The `grep` at its end stops the
database from printing patient data when something fails.

Patient files are not part of the database backup; they are in `data/patients/`. Restoring an old database does not
delete newer files. They show up as "unclassified" until someone classifies them.

### Restart and reboot
Everything restarts by itself after a reboot. To test it once: `reboot`, wait two minutes, then open the site.

### Text message reminders (optional)
The app can text patients a reminder before a visit. It is off until the clinic sets it up, and it works only with
the clinic's **own** account at the SMS service IranPayamak. Nothing is sent through the developer's account.

1. Open an account at iranpayamak.com on the «نقره‌ای» plan or a higher one. The cheapest plan has no web service,
   so the app cannot use it.
2. Verify the identity in the panel (upload the documents it asks for). Unverified panels are blocked.
3. In the panel open «وب‌سرویس» → «لیست کلیدهای دسترسی» and create a key. Keep it private; it is a password for
   sending texts and spending the credit.
4. Charge some credit. Each text costs about 250 toman; a long text is billed per part.
5. In the app open «پیامک» → «تنظیمات», paste the key into «کلید پیامک» and save it. The app checks it with the
   service before saving. Then save the alert number and send a test text; it must arrive on that phone.
6. Switch «ارسال پیامک فعال باشد» on. The page shows how many planned visits get a reminder and asks for a tick
   before it saves.

Good to know:
- Texts go out between 08:00 and 21:00 (the server's clock, `TZ=Asia/Tehran`) and carry only name, date and time.
- The key is stored encrypted. The file that unlocks it is `/opt/clinic-data/data/sms.key`; keep it with the rest
  of the data folder. If you restore the database on a new server **without** `sms.key`, the app shows "key not
  registered" and you type the key again.
- When the credit gets low the app texts the alert number once, and the dashboard shows a card.

### Look at the logs
```
/opt/clinic-data/dc logs --tail 100 backend
/opt/clinic-data/dc logs --tail 100 worker
/opt/clinic-data/dc logs --tail 100 caddy
```

## Safety checklist
- [ ] The first administrator has a strong password nobody else knows.
- [ ] The firewall shows only 22, 80, 443 (`ufw status`).
- [ ] A copy of the data folder is on a different computer or disk.
- [ ] Each staff member has their own account (never share one).
- [ ] The server is updated now and then: `apt update && apt upgrade -y`, then `reboot`.
