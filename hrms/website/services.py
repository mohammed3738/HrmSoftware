from datetime import date, timedelta
from calendar import monthrange
from django.db import transaction
from django.utils import timezone
from .models import AdvanceMaster, AdvanceSchedule, AdvancePayment, Employee
import math

def add_months(src_date, months):
    # simple add months preserving day = 1 for due_month
    y = src_date.year + (src_date.month - 1 + months) // 12
    m = (src_date.month - 1 + months) % 12 + 1
    d = 1
    return date(y, m, d)

def distribute_integer_rupees(total, parts):
    """Return list of length parts that sums to total, distributing remainder to earliest items."""
    if parts <= 0:
        return []
    base = total // parts
    rem = total - base * parts
    out = [base + (1 if i < rem else 0) for i in range(parts)]
    return out

@transaction.atomic
def create_advance(employee, amount_rupees, months, start_date=None):
    """Create AdvanceMaster and initial schedule."""
    if start_date is None:
        start_date = date.today().replace(day=1)
    adv = AdvanceMaster.objects.create(
        employee=employee,
        advance_amount=amount_rupees,
        default_months=months,
        outstanding_amount=amount_rupees,
        start_date=start_date
    )
    # initial even split
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
    """
    Recompute future scheduled amounts from a start index (0 = first pending schedule).
    Logic: take outstanding amount and remaining pending non-skipped schedule count.
    If none remaining, create one schedule with outstanding.
    """
    schedules = list(advance.schedules.order_by('due_month'))
    # filter pending schedules
    pending = [s for s in schedules if s.status == AdvanceSchedule.STATUS_PENDING]
    if not pending:
        # create one final schedule if outstanding exists
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
    # if outstanding is zero, mark pending schedules with 0 scheduled_amount?
    if outstanding <= 0:
        for s in pending:
            s.scheduled_amount = 0
            s.paid_amount = 0
            s.status = AdvanceSchedule.STATUS_PAID
            s.save()
        advance.status = AdvanceMaster.STATUS_COMPLETED
        advance.save()
        return

    # distribute outstanding rupees over remaining_count
    new_amounts = distribute_integer_rupees(outstanding, remaining_count)
    for s, amt in zip(pending, new_amounts):
        s.scheduled_amount = amt
        # paid_amount should remain as is if previously partially paid (rare for pending)
        # Ensure if paid_amount >= scheduled_amount, mark paid
        if s.paid_amount >= amt:
            s.status = AdvanceSchedule.STATUS_PAID
            s.paid_amount = amt
        else:
            s.status = AdvanceSchedule.STATUS_PENDING
        s.save()

    # if outstanding fully distributed to fewer months than scheduled, remove extra zero schedules
    # (not necessary; handled by recompute when pending list is empty)
    advance.save()

@transaction.atomic
def apply_payment(advance: AdvanceMaster, amount: int, payment_date=None, note=''):
    """
    Apply an actual payment amount to the advance.
    Strategy:
      - Reduce outstanding by amount
      - Walk schedules in chronological order and apply paid_amount to earliest pending/skipped? pending only
      - After applying, recompute the future schedule to evenly distribute outstanding across remaining pending months.
      - If outstanding becomes 0 -> mark advance completed.
    """
    if payment_date is None:
        payment_date = timezone.now()

    AdvancePayment.objects.create(advance=advance, amount=amount, date=payment_date, note=note)
    advance.outstanding_amount = max(0, advance.outstanding_amount - amount)
    advance.save()

    # apply to earliest pending schedules
    schedules = list(advance.schedules.order_by('due_month'))
    remaining_payment = amount
    for s in schedules:
        if remaining_payment <= 0:
            break
        if s.status == AdvanceSchedule.STATUS_PAID:
            continue
        # if skipped, do not accept payment into it (we keep skip as 0 scheduled)
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

    # If any remaining payment left (could be overpay), it's already subtracted from outstanding.
    # Now recompute future schedule so outstanding is distributed evenly over remaining pending months
    recompute_future_schedule(advance)

    # If outstanding is zero, mark finished
    if advance.outstanding_amount == 0:
        advance.status = AdvanceMaster.STATUS_COMPLETED
        # set all pending as paid (in case some small rounding issues)
        for s in advance.schedules.filter(status=AdvanceSchedule.STATUS_PENDING):
            s.status = AdvanceSchedule.STATUS_PAID
            s.paid_amount = s.scheduled_amount
            s.save()
        advance.save()

