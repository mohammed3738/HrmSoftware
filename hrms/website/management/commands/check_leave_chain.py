from datetime import timedelta

from django.core.management.base import BaseCommand

from website.models import LeaveBalance


class Command(BaseCommand):
    help = ("List every leave balance whose Opening doesn't equal the previous period's final "
            "Leave Balance. Read-only unless --fix is given.")

    def add_arguments(self, parser):
        parser.add_argument("--fix", action="store_true",
                            help="Recalculate each affected employee from the first broken period onwards "
                                 "(manual Comp Off / LWP edits are kept; finalized payroll periods are skipped).")

    def handle(self, *args, **options):
        from website.signals import recalculate_leave_balance_for_employee
        from website.views import _payroll_settings_with_cycle, get_locking_run_for_period

        broken = {}  # employee -> first broken LeaveBalance
        prev = None
        rows = (LeaveBalance.objects.select_related("employee__company")
                .order_by("employee_id", "period_from_date"))
        for lb in rows.iterator():
            if prev and prev.employee_id == lb.employee_id \
                    and prev.period_to_date + timedelta(days=1) == lb.period_from_date \
                    and lb.opening_balance != prev.final_leave_balance:
                ps = _payroll_settings_with_cycle(lb.employee.company)
                is_reset = ps and not getattr(ps, "carry_forward", True) \
                    and getattr(ps, "reset_month", None) == lb.period_to_date.month and lb.opening_balance == 0
                if not is_reset:
                    locked = get_locking_run_for_period(lb.employee.company, lb.period_from_date, lb.period_to_date)
                    self.stdout.write(
                        f"{lb.employee.employee_code} {lb.employee.first_name} {lb.employee.last_name}: "
                        f"{prev.period_from_date:%d %b} - {prev.period_to_date:%d %b %Y} closed at {prev.final_leave_balance}, "
                        f"next period opens at {lb.opening_balance}"
                        + ("  [next period's payroll is finalized - not auto-fixable]" if locked else "")
                    )
                    broken.setdefault(lb.employee, lb)
            prev = lb

        self.stdout.write(f"{len(broken)} employee(s) with a broken carry-forward.")
        if options["fix"] and broken:
            for employee, lb in broken.items():
                recalculate_leave_balance_for_employee(employee, lb.period_from_date)
            self.stdout.write("Recalculated. Run again without --fix to confirm.")
