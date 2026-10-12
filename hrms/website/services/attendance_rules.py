"""Re-applying attendance rules to days already recorded.

A finalized payroll run freezes the attendance behind it: payslips have
gone out, so a later rules change (weekend days, a bug fix) must not
rewrite those days. Everything outside a finalized run follows the
current rules as soon as it's recalculated.
"""
from django.db import transaction
from django.db.models import Q

from ..models import Attendance, PayrollRun


def finalized_q(company=None):
    """Q matching attendance inside any finalized payroll run (optionally
    only runs that apply to `company`). Matches nothing when there are
    no finalized runs."""
    locked = Q(pk__in=[])
    runs = PayrollRun.objects.filter(status=PayrollRun.STATUS_FINALIZED)
    for run in runs:
        if company is not None and run.company_id not in (None, company.pk):
            continue
        q = Q(date__gte=run.start_date, date__lte=run.end_date)
        if run.company_id:
            q &= Q(employee__company_id=run.company_id)
        locked |= q
    return locked


def exclude_finalized(qs, company=None):
    return qs.exclude(finalized_q(company))


def reapply_weekend_rule(company):
    """After a company's weekend setting changes: recalculate every
    Saturday and every day currently marked Weekend for its employees,
    except days inside a finalized payroll run, then refresh that
    company's draft payroll runs covering those days.

    Returns {"updated": days whose status changed, "locked": days left
    alone in finalized payroll, "runs": draft runs refreshed}."""
    from ..signals import suspend_leave_balance_auto_recalc
    from . import recalculate_payroll_run

    affected = Attendance.objects.filter(employee__company=company).filter(
        Q(date__week_day=7) | Q(status="Weekend"),  # week_day: 1=Sunday ... 7=Saturday
    ).select_related("employee", "employee__company", "employee__branch")
    locked = affected.filter(finalized_q(company)).count()
    rows = list(exclude_finalized(affected, company).order_by("date"))

    changed = []
    with transaction.atomic(), suspend_leave_balance_auto_recalc():
        for attendance in rows:
            before = attendance.status
            attendance.save()  # Attendance.save() recalculates status/count
            if attendance.status != before:
                changed.append(attendance)

    runs = 0
    if changed:
        first, last = changed[0].date, changed[-1].date
        for run in PayrollRun.objects.filter(
            company=company, status=PayrollRun.STATUS_DRAFT, start_date__lte=last, end_date__gte=first,
        ):
            recalculate_payroll_run(run)
            runs += 1
    return {"updated": len(changed), "locked": locked, "runs": runs}
