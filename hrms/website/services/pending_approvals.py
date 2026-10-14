"""Approvals that must be decided before a company's payroll for a period
can be created or finalized.

Anything still pending would change the numbers once decided -- a leave
or comp-off changes leave/LWP, an attendance correction changes paid days,
an employee change can change bank, company or status -- so payroll waits
until each one is approved or rejected.
"""
from django.db.models import Q
from django.urls import reverse

from ..models import (
    AttendanceCorrectionRequest, CompOffRequest, EmployeeChangeRequest, LeaveApplication,
)


def pending_approvals_for_payroll(company, start_date, end_date):
    """[{"label", "count", "url"}] for each kind of approval still pending
    for `company`'s employees in [start_date, end_date]; empty when payroll
    may proceed."""
    in_company = Q(employee__company=company)
    overlaps = Q(start_date__lte=end_date, end_date__gte=start_date)
    checks = [
        ("leave application",
         LeaveApplication.objects.filter(in_company, overlaps, status="Pending"),
         reverse("admin-dashboard")),
        ("comp-off request",
         CompOffRequest.objects.filter(in_company, status="Pending",
                                       from_date__lte=end_date, to_date__gte=start_date),
         reverse("comp_off_requests_list")),
        ("attendance correction",
         AttendanceCorrectionRequest.objects.filter(
             attendance__employee__company=company, status="Pending",
             attendance__date__gte=start_date, attendance__date__lte=end_date),
         reverse("attendance_correction_requests_list")),
        ("employee change request",
         EmployeeChangeRequest.objects.filter(in_company, status=EmployeeChangeRequest.STATUS_PENDING),
         reverse("employee_change_requests")),
    ]
    pending = []
    for label, qs, url in checks:
        count = qs.count()
        if count:
            pending.append({"label": label + ("s" if count != 1 else ""), "count": count, "url": url})
    return pending


def pending_approvals_message(company, start_date, end_date, pending):
    """One sentence for a refusal: "Payroll for X (1 Mar – 31 Mar) can't
    proceed until these are approved or rejected: 2 leave applications, ..."."""
    items = ", ".join(f"{p['count']} {p['label']}" for p in pending)
    return (f"Payroll for {company} ({start_date:%d %b} – {end_date:%d %b %Y}) can't proceed until these are "
            f"approved or rejected: {items}.")
