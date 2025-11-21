from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import *
from django.db.models import Sum
from dateutil.relativedelta import relativedelta
from datetime import date, timedelta
from django.db.models.signals import post_delete
from django.db.models import Q

from decimal import Decimal


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
def _to_date(d):
    """Ensure 'd' is a date object (not datetime)."""
    if d is None:
        return None
    if hasattr(d, "date"):
        return d.date()
    return d

def _inclusive_days(start, end):
    """Return inclusive days between two date-like objects (end >= start)."""
    start = _to_date(start)
    end = _to_date(end)
    if not start or not end:
        return 0
    return max(0, (end - start).days + 1)

def _payroll_period_for(employee, ref_date):
    """Return (from_date, to_date) using PayrollSettings if available, else calendar month."""
    payroll_settings = PayrollSettings.objects.filter(company=employee.company).first()
    if payroll_settings:
        return payroll_settings.get_payroll_period()
    first = ref_date.replace(day=1)
    next_month = first.replace(day=28) + timedelta(days=4)
    last = next_month - timedelta(days=next_month.day)
    return first, last

# -----------------------
# 1) Create a LeaveBalance for new employees (initialized to zero)
# -----------------------
@receiver(post_save, sender=Employee)
def create_leave_balance(sender, instance, created, **kwargs):
    if created:
        LeaveBalance.objects.create(
            employee=instance,
            opening_balance=Decimal("0.00"),
            leave_taken=Decimal("0.00"),
            number_of_days_present=Decimal("0.00"),
            total_number_of_days=0,
            late=0,
            compoff=0.0,
            leave_without_pay=Decimal("0.00"),
            closing_balance=Decimal("0.00"),
            leave_balance=Decimal("0.00"),
            final_leave_balance=Decimal("0.00"),
        )
        print(f"[signals] Initialized LeaveBalance = 0 for {instance.first_name}")

