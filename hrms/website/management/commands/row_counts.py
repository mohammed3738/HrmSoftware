from django.apps import apps
from django.core.management.base import BaseCommand

# Rebuilt automatically by Django or not copied during the SQLite -> PostgreSQL
# move (see DEPLOYMENT.md), so their counts are expected to differ.
SKIPPED = {
    "contenttypes.contenttype", "auth.permission", "admin.logentry",
    "sessions.session", "django_celery_results.taskresult",
    "django_celery_results.groupresult", "django_celery_results.chordcounter",
}


class Command(BaseCommand):
    help = "Print the row count of every table, for comparing two databases."

    def handle(self, *args, **options):
        for model in sorted(apps.get_models(), key=lambda m: m._meta.label_lower):
            label = model._meta.label_lower
            if label not in SKIPPED:
                self.stdout.write(f"{label} {model._base_manager.count()}")