@transaction.atomic
def skip_month(advance: AdvanceMaster, due_month_date):
    """
    Mark the schedule of due_month_date as skipped.
    Implementation:
      - find schedule with that due_month (first day of month)
      - mark as skipped and set scheduled_amount = 0 (paid_amount remains 0)
      - append a new schedule at the end to preserve the original number of pending months (tenure++). 
      - After skip, recompute future schedule distribution.
    """
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

    # append a new pending schedule at the end (next month after last schedule)
    last_schedule = advance.schedules.order_by('due_month').last()
    next_month = add_months(last_schedule.due_month, 1)
    AdvanceSchedule.objects.create(
        advance=advance,
        due_month=next_month,
        scheduled_amount=0  # will be filled by recompute
    )

    # now recompute distribution for pending months
    recompute_future_schedule(advance)




def revert_skip(advance: AdvanceMaster, due_month: date):
    """
    Reverts a skipped EMI month and recalculates schedule.
    """

    schedule = advance.schedules.filter(due_month=due_month).first()
    if not schedule:
        raise ValueError("Schedule not found")

    if schedule.status != "skipped":
        raise ValueError("This EMI is not skipped and cannot be reverted")

    # 1. Restore this EMI month
    schedule.status = "pending"

    # assign a temporary amount (it will be recalculated anyway)
    schedule.scheduled_amount = 0
    schedule.save()

    # 2. Remove the extra last EMI added due to skip
    # Find last schedule that is still pending or zero
    extra_month = advance.schedules.order_by('-due_month').first()
    if extra_month and extra_month.status == "pending" and extra_month.paid_amount == 0:
        extra_month.delete()

    # 3. Recalculate EMI schedule across remaining pending months
    pending = advance.schedules.filter(status="pending").order_by('due_month')
    remaining_count = pending.count()

    outstanding = advance.outstanding_amount

    # Distribute amount evenly
    base = outstanding // remaining_count
    remainder = outstanding % remaining_count

    for idx, emi in enumerate(pending):
        emi.scheduled_amount = base + (1 if idx < remainder else 0)
        emi.save()

    advance.save()
    return advance





# services.py
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from .models import PayrollRun, PayrollRecord, SalaryMaster, Attendance, AdvanceSchedule, PayrollSettings, Employee
from django.db.models import Sum

