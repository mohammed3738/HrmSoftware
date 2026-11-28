"""Page hierarchy shared by the header, section directories and breadcrumbs."""
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse

from .templatetags.custom_filters import dashboard_home, has_feature, has_reportees, in_group, is_employee_role


def navigation(request):
    if hasattr(request, "_hrms_navigation"):
        return request._hrms_navigation

    user = request.user
    employee = getattr(user, "employee_profile", None)
    team = has_reportees(user)
    home = dashboard_home(user)
    grants = {}

    def can(permission):
        if permission not in grants:
            grants[permission] = has_feature(user, permission)
        return grants[permission]

    def page(label, route, allowed=True, *, args=(), query="", children=()):
        if allowed:
            return dict(label=label, route=route, url=reverse(route, args=args) + query, children=children)

    def section(key, label, *pages):
        return dict(key=key, label=label, url=reverse("navigation-section", args=[key]),
                    pages=[entry for entry in pages if entry])

    directory = can("employee_records:view")
    sections = [
        section("workspace", "My workspace",
            page("Workforce analytics", "workforce-analytics", can("admin_dashboard:view")),
            page("Executive summary", "executive-dashboard", can("executive_dashboard:view")),
            page("My dashboard", "employee-dashboard", employee),
            page("My Profile", "employee_detail", employee, args=[employee.pk] if employee else []),
            page("My requests", "employee-request-history", args=["leave"],
                 children=("employee-request-record",)),
            page("Announcements", "announcement-feed"),
            page("Change password", "change-password")),
        section("people", "People",
            page("Employee directory", "employee_list", directory, children=("employee_create", "employee_detail", "employee_edit")),
            page("Org chart", "org-chart", employee or directory),
            page("Team dashboard", "team-analytics", team),
            page("My Approvals", "my-approvals", team),
            page("Pending Onboarding", "employee_list", directory, query="?onboarding=pending"),
            page("Profile change requests", "employee_change_requests", directory, children=("employee_change_request_detail",)),
            page("Employee Offboarding", "offboarding-list", can("offboarding:view"))),
        section("attendance", "Attendance",
            page("My Attendance", "employee_attendance_detail", employee, args=[employee.pk] if employee else []),
            page("Field Duty", "field-duty", employee),
            page("Attendance List", "attendance", can("attendance_review:view"), children=("employee_attendance_detail",)),
            page("Correction requests", "attendance_correction_requests_list", children=("attendance_correction_detail",)),
            page("Field Duty Log" if can("field_duty:view") else "My Team's Field Duty", "field-duty-log", team or can("field_duty:view")),
            page("Shift Roster", "shift_roster_list", can("shift_roster:view")),
            page("Attendance Register", "attendance-register", can("attendance_register:view")),
            page("Late Attendance Review", "late_attendance_review", can("attendance_review:edit")),
            page("Upload Attendance (Excel)", "upload_attendance", can("attendance_data:edit")),
            page("Biometric Sync", "biometric-sync", can("attendance_data:edit"))),
        section("leave", "Leave",
            page("Apply for leave", "leave_apply"), page("Leave Balance", "leave_balance", children=("leave_balance_report",)),
            page("Comp-off requests", "comp_off_requests_list", children=("comp_off_requests",)),
            page("Holiday calendar", "holiday-calendar", children=("holiday-dashboard", "earned-leaves")),
            page("Leave Credit Policy", "leave_credit_policy", can("leave_management:edit"))),
        section("payroll", "Payroll",
            page("Salary Slips" if can("payroll:edit") else "My Salary Slips", "salary-slips",
                 employee or can("payroll:edit"), children=("salary-slip", "salary-slip-statement")),
            page("Payroll Run", "payroll-run-list", can("payroll:view"), children=("payroll-run-detail", "payroll-run-create")),
            page("Salary advances", "advances-list", employee or can("advances:view"), children=("advance-detail", "advance-edit", "create-advance")),
            page("Create Salary Structure", "create-salary", can("salary_structure:create")),
            page("Salary Increment", "salary_increment", can("salary_structure:edit")),
            page("Salary History", "salary_history", can("salary_structure:view"), children=("salary_history_detail", "salary_compare"))),
        section("administration", "Administration",
            page("Companies", "create-company", can("company_management:view")),
            page("Branches", "create-branch", can("branch_management:edit")),
            page("Departments", "department-list", can("department_management:view")),
            page("Manage announcements", "announcements-hub", can("announcements:view")),
            page("Company settings", "company-settings-hub", can("company_settings:view") and not is_employee_role(user), children=("settings-page",)),
            page("Roles & Permissions", "roles-permissions-hub", in_group(user, "Super Admin,Admin") and not is_employee_role(user)),
            page("Create user account", "create-user", can("user_accounts:edit")),
            page("Audit Log", "audit-log", can("audit_log:view"))),
    ]
    sections = [group for group in sections if group["pages"]]
    actions = {
        "employee_list": page("Add employee", "employee_create", can("employee_records:create")),
        "payroll-run-list": page("New payroll run", "payroll-run-create", can("payroll:edit")),
        "advances-list": page("New advance", "create-advance", can("advances:edit")),
    }
    for group in sections:
        for entry in group["pages"]:
            if "?" not in entry["url"]:
                entry["action"] = actions.get(entry["route"])
    result = dict(home=home, sections=sections, crumbs=[], section=None)
    request._hrms_navigation = result
    match = request.resolver_match
    if not match or request.path == home:
        return result
    route = match.url_name
    root = dict(label="Home", url=home)
    index = dict(label="All pages", url=reverse("navigation-index"))
    crumbs = result["crumbs"]
    crumbs.extend([root, index])
    if route == "navigation-index":
        return result
    if route == "navigation-section":
        group = next((g for g in sections if g["key"] == match.kwargs["section"]), None)
        result["section"] = group
        if group:
            crumbs.append(group)
        return result

    entries = [(g, p) for g in sections for p in g["pages"]]
    selected = None
    if route == "employee_list" and request.GET.get("onboarding") == "pending":
        selected = next(((g, p) for g, p in entries if p["url"].endswith("?onboarding=pending")), None)
    selected = selected or next(((g, p) for g, p in entries if p["url"] == request.path), None)
    selected = selected or next(((g, p) for g, p in entries if route in p["children"]
                                 or (route == "employee-request-history" and p["route"] == route)), None)
    if selected:
        group, parent = selected
        result["section"] = group
        crumbs.extend([group, parent.copy()])
        if route in ("employee-request-history", "employee-request-record"):
            kind = match.kwargs["kind"]
            label = {"leave": "Leave requests", "comp-off": "Comp-off requests",
                     "correction": "Attendance corrections", "profile": "Profile change requests"}
            crumbs[-1] = dict(label=label.get(kind, "My requests"), url=reverse("employee-request-history", args=[kind]))
        if route == "employee_edit" and directory:
            crumbs.append(dict(label="Employee profile", url=reverse("employee_detail", args=[match.kwargs["employee_id"]])))
        if route == "advance-edit":
            crumbs.append(dict(label="Advance details", url=reverse("advance-detail", args=[match.kwargs["pk"]])))
        if route in parent["children"]:
            crumbs.append(dict(label=DETAIL_LABELS.get(route, "Details")))
    else:
        crumbs.clear()
    return result


