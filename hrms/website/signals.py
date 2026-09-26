from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import *
from django.db.models import Sum
from dateutil.relativedelta import relativedelta
from datetime import date, timedelta
from django.db.models.signals import post_delete
from django.db.models import Q

from decimal import Decimal

def D(val):
    return Decimal(str(val or "0"))


# -----------------------------------------------------------------------
# Auto-recalculate LeaveBalance whenever Attendance changes
# -----------------------------------------------------------------------
# The Leave Balance report used to require someone to click "Recalculate"
# after every attendance upload/correction/override -- easy to forget, and
# the numbers would silently go stale until someone remembered. This makes
# it automatic: any Attendance create/update/delete recalculates that one
# employee's affected payroll period(s), reusing the exact same
# calculate_leave_balance_for_period() the manual "Recalculate" button
# already calls, so the numbers always match what that button would have
# produced.
import threading

_recalc_suspend_state = threading.local()


class suspend_leave_balance_auto_recalc:
    """Context manager for bulk Attendance writers (Excel import, the
    "Recalculate Attendance" status-refresh chunk endpoint): hundreds of
    .save() calls for the same handful of employees would otherwise each
    recompute that employee's leave balance from scratch. Wrap the bulk
    loop in this, then call recalculate_leave_balance_for_employee() once
    per distinct employee touched, after the loop -- see its use in
    website/views.py (_process_attendance_rows, recalculate_attendance_chunk)."""

    def __enter__(self):
        _recalc_suspend_state.depth = getattr(_recalc_suspend_state, "depth", 0) + 1
        return self

    def __exit__(self, *exc_info):
        _recalc_suspend_state.depth -= 1


def _auto_recalc_suspended():
    return getattr(_recalc_suspend_state, "depth", 0) > 0


def recalculate_leave_balance_for_employee(employee, from_date):
    """Recalculate one employee's LeaveBalance for the payroll period
    containing from_date, and every later period known to have attendance
    -- a change to an old period must also refresh every later period's
    carried-forward opening balance, not just the one that changed.
    Finalized payroll periods are left alone: those numbers are what
    payslips were already computed from."""
    from website.views import (
        calculate_leave_balance_for_period,
        get_all_payroll_periods_from_attendance,
        get_payroll_period_for_date,
        get_locking_run_for_period,
    )

    if not employee.company_id:
        return
    payroll_settings = PayrollSettings.objects.filter(company_id=employee.company_id).first()
    if not payroll_settings:
        return

    period_start, period_end = get_payroll_period_for_date(payroll_settings, from_date)
    # get_all_payroll_periods_from_attendance only returns periods that
    # currently HAVE an attendance row, so a delete that empties the
    # affected period out entirely would otherwise never get recalculated
    # (the stale LeaveBalance row would just be left standing) -- the
    # directly-affected period is always included explicitly below.
    later_periods = [
        p for p in get_all_payroll_periods_from_attendance(employee.company, payroll_settings)
        if p["from_date"] > period_start
    ]
    periods_to_recalc = sorted(
        [{"from_date": period_start, "to_date": period_end}] + later_periods,
        key=lambda p: p["from_date"],
    )

    for period in periods_to_recalc:
        if get_locking_run_for_period(employee.company, period["from_date"], period["to_date"]):
            continue
        try:
            calculate_leave_balance_for_period(employee, payroll_settings, period["from_date"], period["to_date"])
        except Exception:
            pass


@receiver(post_save, sender=Attendance)
def auto_recalc_leave_balance_on_attendance_save(sender, instance, **kwargs):
    if _auto_recalc_suspended():
        return
    recalculate_leave_balance_for_employee(instance.employee, instance.date)


@receiver(post_delete, sender=Attendance)
def auto_recalc_leave_balance_on_attendance_delete(sender, instance, **kwargs):
    if _auto_recalc_suspended():
        return
    recalculate_leave_balance_for_employee(instance.employee, instance.date)


# calculate_leave_balance_for_period reads approved CompOffRequests directly
# (not via Attendance), so approving/rejecting/deleting one also needs to
# retrigger the recalc -- otherwise the Comp Off column only updates on the
# next unrelated attendance change for that employee.
@receiver(post_save, sender=CompOffRequest)
def auto_recalc_leave_balance_on_compoff_save(sender, instance, **kwargs):
    if _auto_recalc_suspended() or not instance.from_date:
        return
    recalculate_leave_balance_for_employee(instance.employee, instance.from_date)