# -----------------------
# 2) Recalculate leave balance whenever an Attendance record is saved
# -----------------------
@receiver(post_save, sender=Attendance)
def update_leave_balance_on_attendance(sender, instance, created, **kwargs):
    """
    Recalculate leave balance for the employee of the attendance record.
    Uses instance.date as the "current" date so testing with historic/future attendance works.
    """
    employee = instance.employee
    leave_record, _ = LeaveBalance.objects.get_or_create(employee=employee)

    # Use attendance date (helps when uploading ranges); fallback to today.
    today = _to_date(getattr(instance, "date", None)) or date.today()

    # Payroll period
    period_start, period_end = _payroll_period_for(employee, today)

    # Aggregate attendance and late
    total_present = Attendance.objects.filter(
        employee=employee,
        date__gte=period_start,
        date__lte=today
    ).aggregate(total_present=Sum("count"))["total_present"] or 0

    total_late = Attendance.objects.filter(
        employee=employee,
        date__gte=period_start,
        date__lte=today
    ).aggregate(total_late=Sum("late"))["total_late"] or 0

    total_present = Decimal(total_present)
    total_late = Decimal(total_late)

    # total days in current payroll period up to today (inclusive)
    total_days_till_now = Decimal((today - period_start).days + 1)

    # leaves taken in this period (days not present)
    leave_taken_till_now = total_days_till_now - total_present

    # Opening balance: carry forward from previous month's leave_balance (not closing_balance)
    # If this is the first day of the payroll period, opening is 0 for new cycle.
    if today == period_start:
        opening_balance = Decimal("0.00")
    else:
        opening_balance = Decimal(leave_record.leave_balance or Decimal("0.00"))

    # -------------------------
    # Compute approved comp-off days that overlap WITHIN the current payroll period (up to 'today')
    # This handles requests that may start before period_start or end after today.
    # -------------------------
    compoff_qs = CompOffRequest.objects.filter(
        employee=employee,
        status="Approved"
    )

    comp_off_days = Decimal(0)
    for comp in compoff_qs:
        comp_start = _to_date(comp.from_date)
        comp_end = _to_date(comp.to_date)
        if not comp_start or not comp_end:
            continue

        # intersect [comp_start, comp_end] with [period_start, today]
        inter_start = max(comp_start, period_start)
        inter_end = min(comp_end, today)
        if inter_end >= inter_start:
            comp_off_days += Decimal((inter_end - inter_start).days + 1)

    # -------------------------
    # Formula: closing_balance = opening - leave_taken - late + compoff
    # If closing_balance < 0 => leave_without_pay = abs(closing_balance), leave_balance = 0
    # Else leave_balance = closing_balance and leave_without_pay = 0
    # Then final_leave_balance = leave_balance + monthly_credit (monthly credit logic below)
    # -------------------------
    closing_balance = opening_balance - leave_taken_till_now - total_late + comp_off_days

    if closing_balance < 0:
        leave_without_pay = abs(closing_balance)
        leave_balance_val = Decimal("0.00")
    else:
        leave_without_pay = Decimal("0.00")
        leave_balance_val = closing_balance

    # -------------------------
    # Monthly credit policy:
    # Defaults: credit_low=0 (<= credit_1_limit), credit_mid=1, credit_high=2
    # Thresholds default credit_1_limit=15, credit_2_limit=25
    # You can supply a LeaveCreditPolicy for company to override these.
    # -------------------------
    credit_1_limit = 15
    credit_2_limit = 25
    credit_low = Decimal("0")
    credit_mid = Decimal("1")
    credit_high = Decimal("2")

    try:
        policy = LeaveCreditPolicy.objects.filter(company=employee.company).first()
        if policy:
            credit_1_limit = int(policy.credit_1_limit)
            credit_2_limit = int(policy.credit_2_limit)
            credit_low = Decimal(policy.credit_low)
            credit_mid = Decimal(policy.credit_mid)
            credit_high = Decimal(policy.credit_high)
    except Exception:
        # if LeaveCreditPolicy model missing or broken, keep defaults
        pass

    # Decide monthly credit based on days present (total_present)
    if total_present <= credit_1_limit:
        monthly_credit = credit_low
    elif credit_1_limit < total_present <= credit_2_limit:
        monthly_credit = credit_mid
    else:
        monthly_credit = credit_high

    final_leave_balance = leave_balance_val + monthly_credit

    # -------------------------
    # Save everything (use Decimal -> model types carefully)
    # -------------------------
    leave_record.opening_balance = opening_balance
    leave_record.leave_taken = leave_taken_till_now
    leave_record.number_of_days_present = total_present
    leave_record.total_number_of_days = int(total_days_till_now)
    leave_record.late = int(total_late)
    leave_record.leave_without_pay = leave_without_pay
    leave_record.closing_balance = closing_balance
    leave_record.leave_balance = leave_balance_val
    leave_record.final_leave_balance = final_leave_balance
    # model field compoff is FloatField in your schema: store as float
    leave_record.compoff = float(comp_off_days)
    leave_record.save()

    print(
        f"[signals] Updated leave for {employee.first_name}: "
        f"OB={opening_balance} Present={total_present} LT={leave_taken_till_now} "
        f"Late={total_late} CO={comp_off_days} CB={closing_balance} "
        f"LWP={leave_without_pay} LB={leave_balance_val} Final={final_leave_balance}"
    )

# -----------------------
# 3) When a CompOffRequest is created/approved -> recalc employee's compoff & leave
# -----------------------
@receiver(post_save, sender=CompOffRequest)
def update_leave_balance_on_compoff(sender, instance, created, **kwargs):
    """
    Recalculate compoff total for the employee (within payroll period) and
    then trigger an attendance-based recalculation (by calling the same logic).
    """
    employee = instance.employee
    # Only act on approved requests
    if instance.status != "Approved":
        return

    # Recalculate compoff total for the current payroll period
    today = date.today()
    period_start, period_end = _payroll_period_for(employee, today)

    compoff_qs = CompOffRequest.objects.filter(
        employee=employee,
        status="Approved",
    )

    total_compoff = Decimal(0)
    for comp in compoff_qs:
        comp_start = _to_date(comp.from_date)
        comp_end = _to_date(comp.to_date)
        if not comp_start or not comp_end:
            continue
        inter_start = max(comp_start, period_start)
        inter_end = min(comp_end, period_end)
        if inter_end >= inter_start:
            total_compoff += Decimal((inter_end - inter_start).days + 1)

    leave_record, _ = LeaveBalance.objects.get_or_create(employee=employee)
    leave_record.compoff = float(total_compoff)
    leave_record.save(update_fields=["compoff"])
    print(f"[signals] CompOff saved for {employee.first_name}: {total_compoff} days")

    # Also trigger a full recalc (use a dummy Attendance instance-like approach)
    # Simpler: call update_leave_balance_on_attendance using most-recent Attendance for employee if exists
    last_att = Attendance.objects.filter(employee=employee).order_by("-date").first()
    if last_att:
        update_leave_balance_on_attendance(Attendance, last_att, created=False)

