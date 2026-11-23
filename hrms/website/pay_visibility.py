"""
TEMPORARY (Nov 2026): salary structure, salary slips and advances are shown
to Admin / Super Admin only -- hidden from employees, HR, HOD and Payroll
Officer everywhere: menus, dashboards, the employee details page, and the
pages themselves (opening one by address gives 403).

Switched by PAY_ADMIN_ONLY in .env (default on). To undo, set
PAY_ADMIN_ONLY=false and restart; everything returns to the normal
per-role permissions.
"""
from django.conf import settings

PAY_ADMIN_ROLES = ("Super Admin", "Admin")

# Every page / endpoint that shows salary structure, salary slips or advances.
PAY_URL_NAMES = frozenset({
    # salary structure
    "create-salary", "salary-master-export-excel", "salary_details",
    "salary_increment", "salary-increment-export-excel", "edit_increment",
    "update_increment", "delete_increment", "increment_details",
    "salary_history", "employee_details_ajax", "salary_history_detail",
    "salary_compare", "salary_timeline_data", "salary_history_export_excel",
    "import-salary", "salary-import-template",
    # salary slips
    "salary-slip", "salary-slips", "salary-slip-statement",
    # advances
    "advances-list", "create-advance", "advance-detail", "advance-edit",
    "advance-delete", "advances-pay", "advances-skip", "revert-skip",
})


def pay_admin_only():
    return getattr(settings, "PAY_ADMIN_ONLY", False)


def can_see_pay(user):
    """False only while the switch is on and the user isn't Admin / Super
    Admin. True otherwise -- the normal permission checks still apply."""
    if not pay_admin_only():
        return True
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=PAY_ADMIN_ROLES).exists()
