from datetime import date, timedelta
from calendar import monthrange
from django.db import transaction
from django.utils import timezone
from ..models import AdvanceMaster, AdvanceSchedule, AdvancePayment, Employee
import math

def add_months(src_date, months):
    y = src_date.year + (src_date.month - 1 + months) // 12
    m = (src_date.month - 1 + months) % 12 + 1
    d = 1
    return date(y, m, d)

def distribute_integer_rupees(total, parts):
    if parts <= 0:
        return []
    base = total // parts
    rem = total - base * parts
    out = [base + (1 if i < rem else 0) for i in range(parts)]
    return out

@transaction.atomic
def create_advance(employee, amount_rupees, months, start_date=None):
    if start_date is None:
        start_date = date.today().replace(day=1)
    adv = AdvanceMaster.objects.create(
        employee=employee,
        advance_amount=amount_rupees,
        default_months=months,
        outstanding_amount=amount_rupees,
        start_date=start_date
    )
    parts = distribute_integer_rupees(amount_rupees, months)
    for i, amt in enumerate(parts):
        due = add_months(start_date, i)
        AdvanceSchedule.objects.create(
            advance=adv,
            due_month=due,
            scheduled_amount=amt
        )
    return adv

def recompute_future_schedule(advance, start_from_index=0):
    schedules = list(advance.schedules.order_by('due_month'))
    pending = [s for s in schedules if s.status == AdvanceSchedule.STATUS_PENDING]
    if not pending:
        if advance.outstanding_amount > 0:
            due = add_months(advance.start_date, len(schedules))
            AdvanceSchedule.objects.create(
                advance=advance,
                due_month=due,
                scheduled_amount=advance.outstanding_amount
            )
        return

    remaining_count = len(pending)
    outstanding = advance.outstanding_amount
    if outstanding <= 0:
        for s in pending:
            s.scheduled_amount = 0
            s.paid_amount = 0
            s.status = AdvanceSchedule.STATUS_PAID
            s.save()
        advance.status = AdvanceMaster.STATUS_COMPLETED
        advance.save()
        return

    new_amounts = distribute_integer_rupees(outstanding, remaining_count)
    for s, amt in zip(pending, new_amounts):
        s.scheduled_amount = amt
        if s.paid_amount >= amt:
            s.status = AdvanceSchedule.STATUS_PAID
            s.paid_amount = amt
        else:
            s.status = AdvanceSchedule.STATUS_PENDING
        s.save()

    advance.save()

@transaction.atomic
def apply_payment(advance: AdvanceMaster, amount: int, payment_date=None, note=''):
    if payment_date is None:
        payment_date = timezone.now()

    AdvancePayment.objects.create(advance=advance, amount=amount, date=payment_date, note=note)
    advance.outstanding_amount = max(0, advance.outstanding_amount - amount)
    advance.save()

    schedules = list(advance.schedules.order_by('due_month'))
    remaining_payment = amount
    for s in schedules:
        if remaining_payment <= 0:
            break
        if s.status == AdvanceSchedule.STATUS_PAID:
            continue
        if s.status == AdvanceSchedule.STATUS_SKIPPED:
            continue
        need = s.scheduled_amount - s.paid_amount
        if need <= 0:
            s.status = AdvanceSchedule.STATUS_PAID
            s.save()
            continue
        apply_amt = min(need, remaining_payment)
        s.paid_amount += apply_amt
        remaining_payment -= apply_amt
        if s.paid_amount >= s.scheduled_amount:
            s.status = AdvanceSchedule.STATUS_PAID
        s.save()

    recompute_future_schedule(advance)

    if advance.outstanding_amount == 0:
        advance.status = AdvanceMaster.STATUS_COMPLETED
        for s in advance.schedules.filter(status=AdvanceSchedule.STATUS_PENDING):
            s.status = AdvanceSchedule.STATUS_PAID
            s.paid_amount = s.scheduled_amount
            s.save()
        advance.save()

@transaction.atomic
def skip_month(advance: AdvanceMaster, due_month_date):
    try:
        sched = advance.schedules.get(due_month=due_month_date)
    except AdvanceSchedule.DoesNotExist:
        raise ValueError("Schedule not found for that month")

    if sched.status == AdvanceSchedule.STATUS_PAID:
        raise ValueError("Cannot skip a paid month")

    sched.status = AdvanceSchedule.STATUS_SKIPPED
    sched.scheduled_amount = 0
    sched.paid_amount = 0
    sched.save()

    last_schedule = advance.schedules.order_by('due_month').last()
    next_month = add_months(last_schedule.due_month, 1)
    AdvanceSchedule.objects.create(
        advance=advance,
        due_month=next_month,
        scheduled_amount=0
    )

    recompute_future_schedule(advance)