DETAIL_LABELS = {
    "employee_create":"Add employee", "employee_detail":"Employee profile", "employee_edit":"Edit employee",
    "employee_change_request_detail":"Change request", "employee-request-record":"Request details",
    "employee_attendance_detail":"Employee attendance", "salary-slip":"Payslip", "salary-slip-statement":"Salary statement",
    "advance-detail":"Advance details", "advance-edit":"Edit advance", "create-advance":"New advance",
    "payroll-run-detail":"Run details", "payroll-run-create":"New payroll run", "salary_history_detail":"Salary details",
    "salary_compare":"Salary comparison", "leave_balance_report":"Balance report", "holiday-dashboard":"Holiday settings",
}


SECTION_ICONS = {
    "workspace": "apps", "people": "group", "attendance": "time",
    "leave": "flight-takeoff", "payroll": "wallet-3", "administration": "settings-3",
}

PAGE_ICONS = {
    "workforce-analytics": "bar-chart-2", "executive-dashboard": "pie-chart", "employee-dashboard": "dashboard",
    "employee_detail": "user", "employee-request-history": "inbox", "announcement-feed": "megaphone",
    "change-password": "lock-password", "employee_list": "contacts", "org-chart": "git-branch",
    "team-analytics": "team", "my-approvals": "checkbox-circle", "employee_change_requests": "user-settings",
    "offboarding-list": "logout-box", "employee_attendance_detail": "time", "field-duty": "map-pin",
    "attendance": "file-list-2", "attendance_correction_requests_list": "edit-box", "field-duty-log": "route",
    "shift_roster_list": "calendar-schedule", "attendance-register": "book-open", "late_attendance_review": "alarm",
    "upload_attendance": "upload-cloud", "biometric-sync": "fingerprint", "leave_apply": "flight-takeoff",
    "leave_balance": "scales-3", "comp_off_requests_list": "exchange", "holiday-calendar": "calendar-event",
    "leave_credit_policy": "file-list-3", "salary-slips": "bill", "payroll-run-list": "calculator",
    "advances-list": "wallet-3", "create-salary": "stack", "salary_increment": "line-chart",
    "salary_history": "history", "create-company": "building", "create-branch": "building-2",
    "department-list": "git-branch", "announcements-hub": "megaphone", "company-settings-hub": "settings-3",
    "roles-permissions-hub": "shield-keyhole", "create-user": "user-add", "audit-log": "file-search",
}


@login_required
def page_directory(request, section=None):
    tree = navigation(request)
    if section and not tree["section"]:
        raise Http404
    for group in tree["sections"]:
        group["icon"] = SECTION_ICONS[group["key"]]
        for page in group["pages"]:
            page["icon"] = PAGE_ICONS.get(page["route"], "file-list-3")
            if page["url"].endswith("?onboarding=pending"):
                page["icon"] = "user-follow"
    return render(request, "navigation/directory.html", {"tree": tree, "section": tree["section"]})
