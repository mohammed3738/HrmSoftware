"""Nightly backup sent by email -- nothing is kept on the server.

Dumps the PostgreSQL database (and the media folder when it fits under the
attachment limit) into a temporary folder, emails it, then deletes the
folder. If anything fails, an error email is sent instead, so a silent
failure can't go unnoticed.

Run by cron (see DEPLOYMENT.md, "Backups"):
    /home/multihost/hrms_prod/venv/bin/python /home/multihost/hrms_prod/hrms/scripts/email_backup.py

Settings come from hrms/.env: the DB_* values plus the BACKUP_EMAIL_* ones
documented in .env.example.
"""
import os
import shutil
import smtplib
import socket
import subprocess
import sys
import tarfile
import tempfile
import traceback
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_DIR / ".env")


def env(name, default=None):
    value = os.environ.get(name, default)
    if value is None or value == "":
        sys.exit(f"Missing {name} in {PROJECT_DIR / '.env'}")
    return value


def send(subject, body, attachments=()):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = env("BACKUP_EMAIL_FROM", os.environ.get("BACKUP_EMAIL_USER"))
    msg["To"] = env("BACKUP_EMAIL_TO")
    msg.set_content(body)
    for path in attachments:
        msg.add_attachment(path.read_bytes(), maintype="application",
                           subtype="octet-stream", filename=path.name)

    host, port = env("BACKUP_EMAIL_HOST"), int(env("BACKUP_EMAIL_PORT", "587"))
    user, password = env("BACKUP_EMAIL_USER"), env("BACKUP_EMAIL_PASSWORD")
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=120)
    else:
        server = smtplib.SMTP(host, port, timeout=120)
        server.starttls()
    with server:
        server.login(user, password)
        server.send_message(msg)


def mb(path):
    return path.stat().st_size / (1024 * 1024)


def main():
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    name = os.environ.get("BACKUP_NAME", "hrms_prod")
    # Base64 encoding makes attachments ~33% bigger; 18 MB of files keeps the
    # email under Gmail's 25 MB limit.
    limit_mb = float(os.environ.get("BACKUP_EMAIL_MAX_MB", "18"))
    host = socket.gethostname()
    tmp = Path(tempfile.mkdtemp(prefix=f"{name}_backup_"))
    try:
        dump = tmp / f"{name}_db_{stamp}.dump"
        subprocess.run(
            ["pg_dump", "-h", env("DB_HOST", "127.0.0.1"), "-p", env("DB_PORT", "5432"),
             "-U", env("DB_USER"), "-Fc", "-f", str(dump), env("DB_NAME")],
            check=True, capture_output=True, text=True,
            env={**os.environ, "PGPASSWORD": env("DB_PASSWORD")},
        )
        attachments, notes = [dump], [f"Database dump: {dump.name} ({mb(dump):.2f} MB)"]

        media_dir = PROJECT_DIR / "media"
        if media_dir.is_dir():
            media = tmp / f"{name}_media_{stamp}.tar.gz"
            with tarfile.open(media, "w:gz") as tar:
                tar.add(media_dir, arcname="media")
            if mb(dump) + mb(media) <= limit_mb:
                attachments.append(media)
                notes.append(f"Uploaded files: {media.name} ({mb(media):.2f} MB)")
            else:
                notes.append(
                    f"Uploaded files NOT attached: the archive is {mb(media):.1f} MB, over the "
                    f"{limit_mb:.0f} MB email limit. Back up the media folder another way "
                    "(see DEPLOYMENT.md, 'Backups')."
                )

        if mb(dump) > limit_mb:
            raise RuntimeError(
                f"The database dump alone is {mb(dump):.1f} MB, over the {limit_mb:.0f} MB "
                "email limit -- email backups are no longer enough for this database."
            )

        send(
            f"[{name}] Backup {stamp} OK",
            f"Nightly backup from {host}.\n\n" + "\n".join(notes)
            + "\n\nRestore instructions: DEPLOYMENT.md, 'Restoring a backup'.\n",
            attachments,
        )
        print(f"Backup {stamp} emailed: " + "; ".join(notes))
    except Exception as exc:
        detail = exc.stderr if isinstance(exc, subprocess.CalledProcessError) else traceback.format_exc()
        print(f"Backup {stamp} FAILED:\n{detail}", file=sys.stderr)
        try:
            send(f"[{name}] Backup {stamp} FAILED", f"The nightly backup on {host} failed:\n\n{detail}")
        except Exception:
            print("Could not send the failure email either:\n" + traceback.format_exc(), file=sys.stderr)
        sys.exit(1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