# -----------------------
# 4) When a CompOffRequest is deleted -> recalc totals
# -----------------------
@receiver(post_delete, sender=CompOffRequest)
def recalc_compoff_on_delete(sender, instance, **kwargs):
    employee = instance.employee
    today = date.today()
    period_start, period_end = _payroll_period_for(employee, today)

    compoff_qs = CompOffRequest.objects.filter(
        employee=employee,
        status="Approved",
    )

    total_compoff = Decimal(0)
    for comp in compoff_qs:
        comp_start = _to_date(comp.from_date)
        comp_end = _to_date(comp.to_date)
        if not comp_start or not comp_end:
            continue
        inter_start = max(comp_start, period_start)
        inter_end = min(comp_end, period_end)
        if inter_end >= inter_start:
            total_compoff += Decimal((inter_end - inter_start).days + 1)

    leave_record, _ = LeaveBalance.objects.get_or_create(employee=employee)
    leave_record.compoff = float(total_compoff)
    leave_record.save(update_fields=["compoff"])
    print(f"[signals] CompOff recalculated after delete for {employee.first_name}: {total_compoff} days")

    # re-run attendance-based recalc if attendance exists
    last_att = Attendance.objects.filter(employee=employee).order_by("-date").first()
    if last_att:
        update_leave_balance_on_attendance(Attendance, last_att, created=False)

# -----------------------
# 5) Monthly reset helper (call this from management command / cron)
# -----------------------
def reset_monthly_leave_balances():
    """
    - Should be run on 1st of month via cron.
    - Saves LeaveBalanceHistory snapshot and carries forward closing balance.
    - Skips new joiners (who joined in this payroll month).
    """
    today = date.today()
    if today.day != 1:
        print("[signals] reset_monthly_leave_balances: skipped (not 1st of month)")
        return

    current_month_str = today.strftime("%B %Y")
    print(f"[signals] Running monthly reset for {current_month_str}...")

    all_records = LeaveBalance.objects.select_related("employee").all()
    for rec in all_records:
        emp = rec.employee
        payroll_start, payroll_end = _payroll_period_for(emp, today)

        # skip new joiners who joined inside this payroll period
        join_date = getattr(emp, "date_of_joining", None)
        if join_date and _to_date(join_date) >= payroll_start:
            print(f"[signals] Skipping new joiner {emp.first_name} (joined {join_date})")
            continue

        # save history
        LeaveBalanceHistory.objects.create(
            employee=emp,
            month=current_month_str,
            opening_balance=Decimal(rec.opening_balance or 0),
            days_present=Decimal(rec.number_of_days_present or 0),
            leave_taken=Decimal(rec.leave_taken or 0),
            late=int(rec.late or 0),
            compoff=Decimal(rec.compoff or 0),
            leave_without_pay=Decimal(rec.leave_without_pay or 0),
            closing_balance=Decimal(rec.closing_balance or 0),
            final_leave_balance=Decimal(rec.final_leave_balance or rec.leave_balance or 0),
        )

        # carry forward closing -> opening; reset monthly fields
        new_opening = Decimal(rec.closing_balance or 0)
        rec.opening_balance = new_opening
        rec.leave_taken = Decimal("0.00")
        rec.number_of_days_present = Decimal("0.00")
        rec.total_number_of_days = 0
        rec.late = 0
        rec.compoff = 0.0
        rec.leave_without_pay = Decimal("0.00")
        rec.closing_balance = new_opening
        rec.leave_balance = new_opening
        rec.final_leave_balance = new_opening
        rec.save(update_fields=[
            "opening_balance", "leave_taken", "number_of_days_present", "total_number_of_days",
            "late", "compoff", "leave_without_pay", "closing_balance", "leave_balance", "final_leave_balance"
        ])
        print(f"[signals] Reset done for {emp.first_name}, new opening: {new_opening}")

    print("[signals] Monthly reset finished.")




