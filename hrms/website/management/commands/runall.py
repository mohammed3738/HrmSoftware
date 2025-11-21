import os
import subprocess
import sys
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = "Run Django server + Celery worker + Celery beat together (for local dev)."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("🚀 Starting Django + Celery (worker & beat)..."))

        # Paths
        base_dir = os.getcwd()

        # Start Celery worker (solo mode for Windows)
        worker_cmd = ["celery", "-A", "hrms", "worker", "-l", "info", "--pool=solo"]
        beat_cmd = ["celery", "-A", "hrms", "beat", "-l", "info"]
        django_cmd = ["python", "manage.py", "runserver"]

        processes = []

        try:
            # Start Celery Worker
            self.stdout.write(self.style.WARNING("⚙️  Starting Celery Worker..."))
            worker_proc = subprocess.Popen(worker_cmd, cwd=base_dir)
            processes.append(worker_proc)

            # Start Celery Beat
            self.stdout.write(self.style.WARNING("🕒 Starting Celery Beat..."))
            beat_proc = subprocess.Popen(beat_cmd, cwd=base_dir)
            processes.append(beat_proc)

            # Start Django Server
            self.stdout.write(self.style.WARNING("💻 Starting Django Server..."))
            django_proc = subprocess.Popen(django_cmd, cwd=base_dir)
            processes.append(django_proc)

            # Wait for all
            django_proc.wait()

        except KeyboardInterrupt:
            self.stdout.write(self.style.ERROR("\n🛑 Shutting down all services..."))
            for p in processes:
                p.terminate()

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"❌ Error: {e}"))
            for p in processes:
                p.terminate()