def money_d(v):
    return Decimal(v or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def get_attendance_summary(employee, start_date, end_date):
    total_days = (end_date - start_date).days + 1
    qs = Attendance.objects.filter(employee=employee, date__range=[start_date, end_date])
    present_sum = qs.aggregate(total=Sum("count"))["total"] or Decimal("0.00")
    leave_taken = Decimal(total_days) - Decimal(present_sum)
    return {"total_days": int(total_days), "present_days": money_d(present_sum), "leave_taken": money_d(max(Decimal(0), leave_taken))}

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
    run = PayrollRun.objects.create(company=company, month=month_start.replace(day=1), start_date=month_start, end_date=month_end)
    if create_records:
        generate_records_for_month(run)
    return run

def generate_records_for_month(run: PayrollRun):
    settings = PayrollSettings.objects.filter(company=run.company).first()
    employees = Employee.objects.filter(company=run.company, status="Active")
    for emp in employees:
        salary = SalaryMaster.objects.filter(employee=emp, is_active=True).first()
        if not salary:
            continue
        att = get_attendance_summary(emp, run.start_date, run.end_date)
        advance_amt = get_advance_for_employee_month(emp, run.start_date, run.end_date)

        rec = PayrollRecord.objects.create(
            payroll=run,
            employee=emp,
            employee_code=emp.employee_code,
            employee_name=f"{emp.first_name} {emp.last_name}",
            company_name=emp.company.name if emp.company else "",
            designation=emp.designation,
            branch_name=emp.branch.branch_name if emp.branch else "",
            date_of_joining=emp.date_of_joining,
            month_display=run.month.strftime("%b %Y"),

            gross_ctc=money_d(salary.gross_ctc_pm),
            opted_for_pf=bool(salary.pf_deducted),
            basic_pm=money_d(salary.basic_pm),
            hra_pm=money_d(salary.hra_pm),
            sp_allowance_pm=money_d(salary.sp_allowance_pm),
            stat_bonus_pm=money_d(salary.stat_bonus_pm),
            allowance1_pm=money_d(salary.allowance1_pm),
            allowance2_pm=money_d(salary.allowance2_pm),
            pf_employer=money_d(salary.pf_er_cont_pm if hasattr(salary, "pf_er_cont_pm") else getattr(salary, "pf_er_cont_pa", 0)),
            esic_employer=money_d(salary.esic_er_cont_pm if hasattr(salary, "esic_er_cont_pm") else getattr(salary, "esic_er_cont_pa", 0)),
            total_gross_salary=money_d(salary.gross_ctc_pm),

            total_days=att["total_days"],
            present_days=att["present_days"],
            leave_taken=att["leave_taken"],
            leave_adjust=money_d(0),
            percent_adjusted=money_d(0),

            advance=advance_amt
        )

        # do initial authoritative calc
        recalc_and_save_record(rec, manual_overrides={})

def calculate_pro_rata(component_pm, present_days, total_days):
    if total_days <= 0:
        return Decimal("0.00")
    factor = Decimal(present_days) / Decimal(total_days)
    return money_d(Decimal(component_pm) * factor)

def calculate_and_populate_record(record: PayrollRecord, payroll_run: PayrollRun, payroll_settings: PayrollSettings = None, manual_overrides: dict = None):
    if payroll_settings is None:
        payroll_settings = PayrollSettings.objects.filter(company=payroll_run.company).first()

    TD = Decimal(record.total_days or 0)
    PD = Decimal(record.present_days or 0)
    # Option B: leave_adjust increases present_days and decreases leave_taken
    LA = Decimal(record.leave_adjust or 0)
    # Bound leave_adjust: cannot exceed existing leave_taken, cannot make present > total
    LA = max(Decimal(0), min(LA, Decimal(record.leave_taken or 0), TD - PD))
    PD_adj = PD + LA
    leave_taken_adj = max(Decimal(0), Decimal(record.leave_taken or 0) - LA)
    percent_adjusted = (PD_adj / TD * 100) if TD > 0 else Decimal(0)

    basic_proc = calculate_pro_rata(record.basic_pm, PD_adj, TD)
    hra_proc = calculate_pro_rata(record.hra_pm, PD_adj, TD)
    sp_proc = calculate_pro_rata(record.sp_allowance_pm, PD_adj, TD)
    stat_proc = calculate_pro_rata(record.stat_bonus_pm, PD_adj, TD)
    a1_proc = calculate_pro_rata(record.allowance1_pm, PD_adj, TD)
    a2_proc = calculate_pro_rata(record.allowance2_pm, PD_adj, TD)

    gross_proc = money_d(basic_proc + hra_proc + sp_proc + stat_proc + a1_proc + a2_proc)

    # PF calc (employee side) - prefer manual override if passed, else compute
    pf_emp = Decimal(0)
    if record.opted_for_pf:
        pf_percentage = Decimal(getattr(payroll_settings, "pf_percentage", 12) or 12)
        basic_cap = Decimal(getattr(payroll_settings, "basic_cap", 9999999))
        pf_base = min(basic_proc, basic_cap)
        pf_emp = money_d(pf_base * (pf_percentage / Decimal(100)))

    # ESIC calc (employee)
    esic_emp = Decimal(0)
    esic_percentage = Decimal(getattr(payroll_settings, "esic_percentage", 0) or 0)
    esic_threshold = Decimal(getattr(payroll_settings, "esic_threshold", 21000))
    guaranteed_cash = gross_proc
    if record.esic_employer and guaranteed_cash <= esic_threshold:
        esic_emp = money_d(guaranteed_cash * (esic_percentage / Decimal(100)))

    # Gratuity (if required)
    gratuity = Decimal(0)
    gratuity_percentage = Decimal(getattr(payroll_settings, "gratuity_percentage", 0) or 0)
    # if needed, compute gratuity on basic_proc
    gratuity = money_d(basic_proc * (gratuity_percentage / Decimal(100))) if getattr(record, "gratuity_applicable", False) else Decimal(0)

    # professional tax default
    prof_tax = Decimal(getattr(payroll_settings, "professional_tax", 0) or 0)

    # apply manual overrides if provided
    if manual_overrides:
        pf_emp = money_d(Decimal(manual_overrides.get("pf_employee", pf_emp)))
        esic_emp = money_d(Decimal(manual_overrides.get("esic_employee", esic_emp)))
        prof_tax = money_d(Decimal(manual_overrides.get("professional_tax", prof_tax)))
        tds = money_d(Decimal(manual_overrides.get("tds", record.tds or 0)))
        advance = money_d(Decimal(manual_overrides.get("advance", record.advance or 0)))
        other_ded = money_d(Decimal(manual_overrides.get("other_deductions", record.other_deductions or 0)))
    else:
        tds = money_d(record.tds or 0)
        advance = money_d(record.advance or 0)
        other_ded = money_d(record.other_deductions or 0)

    total_ded = money_d(pf_emp + esic_emp + prof_tax + tds + advance + other_ded)
    net_pay = money_d(gross_proc - total_ded)

    breakdown = {
        "attendance": {"TD": int(TD), "PD_adj": float(PD_adj), "LA": float(LA), "leave_taken_adj": float(leave_taken_adj)},
        "components": {
            "basic_processed": float(basic_proc),
            "hra_processed": float(hra_proc),
            "sp_processed": float(sp_proc),
            "stat_processed": float(stat_proc),
            "a1_processed": float(a1_proc),
            "a2_processed": float(a2_proc),
            "gross_processed": float(gross_proc)
        },
        "deductions": {
            "pf_employee": float(pf_emp),
            "esic_employee": float(esic_emp),
            "professional_tax": float(prof_tax),
            "tds": float(tds),
            "advance": float(advance),
            "other": float(other_ded),
            "total": float(total_ded)
        },
        "net_pay": float(net_pay),
        "gratuity": float(gratuity)
    }

    return {
        "basic_processed": basic_proc,
        "hra_processed": hra_proc,
        "sp_allowance_processed": sp_proc,
        "stat_bonus_processed": stat_proc,
        "allowance1_processed": a1_proc,
        "allowance2_processed": a2_proc,
        "gross_processed": gross_proc,
        "pf_employee": pf_emp,
        "esic_employee": esic_emp,
        "professional_tax": prof_tax,
        "tds": tds,
        "advance": advance,
        "other_deductions": other_ded,
        "total_deductions": total_ded,
        "net_salary": net_pay,
        "pf_employer": record.pf_employer,
        "esic_employer": record.esic_employer,
        "percent_adjusted": money_d(percent_adjusted),
        "present_days_adj": money_d(PD_adj),
        "leave_taken_adj": money_d(leave_taken_adj),
        "breakdown": breakdown
    }

@transaction.atomic
def recalc_and_save_record(record: PayrollRecord, manual_overrides: dict = None):
    run = record.payroll
    settings = PayrollSettings.objects.filter(company=run.company).first()
    # Bound leave_adjust value in record before calculation (Option B)
    record.leave_adjust = money_d(max(Decimal(0), min(record.leave_adjust, record.leave_taken)))
    result = calculate_and_populate_record(record, run, settings, manual_overrides)
    # apply to record and save
    for field in ["basic_processed","hra_processed","sp_allowance_processed","stat_bonus_processed",
                  "allowance1_processed","allowance2_processed","gross_processed",
                  "pf_employee","esic_employee","professional_tax","tds","advance","other_deductions",
                  "total_deductions","net_salary","pf_employer","esic_employer","percent_adjusted"]:
        if field in result:
            setattr(record, field, result[field])
    # update present/leave adjusted values
    record.present_days = result.get("present_days_adj", record.present_days)
    record.leave_taken = result.get("leave_taken_adj", record.leave_taken)
    record.percent_adjusted = result.get("percent_adjusted", record.percent_adjusted)
    # store breakdown
    record.calculation_breakdown = result.get("breakdown", {})
    # store manual overrides
    if manual_overrides:
        record.manual_override.update(manual_overrides)
    record.save()
    return record