@receiver(post_delete, sender=CompOffRequest)
def auto_recalc_leave_balance_on_compoff_delete(sender, instance, **kwargs):
    if _auto_recalc_suspended() or not instance.from_date:
        return
    recalculate_leave_balance_for_employee(instance.employee, instance.from_date)


@receiver(post_save, sender=Offboarding)
def update_status_in_model_a(sender, instance, created, **kwargs):
    if created:  # Only update when a new ModelB instance is created
        print('working')
        model_a_instance = instance.employee  # Get related ModelA instance
        model_a_instance.status = 'Pending'  # Change status value
        model_a_instance.save()  # Save the ModelA instance with the new status



@receiver(post_delete, sender=Offboarding)
def revert_status_in_model_a(sender, instance, **kwargs):
    model_a_instance = instance.employee  # Get related ModelA instance
    model_a_instance.status = 'Active'  # Revert status value
    model_a_instance.save()  # Save the ModelA instance with the reverted status

# from django.db.models.signals import post_save
# from django.dispatch import receiver
# from .models import Employee, LeaveBalance

# @receiver(post_save, sender=Employee)
# def create_leave_balance(sender, instance, created, **kwargs):
#     """Automatically create a leave balance record when an employee is created."""
#     if created:
#         LeaveBalance.objects.create(employee=instance)  # Default 10 leaves






from django.db.models import Sum
from django.utils.timezone import now
from datetime import date








# -----------------------
# Helper utilities
# -----------------------
# def _to_date(d):
#     """Ensure 'd' is a date object (not datetime)."""
#     if d is None:
#         return None
#     if hasattr(d, "date"):
#         return d.date()
#     return d


# -----------------------
# 1) Create a LeaveBalance for new employees (initialized to zero)
# -----------------------
# @receiver(post_save, sender=Employee)
# def create_leave_balance(sender, instance, created, **kwargs):
#     if created:
#         LeaveBalance.objects.create(
#             employee=instance,
#             opening_balance=Decimal("0.00"),
#             leave_taken=Decimal("0.00"),
#             number_of_days_present=Decimal("0.00"),
#             total_number_of_days=0,
#             late=0,
#             compoff=0.0,
#             leave_without_pay=Decimal("0.00"),
#             closing_balance=Decimal("0.00"),
#             leave_balance=Decimal("0.00"),
#             final_leave_balance=Decimal("0.00"),
#         )
#         print(f"[signals] Initialized LeaveBalance = 0 for {instance.first_name}")













# signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User, Group
# from .models import Employee

@receiver(post_save, sender=Employee)
def sync_user(sender, instance, created, **kwargs):
    if created and not instance.user:
        username = instance.employee_code
        # A username collision here means an unrelated account already
        # owns that exact username (e.g. a leftover/orphaned login) --
        # auto-linking the new employee to someone else's account would be
        # a real data/security mixup, not a minor glitch, so this skips
        # provisioning rather than guessing. HR can finish it by hand via
        # the existing Create User page, which already handles "no user
        # yet" as a normal state.
        if username and not User.objects.filter(username=username).exists():
            user = User.objects.create_user(
                username=username,
                email=instance.personal_email,
                first_name=instance.first_name,
                last_name=instance.last_name,
                password="Temp@123"
            )
            # Give every auto-provisioned login a baseline role immediately --
            # without this, the account has no group at all until someone
            # separately assigns one via the employee form, and in the
            # meantime login_view's fallback sends them to admin-dashboard,
            # which they have no permission for -> 403 on first login. HR can
            # still upgrade them to HR/Admin/Manager later as usual.
            employee_group, _ = Group.objects.get_or_create(name="Employee")
            user.groups.add(employee_group)
            instance.user = user
            instance.force_password_change = True
            instance.save()

    if instance.status == "Left" and instance.user:
        instance.user.is_active = False
        instance.user.save()




@receiver(post_save, sender=PayrollSettings)
def generate_monthly_earned_leaves(sender, instance, created, **kwargs):
    """
    Auto-generate monthly earned leaves whenever PayrollSettings
    is created or updated.
    """

    MonthlyEarnedLeaves.generate_for_payroll_settings(instance)
