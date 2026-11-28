"""Aggregate workforce reporting for the dashboards. Scope precedes every filter."""
import calendar
from datetime import date

from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from openpyxl import Workbook
from dateutil.relativedelta import relativedelta
from django.shortcuts import render
from django.utils import timezone

from .models import (AdvanceMaster, Attendance, AttendanceCorrectionRequest, Company, Employee, FieldDuty,
                     LeaveApplication, LeaveBalance, Offboarding, PayrollRecord, PayrollRun)
from .utils.permissions import has_feature_permission


def reporting_tree(employee):
    seen = {employee.pk}
    frontier = {employee.pk}
    while frontier:
        linked = Employee.objects.filter(Q(manager_id__in=frontier) | Q(reporting_person_id__in=frontier))
        frontier = set(linked.values_list("pk", flat=True)) - seen
        seen.update(frontier)
    return Employee.objects.filter(pk__in=seen - {employee.pk})


def dashboard_report(request, audience):
    from .views import get_company_filter, user_has_global_access

    user = request.user
    people = Employee.objects.all()
    if audience == "team":
        employee = getattr(user, "employee_profile", None)
        if employee is None:
            raise PermissionDenied
        people = reporting_tree(employee)
        if not people.exists():
            raise PermissionDenied
    elif audience == "operations":
        company = get_company_filter(user)
        if company:
            people = people.filter(company=company)
        elif not user_has_global_access(user):
            people = people.none()

    companies = Company.objects.filter(pk__in=people.values("company_id")).order_by("name")
    company_id = request.GET.get("company", "")
    if company_id:
        if not company_id.isascii() or not company_id.isdecimal() or len(company_id) > 19:
            raise PermissionDenied
        people = people.filter(company_id=int(company_id))
    branches = people.exclude(branch__isnull=True).order_by("branch__branch_name").values_list("branch_id", "branch__branch_name").distinct()
    branch = request.GET.get("branch", "")
    if branch:
        if not branch.isascii() or not branch.isdecimal() or len(branch) > 19:
            raise PermissionDenied
        people = people.filter(branch_id=int(branch))
    departments = people.exclude(department__isnull=True).exclude(department="").order_by("department").values_list("department", flat=True).distinct()
    department = request.GET.get("department", "")
    if department:
        people = people.filter(department=department)

    today = timezone.localdate()
    try:
        first = date.fromisoformat(request.GET.get("month", "") + "-01")
    except ValueError:
        first = today.replace(day=1)
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
    active = people.filter(status="Active")
    payroll_access = audience == "executive" or audience == "operations" and (
        user.is_staff or user.is_superuser or has_feature_permission(user, "payroll", "view")
    )
    def allowed(feature):
        return audience in ("team", "executive") or user.is_staff or user.is_superuser or has_feature_permission(user, feature, "view")

    exits = Offboarding.objects.filter(employee__in=people, is_active=True)
    metrics = [
        ("Active employees today", active.count()),
        ("Joined in period", people.filter(date_of_joining__range=(first, min(today, last))).count()),
        ("Exits in period", exits.filter(date_of_relieving__range=(first, min(today, last))).values("employee_id").distinct().count()),
    ]
    sections = []
    sections.append(("Current workforce", list(people.values_list("status").annotate(n=Count("pk")).order_by("status"))))
    trend_start = max(first, date(1, 6, 1)) - relativedelta(months=5)
    hires = dict(people.filter(date_of_joining__range=(trend_start, min(today, last))).annotate(
        bucket=TruncMonth("date_of_joining")).values_list("bucket").annotate(n=Count("pk")).order_by("bucket"))
    periods = [trend_start + relativedelta(months=i) for i in range(6)]
    sections.append(("New hires · six months", [(month.strftime("%b %Y"), hires.get(month, 0)) for month in periods if month <= today]))
    if audience != "team":
        sections.append(("Current headcount by company", list(active.values_list("company__name").annotate(n=Count("pk")).order_by("-n"))))
    if audience == "team":
        metrics.append(("Direct reports today", active.filter(Q(manager=employee) | Q(reporting_person=employee)).count()))

    for heading, field in (("Current headcount by department", "department"), ("Current headcount by branch", "branch__branch_name"), ("Current headcount by designation", "designation")):
        distribution = active.values(field).annotate(n=Count("pk")).order_by("-n", field)
        sections.append((heading, [(row[field] or "Unassigned", row["n"]) for row in distribution]))
    if allowed("attendance_review"):
        att = Attendance.objects.filter(employee__in=people, date__range=(first, last))
        distribution = att.values("status").annotate(n=Count("pk")).order_by("-n", "status")
        sections.append(("Attendance records this month", [(row["status"], row["n"]) for row in distribution]))
        scheduled = att.exclude(status__in=("Weekend", "Holiday"))
        marked = scheduled.count()
        if marked:
            attended = scheduled.filter(status__in=("Present", "Late Present", "Half Day", "Present (Half-Day)")).count()
            metrics.append(("Present among marked workdays", f"{attended / marked:.0%}"))
        sections.append(("Attendance exceptions", [
            ("Missing checkout", att.filter(in_time__isnull=False, out_time__isnull=True, date__lt=today).count()),
            ("Pending corrections for this period", AttendanceCorrectionRequest.objects.filter(attendance__in=att, status="Pending").count()),
        ]))
        metrics.append(("Field visits", FieldDuty.objects.filter(employee__in=people, duty_date__range=(first, last)).count()))
    if allowed("leave_management"):
        requests = LeaveApplication.objects.filter(employee__in=people, start_date__lte=last, end_date__gte=first)
        sections.append(("Leave requests covering this period", list(requests.values_list("status").annotate(n=Count("pk")).order_by("status"))))
        ledger = LeaveBalance.objects.filter(employee__in=people, period_to_date__range=(first, last))
        sections.append(("Leave by department · days used", [(row["employee__department"] or "Unassigned", row["used"]) for row in ledger.values("employee__department").annotate(used=Sum("leave_taken")).order_by("-used")]))
    if payroll_access:
        pay = PayrollRecord.objects.filter(employee__in=people, payroll__status=PayrollRun.STATUS_FINALIZED)
        if audience == "operations" and company:
            pay = pay.filter(payroll__company=company)
        if company_id:
            pay = pay.filter(payroll__company_id=int(company_id))
        gross_history = pay.filter(payroll__month__range=(trend_start, last)).values("payroll__month").annotate(
            gross=Sum("gross_processed")
        ).order_by("payroll__month")
        sections.append(("Finalized gross payroll by month · INR", [
            (row["payroll__month"].strftime("%b %Y"), row["gross"]) for row in gross_history
        ]))
        pay = pay.filter(payroll__month__range=(first, last))
        payment_counts = pay.filter(net_salary__gt=0).aggregate(
            confirmed=Count("pk", filter=Q(payment_date__isnull=False)),
            awaiting=Count("pk", filter=Q(payment_date__isnull=True)),
        )
        sections.append(("Salary payment confirmations", [
            ("Confirmed payslips", payment_counts["confirmed"]),
            ("Awaiting confirmation", payment_counts["awaiting"]),
        ]))
        branch_costs = pay.values("branch_name").annotate(gross=Sum("gross_processed")).order_by("-gross")
        sections.append(("Finalized gross by payroll branch · INR", [
            (row["branch_name"] or "Unassigned", row["gross"]) for row in branch_costs
        ]))
        totals = pay.aggregate(gross=Sum("gross_processed"), deductions=Sum("total_deductions"), net=Sum("net_salary"))
        sections.append(("Finalized payroll · INR", [(label, totals[key] or 0) for label,key in (("Processed gross","gross"),("Deductions","deductions"),("Net payable","net"))] if totals["net"] is not None else []))
        if allowed("advances"):
            outstanding = AdvanceMaster.objects.filter(employee__in=people, status="active").aggregate(amount=Sum("outstanding_amount"))
            metrics.append(("Advances outstanding today · INR", outstanding["amount"] or 0))
        if totals["gross"] is not None:
            paid = pay.values("employee_id").distinct().count()
            metrics.append(("Processed gross per paid employee · INR", round(totals["gross"] / paid, 2)))
    title = {"team":"Team analytics","operations":"Workforce analytics","executive":"Executive dashboard"}[audience]
    if audience == "team":
        title = "Department dashboard" if user.groups.filter(name="HOD").exists() else "Manager dashboard"
    if request.GET.get("export") == "xlsx":
        book = Workbook()
        sheet = book.active
        sheet.title = "Dashboard"
        sheet.append([title, first.strftime("%B %Y")])
        for heading, entries in [("Summary", metrics), *sections]:
            sheet.append([heading])
            for label, value in entries:
                sheet.append([label, value])
                # Labels can contain company-entered free text.
                sheet.cell(sheet.max_row, 1).data_type = "s"
        sheet.column_dimensions["A"].width = 47
        sheet.column_dimensions["B"].width = 24
        response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="dashboard-{first:%Y-%m}.xlsx"'
        book.save(response)
        return response
    return render(request, "dashboard/analytics.html", {
        "report_title": title, "companies": companies, "company_id": company_id, "departments": departments,
        "branch": branch, "branches": branches, "audience": audience, "hires_peak": max(hires.values(), default=1),
        "department": department, "month": first.strftime("%Y-%m"), "metrics": metrics, "sections": sections,
    })
