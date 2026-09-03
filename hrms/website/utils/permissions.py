from django.core.exceptions import PermissionDenied
from django.db.models import Q

def is_admin(user):
    return user.groups.filter(name="Admin").exists()

def is_hr(user):
    return user.groups.filter(name="HR").exists()

def is_manager(user):
    return user.groups.filter(name="Manager").exists()

def is_employee(user):
    return user.groups.filter(name="Employee").exists()

def admin_or_hr(user):
    return is_admin(user) or is_hr(user)


def has_feature_permission(user, feature_key, action="view"):
    """Does any of this user's roles (Django Groups) grant `action` access
    to the feature identified by `feature_key`? Backs @feature_required.
    See website/permissions_registry.py for the full feature list and the
    seed data this is checked against."""
    from website.models import RoleFeaturePermission
    return RoleFeaturePermission.objects.filter(
        role__in=user.groups.all(), feature__key=feature_key, **{f"can_{action}": True}
    ).exists()


def can_approve_for_employee(user, employee, feature_key):
    """May `user` approve or reject `employee`'s leave / comp-off /
    attendance-correction request?

    Two independent ways in:
      * the role-based grant (Admin/HR/Manager via the permission matrix),
        exactly as before -- nobody loses access;
      * being that employee's own reporting person or manager, which is the
        point of the reporting line: routine approvals shouldn't queue
        behind whoever happens to hold the Admin role.
    """
    if user.is_superuser or user.is_staff:
        return True
    if has_feature_permission(user, feature_key, "approve"):
        return True
    approver = getattr(user, "employee_profile", None)
    if approver is None:
        return False
    return approver.id in {employee.reporting_person_id, employee.manager_id}


def is_reporting_approver(user):
    """Does this user sit on anyone's reporting line at all? Coarse gate for
    the approval endpoints -- whether they may act on a *specific* request
    is decided per record by can_approve_for_employee()."""
    from website.models import Employee

    approver = getattr(user, "employee_profile", None)
    if approver is None:
        return False
    return Employee.objects.filter(
        Q(reporting_person_id=approver.id) | Q(manager_id=approver.id)
    ).exists()


def approvable_employees(user, feature_key, base_qs):
    """Narrow an approval queue to the employees `user` may act on. Users
    with the blanket role grant see everything in `base_qs` (unchanged);
    a reporting person sees only their own reportees."""
    if user.is_superuser or user.is_staff or has_feature_permission(user, feature_key, "approve"):
        return base_qs
    approver = getattr(user, "employee_profile", None)
    if approver is None:
        return base_qs.none()
    return base_qs.filter(Q(reporting_person_id=approver.id) | Q(manager_id=approver.id))


def can_access_employee_record(user, employee, feature_key, action="view"):
    """Ownership check for per-employee detail pages (profile, attendance,
    payslip) that used to have no access control at all -- any authenticated
    user could view any employee's page by editing the URL's numeric ID.
    Allows: the employee viewing their own record, superuser/staff, or
    anyone whose role has the given feature permission (so HR/Admin/Manager
    keep their existing cross-employee access)."""
    if user.is_superuser or user.is_staff:
        return True
    if hasattr(user, "employee_profile") and user.employee_profile.id == employee.id:
        return True
    return has_feature_permission(user, feature_key, action)
