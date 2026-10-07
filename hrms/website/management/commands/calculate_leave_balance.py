"""Recalculate leave balances from the command line.

Uses the same calculation as the Leave Balance page and the automatic
recalculation: every payroll period with attendance, oldest first, leaving
finalized payroll periods untouched.

    python manage.py calculate_leave_balance --employee-id=12
    python manage.py calculate_leave_balance --company-id=1
    python manage.py calculate_leave_balance --all
"""
from django.core.management.base import BaseCommand, CommandError

from website.models import Company, Employee
from website.signals import _leave_balance_periods, _recalculate_periods, recalculate_all_leave_balances


class Command(BaseCommand):
    help = "Recalculate leave balances for one employee, one company, or everyone."

    def add_arguments(self, parser):
        parser.add_argument("--employee-id", type=int, help="Recalculate one employee")
        parser.add_argument("--company-id", type=int, help="Recalculate every active employee of one company")
        parser.add_argument("--all", action="store_true", help="Recalculate every active employee")

    def handle(self, *args, **options):
        if options["all"]:
            done, skipped = recalculate_all_leave_balances()
            self.stdout.write(self.style.SUCCESS(
                f"Recalculated {done} leave balance period(s); {skipped} employee(s) skipped (no payroll cycle)."
            ))
            return

        if options["employee_id"]:
            employees = Employee.objects.filter(pk=options["employee_id"])
            if not employees.exists():
                raise CommandError(f"No employee with id {options['employee_id']}.")
        elif options["company_id"]:
            if not Company.objects.filter(pk=options["company_id"]).exists():
                raise CommandError(f"No company with id {options['company_id']}.")
            employees = Employee.objects.filter(company_id=options["company_id"], status="Active")
        else:
            raise CommandError("Specify --employee-id, --company-id or --all.")

        from website.views import _payroll_settings_with_cycle

        done = 0
        for employee in employees.select_related("company"):
            payroll_settings = _payroll_settings_with_cycle(employee.company)
            if not payroll_settings:
                self.stdout.write(self.style.WARNING(f"{employee.employee_code}: no payroll cycle configured, skipped"))
                continue
            periods = _leave_balance_periods(employee, payroll_settings)
            count = _recalculate_periods(employee, payroll_settings, periods)
            done += count
            self.stdout.write(f"{employee.employee_code}: {count} period(s)")
        self.stdout.write(self.style.SUCCESS(f"Recalculated {done} leave balance period(s)."))
