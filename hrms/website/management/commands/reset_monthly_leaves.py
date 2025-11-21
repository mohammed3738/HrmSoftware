from django.core.management.base import BaseCommand
from website.signals import reset_monthly_leave_balances

class Command(BaseCommand):
    help = "Resets monthly leave balances and creates history"

    def handle(self, *args, **options):
        reset_monthly_leave_balances()
        self.stdout.write(self.style.SUCCESS("✅ Monthly leave reset completed successfully"))
