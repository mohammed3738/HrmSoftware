import os
import subprocess
import sys
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = "Run Django, Celery Worker, Celery Beat & Flower using the active virtual environment."

    def handle(self, *args, **options):
        # Windows terminals often default to a legacy codepage (e.g. cp1252)
        # that can't encode emoji, which crashed this command before it ever
        # got to spawn a single subprocess. Force UTF-8 with a safe fallback
        # so the messages below never take the whole command down.
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")

        self.stdout.write(self.style.SUCCESS("🚀 Starting Django + Celery Worker + Beat + Flower...\n"))

        base_dir = os.getcwd()

        python = sys.executable  # <-- USE ACTIVE VENV PYTHON

        commands = {
            "Celery Worker": [python, "-m", "celery", "-A", "hrms", "worker", "--pool=solo", "-l", "info"],
            "Celery Beat":   [python, "-m", "celery", "-A", "hrms", "beat", "-l", "info"],
            "Flower":        [python, "-m", "celery", "-A", "hrms", "flower", "--port=5555"],
            "Django":        [python, "manage.py", "runserver"],
        }

        processes = []

        try:
            for name, cmd in commands.items():
                self.stdout.write(self.style.WARNING(f"▶ Starting {name}..."))
                p = subprocess.Popen(cmd, cwd=base_dir)
                processes.append(p)

            self.stdout.write(self.style.SUCCESS("\n✨ All services are running!"))
            self.stdout.write(self.style.SUCCESS("🌐 Flower: http://localhost:5555"))
            self.stdout.write(self.style.SUCCESS("💻 Django: http://127.0.0.1:8000\n"))

            # keep script alive until Django exits
            processes[-1].wait()

        except KeyboardInterrupt:
            self.stdout.write(self.style.ERROR("\n🛑 Shutting down..."))

        finally:
            for p in processes:
                if p.poll() is None:
                    p.terminate()

            self.stdout.write(self.style.SUCCESS("✔ All services stopped.\n"))