def revert_skip(advance: AdvanceMaster, due_month: date):
    schedule = advance.schedules.filter(due_month=due_month).first()
    if not schedule:
        raise ValueError("Schedule not found")

    if schedule.status != "skipped":
        raise ValueError("This EMI is not skipped and cannot be reverted")

    schedule.status = "pending"
    schedule.scheduled_amount = 0
    schedule.save()

    extra_month = advance.schedules.order_by('-due_month').first()
    if extra_month and extra_month.status == "pending" and extra_month.paid_amount == 0:
        extra_month.delete()

    pending = advance.schedules.filter(status="pending").order_by('due_month')
    remaining_count = pending.count()
    outstanding = advance.outstanding_amount

    base = outstanding // remaining_count
    remainder = outstanding % remaining_count

    for idx, emi in enumerate(pending):
        emi.scheduled_amount = base + (1 if idx < remainder else 0)
        emi.save()

    advance.save()
    return advance


# ── Payroll services ──────────────────────────────────────────────────────────

from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Sum
from ..models import PayrollRun, PayrollRecord, SalaryMaster, Attendance, PayrollSettings, LeaveBalance


def money_d(v):
    return Decimal(v or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_attendance_summary(employee, start_date, end_date):
    total_days = (end_date - start_date).days + 1
    qs = Attendance.objects.filter(employee=employee, date__range=[start_date, end_date])
    present_sum = qs.aggregate(total=Sum("count"))["total"] or Decimal("0.00")
    leave_taken = Decimal(total_days) - Decimal(present_sum)
    return {
        "total_days": int(total_days),
        "present_days": money_d(present_sum),
        "leave_taken": money_d(max(Decimal(0), leave_taken))
    }


def get_advance_for_employee_month(employee, start_date, end_date):
    emi = AdvanceSchedule.objects.filter(
        advance__employee=employee,
        due_month__range=[start_date, end_date],
        status=AdvanceSchedule.STATUS_PENDING
    ).first()
    if emi:
        return money_d(emi.scheduled_amount)
    return money_d(0)


@transaction.atomic
def create_payroll_run(company, month_start, month_end, create_records=True):
    run = PayrollRun.objects.create(
        company=company,
        month=month_start.replace(day=1),
        start_date=month_start,
        end_date=month_end
    )
    if create_records:
        generate_records_for_month(run)
    return run


def _build_record_snapshot(emp, salary, run):
    """Everything a PayrollRecord pulls from source data (employee master,
    salary master, attendance, leave balance, advance schedule) as of right
    now for this run's period. Shared by generate_records_for_month (first
    creation) and recalculate_payroll_run (refresh before finalizing)."""
    att = get_attendance_summary(emp, run.start_date, run.end_date)
    advance_amt = get_advance_for_employee_month(emp, run.start_date, run.end_date)

    # Get LeaveBalance for this specific payroll period
    lb = (
        LeaveBalance.objects.filter(employee=emp, period_to_date=run.end_date).first()
        or LeaveBalance.objects.filter(
            employee=emp,
            period_from_date__lte=run.end_date,
            period_to_date__gte=run.start_date,
            period_to_date__isnull=False
        ).order_by('-period_to_date').first()
    )
    lwop = money_d(lb.leave_without_pay) if lb else money_d(0)

    first = emp.first_name or ""
    last = emp.last_name or ""
    full_name = f"{first} {last}".strip() or emp.employee_code or "Unknown"

    return {
        "employee_code": emp.employee_code or "",
        "employee_name": full_name,
        "company_name": emp.company.name if emp.company else "",
        "designation": emp.designation or "",
        "branch_name": emp.branch.branch_name if emp.branch else "",
        "date_of_joining": emp.date_of_joining,
        "month_display": run.month.strftime("%b %Y"),

        "gross_ctc": money_d(salary.gross_ctc_pm or 0),
        "opted_for_pf": bool(salary.pf_deducted),
        "basic_pm": money_d(salary.basic_pm or 0),
        "hra_pm": money_d(salary.hra_pm or 0),
        "sp_allowance_pm": money_d(salary.sp_allowance_pm or 0),
        "stat_bonus_pm": money_d(salary.stat_bonus_pm or 0),
        "allowance1_pm": money_d(salary.allowance1_pm or 0),
        "allowance2_pm": money_d(salary.allowance2_pm or 0),
        "total_gross_salary": money_d(salary.gross_ctc_pm or 0),

        "total_days": att["total_days"],
        "present_days": att["present_days"],
        "leave_taken": att["leave_taken"],
        "leave_without_pay": lwop,

        "advance": advance_amt,
    }


def generate_records_for_month(run: PayrollRun):
    employees = Employee.objects.filter(company=run.company, status="Active")
    for emp in employees:
        salary = SalaryMaster.objects.filter(employee=emp, is_active=True).first()
        if not salary:
            continue
        rec = PayrollRecord.objects.create(payroll=run, employee=emp, **_build_record_snapshot(emp, salary, run))
        recalc_and_save_record(rec, manual_overrides={})


@transaction.atomic
def recalculate_payroll_run(run: PayrollRun):
    """Refresh every record in a draft payroll run from current attendance,
    leave, advance and salary master data, then recompute PF/ESIC/deductions
    and net pay. Use this before finalizing to pick up attendance
    corrections, leave approvals, advance changes, or payroll-settings
    updates made after the run was first generated.

    Fields a user already manually overrode on a record (via the per-record
    edit modal) are preserved rather than clobbered by the refresh. Active
    employees with a salary who aren't in the run yet (e.g. hired after it
    was first generated) get a new record added. Existing records for
    employees who are no longer Active, or who no longer have an active
    SalaryMaster, are left untouched rather than refreshed or removed.
    """
    existing = {r.employee_id: r for r in run.records.all()}
    active_employee_ids = set()
    refreshed = added = 0

    employees = Employee.objects.filter(company=run.company, status="Active")
    for emp in employees:
        salary = SalaryMaster.objects.filter(employee=emp, is_active=True).first()
        if not salary:
            continue
        active_employee_ids.add(emp.id)
        snapshot = _build_record_snapshot(emp, salary, run)

        rec = existing.get(emp.id)
        if rec is None:
            rec = PayrollRecord(payroll=run, employee=emp)
            added += 1
        else:
            refreshed += 1

        manual = rec.manual_override or {}
        for field, value in snapshot.items():
            if field in manual:
                continue  # a manually-edited field (e.g. advance) wins over the refreshed value
            setattr(rec, field, value)
        rec.save()

        recalc_and_save_record(rec, manual_overrides=manual)

    skipped = sum(1 for emp_id in existing if emp_id not in active_employee_ids)
    return {"refreshed": refreshed, "added": added, "skipped": skipped}


def calculate_pro_rata(component_pm, total_days, leave_without_pay):
    total_days = Decimal(total_days or 0)
    leave_without_pay = Decimal(leave_without_pay or 0)
    if total_days <= 0:
        return Decimal("0.00")
    payable_days = total_days - leave_without_pay
    if payable_days <= 0:
        return Decimal("0.00")
    factor = payable_days / total_days
    return money_d(Decimal(component_pm) * factor)


def calculate_and_populate_record(record: PayrollRecord, payroll_run: PayrollRun, payroll_settings: PayrollSettings = None, manual_overrides: dict = None):
    if payroll_settings is None:
        payroll_settings = PayrollSettings.objects.filter(company=payroll_run.company).first()

    TD = Decimal(record.total_days or 0)
    LWP = Decimal(record.leave_without_pay or 0)

    basic_proc = calculate_pro_rata(record.basic_pm, TD, LWP)
    hra_proc   = calculate_pro_rata(record.hra_pm, TD, LWP)
    sp_proc    = calculate_pro_rata(record.sp_allowance_pm, TD, LWP)
    stat_proc  = calculate_pro_rata(record.stat_bonus_pm, TD, LWP)
    a1_proc    = calculate_pro_rata(record.allowance1_pm, TD, LWP)
    a2_proc    = calculate_pro_rata(record.allowance2_pm, TD, LWP)
    gross_proc = money_d(basic_proc + hra_proc + sp_proc + stat_proc + a1_proc + a2_proc)

    pf_emp = Decimal(0)
    if record.opted_for_pf:
        pf_percentage = Decimal(getattr(payroll_settings, "pf_percentage", 12) or 12)
        # basic_cap caps the Basic component during salary structuring, not
        # PF — the statutory PF wage ceiling is a separate, smaller figure
        # (pf_wage_ceiling, default 15000) so PF matches what the salary
        # structure editor shows (e.g. 15000 x 12% = 1800), not basic_cap.
        pf_wage_ceiling = Decimal(str(getattr(payroll_settings, "pf_wage_ceiling", None) or 15000))
        # PF = 12% of the basic actually earned this period (pro-rated for
        # LWP), capped at the flat statutory contribution (ceiling x pf%,
        # e.g. 15000 x 12% = 1800). So a small LWP for a high earner still
        # leaves PF at the flat cap — only once LWP is heavy enough that
        # even their full earned basic's 12% drops below the flat cap does
        # PF start coming down below it.
        pf_flat_cap = money_d(pf_wage_ceiling * (pf_percentage / Decimal(100)))
        pf_emp = min(money_d(basic_proc * (pf_percentage / Decimal(100))), pf_flat_cap)

    esic_emp = Decimal(0)
    esic_percentage = Decimal(getattr(payroll_settings, "esic_percentage", 0) or 0)
    esic_threshold = Decimal(getattr(payroll_settings, "esic_threshold", 21000))
    if gross_proc <= esic_threshold:
        esic_emp = money_d(gross_proc * (esic_percentage / Decimal(100)))

    prof_tax = Decimal(getattr(payroll_settings, "professional_tax", 0) or 0)

    if manual_overrides:
        pf_emp   = money_d(Decimal(manual_overrides.get("pf_employee", pf_emp)))
        esic_emp = money_d(Decimal(manual_overrides.get("esic_employee", esic_emp)))
        prof_tax = money_d(Decimal(manual_overrides.get("professional_tax", prof_tax)))
        tds      = money_d(Decimal(manual_overrides.get("tds", record.tds or 0)))
        advance  = money_d(Decimal(manual_overrides.get("advance", record.advance or 0)))
        other_ded = money_d(Decimal(manual_overrides.get("other_deductions", record.other_deductions or 0)))
    else:
        tds       = money_d(record.tds or 0)
        advance   = money_d(record.advance or 0)
        other_ded = money_d(record.other_deductions or 0)

    total_ded = money_d(pf_emp + esic_emp + prof_tax + tds + advance + other_ded)
    net_pay   = money_d(gross_proc - total_ded)

    breakdown = {
        "attendance": {"TD": int(TD), "LWP": float(LWP)},
        "components": {
            "basic_processed": float(basic_proc), "hra_processed": float(hra_proc),
            "sp_processed": float(sp_proc), "stat_processed": float(stat_proc),
            "a1_processed": float(a1_proc), "a2_processed": float(a2_proc),
            "gross_processed": float(gross_proc)
        },
        "deductions": {
            "pf_employee": float(pf_emp), "esic_employee": float(esic_emp),
            "professional_tax": float(prof_tax), "tds": float(tds),
            "advance": float(advance), "other": float(other_ded), "total": float(total_ded)
        },
        "net_pay": float(net_pay)
    }

    return {
        "basic_processed": basic_proc, "hra_processed": hra_proc,
        "sp_allowance_processed": sp_proc, "stat_bonus_processed": stat_proc,
        "allowance1_processed": a1_proc, "allowance2_processed": a2_proc,
        "gross_processed": gross_proc,
        "pf_employee": pf_emp, "esic_employee": esic_emp,
        "professional_tax": prof_tax, "tds": tds, "advance": advance,
        "other_deductions": other_ded, "total_deductions": total_ded,
        "net_salary": net_pay,
        "percent_adjusted": money_d((TD - LWP) / TD * 100) if TD > 0 else money_d(0),
        "present_days_adj": record.present_days,
        "leave_taken_adj": record.leave_taken,
        "breakdown": breakdown
    }


@transaction.atomic
def recalc_and_save_record(record: PayrollRecord, manual_overrides: dict = None):
    run = record.payroll
    settings = PayrollSettings.objects.filter(company=run.company).first()
    record.leave_without_pay = money_d(max(Decimal(0), record.leave_without_pay))
    result = calculate_and_populate_record(record, run, settings, manual_overrides)
    for field in [
        "basic_processed", "hra_processed", "sp_allowance_processed", "stat_bonus_processed",
        "allowance1_processed", "allowance2_processed", "gross_processed",
        "pf_employee", "esic_employee", "professional_tax", "tds", "advance", "other_deductions",
        "total_deductions", "net_salary", "percent_adjusted"
    ]:
        if field in result:
            setattr(record, field, result[field])
    record.calculation_breakdown = result.get("breakdown", {})
    if manual_overrides:
        record.manual_override.update(manual_overrides)
    record.save()
    return record