def recalculate_leave_balance_for_employee(employee):
    """
    Manual trigger to recalculate leave balance for an employee.
    EXACT SAME LOGIC as update_leave_balance_on_attendance signal.
    """
    from .models import Attendance, LeaveBalance, LeaveCreditPolicy, PayrollSettings, CompOffRequest
    from decimal import Decimal
    from datetime import date, timedelta
    from dateutil.relativedelta import relativedelta

    leave_record, _ = LeaveBalance.objects.get_or_create(employee=employee)

    # Use "today" as NOW
    today = date.today()

    # Payroll period
    payroll_settings = PayrollSettings.objects.filter(company=employee.company).first()
    if payroll_settings:
        period_start, period_end = payroll_settings.get_payroll_period()
    else:
        period_start = today.replace(day=1)
        next_month = (today.replace(day=1) + relativedelta(months=1))
        period_end = next_month - timedelta(days=next_month.day)

    # Attendance
    total_present = Attendance.objects.filter(
        employee=employee, date__gte=period_start, date__lte=today
    ).aggregate(total_present=Sum("count"))["total_present"] or 0

    total_late = Attendance.objects.filter(
        employee=employee, date__gte=period_start, date__lte=today
    ).aggregate(total_late=Sum("late"))["total_late"] or 0

    total_present = Decimal(total_present)
    total_late = Decimal(total_late)
    total_days = Decimal((today - period_start).days + 1)
    leave_taken = total_days - total_present

    # Opening balance
    if today == period_start:
        opening = Decimal("0.00")
    else:
        opening = Decimal(leave_record.leave_balance)

    # Compoff (overlapping period)
    compoff_days = Decimal(0)
    comp_requests = CompOffRequest.objects.filter(employee=employee, status="Approved")
    for comp in comp_requests:
        start = comp.from_date
        end = comp.to_date
        overlap_start = max(start, period_start)
        overlap_end = min(end, today)
        if overlap_end >= overlap_start:
            compoff_days += Decimal((overlap_end - overlap_start).days + 1)

    # Formula
    closing = opening - leave_taken - total_late + compoff_days

    if closing < 0:
        lwp = abs(closing)
        leave_balance_val = Decimal("0.00")
    else:
        lwp = Decimal("0.00")
        leave_balance_val = closing

    # Monthly credit (same logic)
    credit_1_limit, credit_2_limit = 15, 25
    credit_low, credit_mid, credit_high = Decimal("0"), Decimal("1"), Decimal("2")

    policy = LeaveCreditPolicy.objects.filter(company=employee.company).first()
    if policy:
        credit_1_limit = policy.credit_1_limit
        credit_2_limit = policy.credit_2_limit
        credit_low = Decimal(policy.credit_low)
        credit_mid = Decimal(policy.credit_mid)
        credit_high = Decimal(policy.credit_high)

    if total_present <= credit_1_limit:
        monthly_credit = credit_low
    elif total_present <= credit_2_limit:
        monthly_credit = credit_mid
    else:
        monthly_credit = credit_high

    final = leave_balance_val + monthly_credit

    # SAVE
    leave_record.opening_balance = opening
    leave_record.leave_taken = leave_taken
    leave_record.number_of_days_present = total_present
    leave_record.total_number_of_days = int(total_days)
    leave_record.late = int(total_late)
    leave_record.leave_without_pay = lwp
    leave_record.closing_balance = closing
    leave_record.leave_balance = leave_balance_val
    leave_record.final_leave_balance = final
    leave_record.compoff = float(compoff_days)
    leave_record.save()

    print(f"[MANUAL RECALC] {employee.first_name}: Final = {final}")
