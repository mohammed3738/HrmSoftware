# HRMS (`hrms_prod`) – Production Deployment Guide

**Server:** Ubuntu 24.04, user `multihost`, home `/home/multihost` (shared with other projects)
**Project name on the server:** `hrms_prod`, installed in `/home/multihost/hrms_prod`
**Domain:** `hrms.zacoinfotech.com`
**Stack:** nginx → gunicorn → Django 5.2 · PostgreSQL · Redis · Celery worker + Celery beat

This installs HRMS as a **new, separate project**. The old install in `/home/multihost/HrmSoftware` isn't modified at any point. It keeps running until you switch the domain over in Step 11, and stays available as a fallback afterwards.

Every command block is meant to be pasted into the SSH session as `multihost`. Run them **in order** and check each block's output before moving on. Commands that need root use `sudo`.

> **Other projects on this server are not touched.** Everything this guide creates is named after `hrms_prod`: folder, database, services, nginx site, Redis databases and gunicorn port. `nginx`, `postgresql` and `redis-server` are never stopped or restarted; nginx is only *reloaded*, which doesn't drop live connections.

---

## What you will end up with

| Piece | Value |
|---|---|
| Code | `/home/multihost/hrms_prod` (git clone). The Django project is in `hrms_prod/hrms` |
| Python virtualenv | `/home/multihost/hrms_prod/venv` |
| Config / secrets | `/home/multihost/hrms_prod/hrms/.env`, built from `.env.example` (mode 600, never committed) |
| Database | PostgreSQL database `hrms_prod_db`, owned by role `hrms_prod_user` |
| App server | systemd service `hrms-prod-gunicorn`, listening on `127.0.0.1:8025` |
| Background jobs | systemd services `hrms-prod-celery` (worker) and `hrms-prod-celerybeat` (scheduler) |
| Redis | database `10` (Celery queue) and `11` (cache) |
| Web server | nginx site `/etc/nginx/sites-available/hrms_prod`, HTTPS via Let's Encrypt |
| Static files | `/home/multihost/hrms_prod/hrms/staticfiles` (served by nginx) |
| Uploaded files | `/home/multihost/hrms_prod/hrms/media` (served by nginx) |
| Backups | `/home/multihost/hrms_prod_backups` |

---

## Step 0 – On your PC: push the code

The server installs whatever is on GitHub. Commit and push first; this release includes the PostgreSQL support in `settings.py`, the new packages in `requirements.txt`, `.env.example` and the `row_counts` command.

```bash
cd D:\HrmSoftware
git status
git add -A
git commit -m "Production settings: PostgreSQL, .env config, gunicorn"
git push origin main
```

Check that `git status` lists `hrms/.env.example` (it must be pushed) but **not** `hrms/.env` or `db.sqlite3`; both are git-ignored and must never be pushed.

---

## Step 1 – Check the server *(read-only)*

Nothing here changes the server. Paste it and read the notes below the block.

```bash
echo "=== hrms_prod must not exist yet (should print nothing) ==="
ls -d /home/multihost/hrms_prod 2>/dev/null
ls /etc/systemd/system/hrms-prod-*.service /etc/nginx/sites-available/hrms_prod 2>/dev/null
sudo -u postgres psql -tAc "SELECT datname FROM pg_database WHERE datname='hrms_prod_db'" 2>/dev/null

echo "=== Is port 8025 free? (should print nothing) ==="
sudo ss -ltnp | grep ":8025 " || true

echo "=== Redis databases already in use ==="
redis-cli INFO keyspace 2>/dev/null || echo "(redis not installed yet)"

echo "=== Which nginx config currently serves the domain ==="
sudo grep -rl "hrms.zacoinfotech.com" /etc/nginx/sites-enabled/ 2>/dev/null || echo "(none)"

echo "=== Old install (left untouched; only needed if you copy its data) ==="
ls -la /home/multihost/HrmSoftware/hrms/db.sqlite3 2>/dev/null || echo "(no old SQLite database)"
du -sh /home/multihost/HrmSoftware/hrms/media 2>/dev/null || echo "(no old media folder)"

echo "=== Installed versions ==="
python3 --version; psql --version 2>/dev/null; redis-server --version 2>/dev/null; nginx -v 2>&1
```

How to read the output:

- **First section:** if anything is printed, an earlier `hrms_prod` attempt exists. See [Starting over](#starting-over-from-scratch).
- **Port 8025:** if something is listening there, choose another free port (e.g. `8026`) and replace `8025` in Steps 6, 10 and 11.
- **Redis keyspace:** lines look like `db0:keys=12,...`. This guide uses `db10` and `db11`. If either is listed, choose two unused numbers between 0 and 15 and use them in Step 5.
- **nginx config for the domain:** write the file name down. This is the old site; Step 11 switches the domain from it to `hrms_prod`.

---

## Step 2 – Install system packages

`--no-upgrade` installs only what is missing and **never upgrades** packages that other projects already use.

```bash
sudo apt-get update
sudo apt-get install -y --no-upgrade \
    git python3-venv python3-dev build-essential pkg-config \
    libcairo2-dev libffi-dev libjpeg-dev zlib1g-dev \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
    postgresql postgresql-contrib redis-server nginx \
    certbot python3-certbot-nginx acl

sudo systemctl enable --now postgresql redis-server nginx
systemctl is-active postgresql redis-server nginx
```

The last line must print `active` three times.

What the less obvious packages are for: `libcairo2-dev` and `pkg-config` are needed to build `pycairo`, which the salary-slip PDFs depend on. The `libpango*` and `libharfbuzz0b` libraries are needed by `weasyprint`. `acl` lets nginx read the static and uploaded files without opening up the whole home folder.

---

## Step 3 – Get the code

```bash
cd /home/multihost
git clone https://github.com/mohammed3738/HrmSoftware.git hrms_prod
cd hrms_prod
git log -1 --oneline
ls hrms/manage.py hrms/.env.example
```

The `hrms_prod` at the end of the `git clone` line is the folder name. The last line must list both files. If the repository is private, GitHub will ask for a username and a **personal access token**, not your password.

---

## Step 4 – Python environment and dependencies

```bash
cd /home/multihost/hrms_prod
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip wheel
pip install -r hrms/requirements.txt
python -c "import django, psycopg, gunicorn, celery, xhtml2pdf, dotenv; print('Dependencies OK - Django', django.get_version())"
```

The last line must print `Dependencies OK - Django 5.2.8`. If `pip install` fails while building `pycairo`, a Step 2 package is missing; re-run Step 2.

---

## Step 5 – Create `.env` from `.env.example`

This copies the template and fills in a random Django secret key and database password. You never have to type them. Every other value in `.env.example` is already correct for this server; read the comments in the file for what each one does.

> If Step 1 showed Redis `db10` or `db11` in use, edit the two `redis://` lines afterwards: `nano .env`.

```bash
cd /home/multihost/hrms_prod/hrms
source ../venv/bin/activate
cp .env.example .env
chmod 600 .env

SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(50))")
DBPASS=$(openssl rand -hex 24)
sed -i "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=${SECRET}|" .env
sed -i "s|^DB_PASSWORD=.*|DB_PASSWORD=${DBPASS}|" .env
unset SECRET DBPASS

grep -c "change-me" .env || true
grep -v -E "^#|^$|SECRET_KEY|PASSWORD" .env
```

`grep -c "change-me"` must print `0`, meaning both placeholders were replaced. The last command shows the settings with the two secrets hidden. If you ever need the database password, it's in `.env` (`grep DB_PASSWORD .env`).

---

## Step 6 – Create the PostgreSQL database

The password is read from `.env`, so it always matches what Django uses. Running this block twice is safe.

```bash
cd /home/multihost/hrms_prod/hrms
DBPASS=$(grep '^DB_PASSWORD=' .env | cut -d= -f2)

sudo -u postgres psql -v ON_ERROR_STOP=1 <<EOF
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'hrms_prod_user') THEN
    CREATE ROLE hrms_prod_user LOGIN PASSWORD '${DBPASS}';
  ELSE
    ALTER ROLE hrms_prod_user WITH LOGIN PASSWORD '${DBPASS}';
  END IF;
END
\$\$;
ALTER ROLE hrms_prod_user SET client_encoding TO 'utf8';
ALTER ROLE hrms_prod_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE hrms_prod_user SET timezone TO 'UTC';
EOF

sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='hrms_prod_db'" | grep -q 1 \
  || sudo -u postgres createdb -O hrms_prod_user -E UTF8 -T template0 hrms_prod_db
unset DBPASS

source ../venv/bin/activate
python manage.py shell -c "from django.db import connection; connection.ensure_connection(); print('Connected to', connection.vendor, connection.settings_dict['NAME'])"
```

The last line must print `Connected to postgresql hrms_prod_db`. You can ignore a `could not change directory to "/home/multihost/..."` warning from `psql`.

---

## Step 7 – Create the tables and load data

Choose **one** option.

### Option A – start with an empty system

```bash
cd /home/multihost/hrms_prod/hrms
source ../venv/bin/activate
python manage.py migrate --noinput
python manage.py createsuperuser
```

`migrate` also seeds the default roles and permissions.

### Option B – copy all data from the old `HrmSoftware` install

This **copies** the old SQLite database and uploaded files into `hrms_prod`, converts the copy, and loads it into PostgreSQL. The old install is only read, never written.

> **Copies are a snapshot.** Anything entered in the old app *after* the copy isn't included. You can safely do a trial run now and **repeat this whole block** just before switching the domain (Step 11). For that final run, first stop the old app, or at least tell users not to make changes, so the snapshot is complete.

```bash
cd /home/multihost/hrms_prod/hrms
source ../venv/bin/activate
export PYTHONUTF8=1
BK=/home/multihost/hrms_prod_backups/import_$(date +%Y%m%d_%H%M)
mkdir -p "$BK" media

# 1. Copy the old database and uploads (read-only for the old install)
cp -a /home/multihost/HrmSoftware/hrms/db.sqlite3 db.sqlite3
rsync -a /home/multihost/HrmSoftware/hrms/media/ media/
cp -a db.sqlite3 "$BK/db.sqlite3.original"

# 2. Integrity check of the copy - must print "SQLite OK"
python - <<'PY'
import sqlite3
con = sqlite3.connect("db.sqlite3")
assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "SQLite file is damaged"
bad = con.execute("PRAGMA foreign_key_check").fetchall()
print("SQLite OK" if not bad else f"Broken references (fix before continuing): {bad[:20]}")
PY

# 3. Bring the copy up to the new code's schema, then count and export every row
DB_ENGINE=sqlite python manage.py migrate --noinput
DB_ENGINE=sqlite python manage.py row_counts > "$BK/counts_sqlite.txt"
DB_ENGINE=sqlite python manage.py dumpdata --all --natural-foreign --natural-primary \
    -e contenttypes -e auth.permission -e admin.logentry -e sessions.session -e django_celery_results \
    -o "$BK/hrms_data.json"
ls -lh "$BK/hrms_data.json"

# 4. Create the tables in PostgreSQL, empty them, and import
python manage.py migrate --noinput
python manage.py flush --noinput
python manage.py loaddata "$BK/hrms_data.json"

# 5. Compare - must print "ALL COUNTS MATCH"
python manage.py row_counts > "$BK/counts_postgres.txt"
diff "$BK/counts_sqlite.txt" "$BK/counts_postgres.txt" && echo "ALL COUNTS MATCH"
```

**Do not continue** unless the last line is `ALL COUNTS MATCH`. `diff` shows any table whose count differs.

Notes on this step:

- **`DB_ENGINE=sqlite` in front of a command** makes just that command use the copied `db.sqlite3` instead of PostgreSQL, which is what `.env` says.
- **Why `flush` before `loaddata`:** `migrate` seeds default roles and permissions. `flush` empties them so the import doesn't hit duplicates; the import then restores your real ones. Because of this, re-running the whole block replaces the PostgreSQL data with a fresh copy.
- **What isn't copied:**
  - Login sessions: everyone logs in once more.
  - Celery task-result history.
  - The admin "recent actions" log.
  - Django's internal content-type and permission tables, which are rebuilt automatically.
- **If `loaddata` fails**, see [Troubleshooting](#troubleshooting). Fix the problem in the copied `db.sqlite3`, then rerun parts 3–5.

---

## Step 8 – Static files, uploads and file permissions

```bash
cd /home/multihost/hrms_prod/hrms
source ../venv/bin/activate
mkdir -p media staticfiles
python manage.py collectstatic --noinput

# Let nginx (user www-data) read static files and uploads - nothing else in /home/multihost.
sudo setfacl -m u:www-data:--x /home/multihost /home/multihost/hrms_prod /home/multihost/hrms_prod/hrms
sudo setfacl -R -m u:www-data:rX staticfiles media
sudo setfacl -R -d -m u:www-data:rX staticfiles media      # also applies to files created later

# Check - must print "nginx can read static"
F=$(find staticfiles -type f | head -1)
sudo -u www-data test -r "$F" && echo "nginx can read static" || echo "PROBLEM: nginx cannot read $F"

python manage.py check --deploy
```

`check --deploy` reports two warnings that are expected and safe to ignore: `SECURE_HSTS_SECONDS` and `SECURE_SSL_REDIRECT`. nginx does the HTTP → HTTPS redirect itself (Step 11).

---

## Step 9 – systemd services (gunicorn, Celery worker, Celery beat)

```bash
sudo tee /etc/systemd/system/hrms-prod-gunicorn.service > /dev/null <<'EOF'
[Unit]
Description=hrms_prod Django app (gunicorn)
After=network.target postgresql.service redis-server.service
Wants=postgresql.service redis-server.service

[Service]
User=multihost
Group=multihost
WorkingDirectory=/home/multihost/hrms_prod/hrms
ExecStart=/home/multihost/hrms_prod/venv/bin/gunicorn hrms.wsgi:application \
    --bind 127.0.0.1:8025 \
    --workers 3 \
    --timeout 300 \
    --access-logfile - \
    --error-logfile -
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/hrms-prod-celery.service > /dev/null <<'EOF'
[Unit]
Description=hrms_prod Celery worker
After=network.target postgresql.service redis-server.service
Wants=postgresql.service redis-server.service

[Service]
User=multihost
Group=multihost
WorkingDirectory=/home/multihost/hrms_prod/hrms
ExecStart=/home/multihost/hrms_prod/venv/bin/celery -A hrms worker \
    --loglevel=INFO --concurrency=2 --hostname=hrms_prod@%%h
Restart=always
RestartSec=5
TimeoutStopSec=60

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/hrms-prod-celerybeat.service > /dev/null <<'EOF'
[Unit]
Description=hrms_prod Celery beat (scheduled jobs)
After=network.target postgresql.service redis-server.service
Wants=postgresql.service redis-server.service

[Service]
User=multihost
Group=multihost
WorkingDirectory=/home/multihost/hrms_prod/hrms
ExecStart=/home/multihost/hrms_prod/venv/bin/celery -A hrms beat \
    --loglevel=INFO --pidfile=
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now hrms-prod-gunicorn hrms-prod-celery hrms-prod-celerybeat
sleep 5
systemctl is-active hrms-prod-gunicorn hrms-prod-celery hrms-prod-celerybeat
curl -s -o /dev/null -w "App answered with HTTP %{http_code}\n" -H "Host: hrms.zacoinfotech.com" http://127.0.0.1:8025/
```

You should see `active` three times, then `App answered with HTTP 302` (a redirect to the login page). If not, see [Logs](#logs).

The app is now running privately on the server, but the domain still points at the old site. That's a good moment to check `hrms_prod` before users see it.

Why some settings are the way they are:

- **Port and timeout:** the app listens on `127.0.0.1` only, never directly on the internet. `--timeout 300` gives Excel imports and payroll recalculation time to finish.
- **Celery:** `--hostname=hrms_prod@...` keeps this worker distinct from other projects' workers, including the old HRMS. The Redis database numbers in `.env` keep their task queues separate.
- **Celery beat:** `--pidfile=` (empty) stops beat writing a pid lock file. A crashed beat could otherwise leave a stale lock that blocks the next start.

> **Old HRMS scheduled jobs:** if the old install also runs Celery beat, both installs will run the same scheduled jobs, each against its own database. That does no harm before the switch. After Step 11, stop the old install's Celery services. They're the ones whose service files mention `/home/multihost/HrmSoftware`:
> `grep -l "HrmSoftware" /etc/systemd/system/*.service`

---

## Step 10 – (Option B only) Final data copy

If you loaded data with Option B and users kept working in the old app since then, refresh the copy now:

1. Stop the old app, or tell users not to make changes.
2. Run the **whole Option B block from Step 7** again. It replaces `hrms_prod`'s data with a fresh snapshot.
3. Restart the new app so it picks up the fresh data:

```bash
sudo systemctl restart hrms-prod-gunicorn hrms-prod-celery hrms-prod-celerybeat
```

---

## Step 11 – Point the domain at `hrms_prod` (nginx + HTTPS)

First disable the old site for this domain. Use the file name Step 1 printed from `sites-enabled`:

```bash
sudo rm /etc/nginx/sites-enabled/OLD_FILE      # <-- the name from Step 1; this only removes the symlink, the file stays in sites-available
```

Then create and enable the `hrms_prod` site:

```bash
sudo tee /etc/nginx/sites-available/hrms_prod > /dev/null <<'EOF'
server {
    listen 80;
    listen [::]:80;
    server_name hrms.zacoinfotech.com;

    client_max_body_size 50M;     # Excel / document uploads

    location /static/ {
        alias /home/multihost/hrms_prod/hrms/staticfiles/;
        expires 7d;
        access_log off;
    }

    location /media/ {
        alias /home/multihost/hrms_prod/hrms/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8025;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/hrms_prod /etc/nginx/sites-enabled/hrms_prod
sudo nginx -t && sudo systemctl reload nginx
```

**Only reload if `nginx -t` says `syntax is ok` and `test is successful`.** If it fails, the running config keeps serving every site; fix the error and run the last line again. A warning like `conflicting server name "hrms.zacoinfotech.com"` means the old site is still enabled, so remove its symlink as shown above.

Now turn on HTTPS. Certbot adds the certificate and the HTTP → HTTPS redirect to the `hrms_prod` site:

```bash
sudo certbot --nginx -d hrms.zacoinfotech.com --redirect
sudo nginx -t && sudo systemctl reload nginx
curl -s -o /dev/null -w "HTTPS answered with HTTP %{http_code}\n" https://hrms.zacoinfotech.com/
```

If a certificate for the domain already exists, choose **"Attempt to reinstall this existing certificate"**. The `curl` line should print `HTTPS answered with HTTP 302`.

---

## Step 12 – Final checks

```bash
cd /home/multihost/hrms_prod/hrms
source ../venv/bin/activate

systemctl is-active hrms-prod-gunicorn hrms-prod-celery hrms-prod-celerybeat nginx postgresql redis-server
celery -A hrms inspect ping --timeout 5
sudo journalctl -u hrms-prod-celerybeat --since "5 min ago" --no-pager | tail -5
curl -s -o /dev/null -w "Static file: HTTP %{http_code}\n" https://hrms.zacoinfotech.com/static/$(cd staticfiles && find . -type f -name "*.css" | head -1 | sed 's|^\./||')
```

Expected:

- `active` six times.
- The ping replies with `hrms_prod@hostingserver: OK pong`.
- The beat log shows `Sending due task ...` lines; several jobs run every minute.
- The static file returns `HTTP 200`.

Then in a browser, at `https://hrms.zacoinfotech.com`:

1. Log in. With Option B, everyone has to log in again once, because sessions weren't copied.
2. Open **Employees**, **Attendance Register**, **Leave Balance**, **Payroll Run** and **My Salary Slips**. With Option B, check the numbers match the old app.
3. Download one salary slip PDF.
4. Open an employee who has uploaded documents, and open one document. This proves `/media/` works.

Once you're happy, stop the old install's background services so its scheduled jobs no longer run, and leave its files in place as a fallback:

```bash
grep -l "HrmSoftware" /etc/systemd/system/*.service          # lists the old install's services
# sudo systemctl disable --now OLD_SERVICE_NAME              # <-- for each one listed
```

---

## Routine updates (every later deploy)

After pushing new code from your PC:

```bash
cd /home/multihost/hrms_prod
git pull --ff-only origin main
source venv/bin/activate
pip install -r hrms/requirements.txt
cd hrms
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py check --deploy --fail-level ERROR
sudo systemctl restart hrms-prod-gunicorn hrms-prod-celery hrms-prod-celerybeat
systemctl is-active hrms-prod-gunicorn hrms-prod-celery hrms-prod-celerybeat
```

If a new release adds a setting to `.env.example`, add the same line to your `.env`. To spot missing ones:

```bash
cd /home/multihost/hrms_prod/hrms
diff <(grep -oE "^[A-Z_]+" .env.example | sort) <(grep -oE "^[A-Z_]+" .env | sort)
```

Lines starting with `<` are in the template but missing from `.env`.

---

## Backups

### Nightly automatic backup

This keeps 14 days of database dumps and media archives:

```bash
mkdir -p /home/multihost/hrms_prod_backups/nightly
cat > /home/multihost/hrms_prod_backups/backup.sh <<'EOF'
#!/bin/bash
set -euo pipefail
DIR=/home/multihost/hrms_prod_backups/nightly
ENV=/home/multihost/hrms_prod/hrms/.env
STAMP=$(date +%Y%m%d_%H%M)
PGPASSWORD=$(grep '^DB_PASSWORD=' "$ENV" | cut -d= -f2) \
  pg_dump -h 127.0.0.1 -U hrms_prod_user -Fc hrms_prod_db > "$DIR/hrms_prod_db_$STAMP.dump"
tar -czf "$DIR/media_$STAMP.tar.gz" -C /home/multihost/hrms_prod/hrms media
find "$DIR" -type f -mtime +14 -delete
EOF
chmod 700 /home/multihost/hrms_prod_backups/backup.sh
/home/multihost/hrms_prod_backups/backup.sh && ls -lh /home/multihost/hrms_prod_backups/nightly
( crontab -l 2>/dev/null | grep -v hrms_prod_backups/backup.sh; echo "30 2 * * * /home/multihost/hrms_prod_backups/backup.sh" ) | crontab -
crontab -l | grep backup.sh
```

The script runs once immediately as a test, then nightly at 02:30. Copy a dump off the server now and then; a backup on the same disk doesn't protect you if the disk fails.

### Restoring a database dump

This replaces the live database with the backup:

```bash
sudo systemctl stop hrms-prod-gunicorn hrms-prod-celery hrms-prod-celerybeat
cd /home/multihost/hrms_prod/hrms
PGPASSWORD=$(grep '^DB_PASSWORD=' .env | cut -d= -f2) \
  pg_restore -h 127.0.0.1 -U hrms_prod_user -d hrms_prod_db --clean --if-exists \
  /home/multihost/hrms_prod_backups/nightly/hrms_prod_db_YYYYMMDD_HHMM.dump     # <-- pick the file
sudo systemctl start hrms-prod-gunicorn hrms-prod-celery hrms-prod-celerybeat
```

---

## Switching back to the old site *(emergency only)*

The old install was never modified, so switching back only means pointing the domain at it again:

```bash
sudo rm /etc/nginx/sites-enabled/hrms_prod
sudo ln -s /etc/nginx/sites-available/OLD_FILE /etc/nginx/sites-enabled/OLD_FILE   # the file noted in Step 1
sudo nginx -t && sudo systemctl reload nginx
# then re-enable the old install's services if you disabled them in Step 12:
# sudo systemctl enable --now OLD_SERVICE_NAME
```

You may need to run `sudo certbot --nginx -d hrms.zacoinfotech.com` again so the old site has HTTPS. Data entered in `hrms_prod` after the switch only exists in its PostgreSQL database.

---

## Starting over from scratch

If an install attempt went wrong and you want to remove `hrms_prod` completely before redoing the guide, run this. It **permanently deletes** `hrms_prod`'s database and files; the old install and other projects aren't affected.

```bash
sudo systemctl disable --now hrms-prod-gunicorn hrms-prod-celery hrms-prod-celerybeat 2>/dev/null
sudo rm -f /etc/systemd/system/hrms-prod-*.service && sudo systemctl daemon-reload
sudo rm -f /etc/nginx/sites-enabled/hrms_prod /etc/nginx/sites-available/hrms_prod
sudo nginx -t && sudo systemctl reload nginx
sudo -u postgres dropdb --if-exists hrms_prod_db
sudo -u postgres psql -c "DROP ROLE IF EXISTS hrms_prod_user;"
rm -rf /home/multihost/hrms_prod
```

Backups in `/home/multihost/hrms_prod_backups` are kept.

---

## Logs

```bash
sudo journalctl -u hrms-prod-gunicorn -n 100 --no-pager        # web app errors (Python tracebacks)
sudo journalctl -u hrms-prod-celery -n 100 --no-pager          # background task errors
sudo journalctl -u hrms-prod-celerybeat -n 100 --no-pager      # scheduler
sudo journalctl -u hrms-prod-gunicorn -f                       # follow live (Ctrl+C to stop)
sudo tail -n 50 /var/log/nginx/error.log                       # nginx errors (502s, permission denied)
```

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| **502 Bad Gateway** | gunicorn isn't running or is on a different port. `systemctl status hrms-prod-gunicorn`, then check the logs. Confirm the port is `8025` in both the service file and the nginx site. |
| **400 Bad Request** | The domain isn't in `DJANGO_ALLOWED_HOSTS` in `.env`. Add it, then `sudo systemctl restart hrms-prod-gunicorn`. |
| **403 CSRF verification failed** when logging in | `DJANGO_CSRF_TRUSTED_ORIGINS` must be exactly `https://hrms.zacoinfotech.com`. Also make sure you're on `https://`: with `DJANGO_SECURE_COOKIES=true`, plain `http://` logins fail by design. |
| Page has **no styling** | Run `collectstatic` (Step 8), then check the nginx error log for `Permission denied` and re-run the `setfacl` lines. |
| **Uploaded documents 404/403** | Option B: check `media/` was copied (`du -sh media`). Then re-run the `setfacl` lines in Step 8. |
| `loaddata`: **value too long for type character varying(N)** | SQLite never enforced field lengths, PostgreSQL does. The error names the table and field. Find the row in the copied SQLite with `DB_ENGINE=sqlite python manage.py shell` and shorten the value, then rerun parts 3–5 of Option B. |
| `loaddata`: **numeric field overflow** | Same idea: a number is larger than the field allows. Fix it in the copied SQLite and rerun parts 3–5. |
| `loaddata`: **duplicate key value violates unique constraint** | The `flush` was skipped. Run `python manage.py flush --noinput`, then `loaddata` again. |
| `loaddata`: **UnicodeDecodeError** | The export wasn't written as UTF-8. Rerun the block in the same shell after `export PYTHONUTF8=1`. |
| **password authentication failed for user "hrms_prod_user"** | `.env` and PostgreSQL disagree. Re-run Step 6, which resets the role's password from `.env`. |
| **permission denied for schema public** | The database isn't owned by the app's role: `sudo -u postgres psql -c "ALTER DATABASE hrms_prod_db OWNER TO hrms_prod_user;"` |
| Scheduled jobs never run | `systemctl status hrms-prod-celerybeat hrms-prod-celery`. Both must be active, and `CELERY_BROKER_URL` must use a Redis database no other project uses. |
| `pip install` fails building **pycairo** | Re-run Step 2. `libcairo2-dev` and `pkg-config` are required. |
| Changed `.env` but nothing happened | Settings load once at start-up: `sudo systemctl restart hrms-prod-gunicorn hrms-prod-celery hrms-prod-celerybeat` |

---

## Configuration reference (`hrms/.env`)

The template is [`hrms/.env.example`](hrms/.env.example). Its comments explain each value.

| Variable | Purpose | `hrms_prod` value |
|---|---|---|
| `DJANGO_SECRET_KEY` | Signs sessions and tokens. Changing it logs everyone out. | Random (generated in Step 5) |
| `DJANGO_DEBUG` | Shows full error pages. **Must be `false` in production.** | `false` |
| `DJANGO_ALLOWED_HOSTS` | Domains the app answers to (comma-separated) | `hrms.zacoinfotech.com,127.0.0.1,localhost` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | HTTPS origins allowed to submit forms | `https://hrms.zacoinfotech.com` |
| `DJANGO_SECURE_COOKIES` | Send login cookies over HTTPS only | `true` |
| `DB_ENGINE` | `postgres`, or `sqlite` (the default when unset) | `postgres` |
| `DB_NAME` / `DB_USER` | PostgreSQL database and role | `hrms_prod_db` / `hrms_prod_user` |
| `DB_PASSWORD` | PostgreSQL password | Random (generated in Step 5) |
| `DB_HOST` / `DB_PORT` | PostgreSQL server | `127.0.0.1` / `5432` |
| `SQLITE_PATH` | Location of the SQLite file when `DB_ENGINE=sqlite` | `hrms/db.sqlite3` (default) |
| `CELERY_BROKER_URL` | Redis database for the Celery task queue | `redis://127.0.0.1:6379/10` |
| `REDIS_CACHE_URL` | Redis database for Django's cache | `redis://127.0.0.1:6379/11` |

Without a `.env` file, for example on a developer PC, every value falls back to the development defaults: SQLite, `DEBUG=True`, local Redis databases `0` and `1`.
