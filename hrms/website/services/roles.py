"""
Role (Django Group) assignment for an Employee's linked login account.
Single source of truth for the "clear old groups, ensure a linked User
exists, assign one new group" logic that used to be duplicated across
create_or_edit_employee, bulk_employee_action, and create_user_view.
Preserves the existing single-role-per-user invariant those three call
sites all relied on.
"""
from django.contrib.auth.models import User


def assign_employee_role(employee, group):
    """Assign `employee`'s linked User to `group`, replacing any existing
    role. Auto-creates a login User (username = employee_code, unusable
    password) if the employee doesn't have one yet and has an employee_code.
    Returns the User, or None if no employee_code was available to create one."""
    if not employee.user:
        if not employee.employee_code:
            return None
        username = employee.employee_code.lower()
        user, created = User.objects.get_or_create(username=username)
        if created:
            user.set_unusable_password()
            user.save()
        employee.user = user
        employee.save(update_fields=["user"])

    employee.user.groups.clear()
    employee.user.groups.add(group)
    return employee.user
