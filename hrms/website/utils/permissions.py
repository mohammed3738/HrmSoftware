from django.core.exceptions import PermissionDenied
from django.db.models import Q

def is_admin(user):
    return user.groups.filter(name="Admin").exists()

def is_hr(user):
    return user.groups.filter(name="HR").exists()

def is_hod(user):
    return user.groups.filter(name="HOD").exists()


def is_super_admin(user):
    return user.groups.filter(name="Super Admin").exists()


def is_payroll_officer(user):
    return user.groups.filter(name="Payroll Officer").exists()

def is_employee(user):
    return user.groups.filter(name="Employee").exists()

def admin_or_hr(user):
    return is_admin(user) or is_hr(user) or is_super_admin(user)


_PERMISSION_CACHE_ATTR = "_feature_permission_cache"


def _load_feature_permissions(user):
    """Every (feature_key, action) this user's roles grant, in one query.

    Loaded whole rather than one query per check: the nav alone asks about
    half a dozen features on every page render, and each gated panel asks
    about more."""
    from website.models import RoleFeaturePermission

    granted = set()
    rows = RoleFeaturePermission.objects.filter(role__in=user.groups.all()).values_list(
        "feature__key", "can_view", "can_create", "can_edit", "can_approve",
    )
    for feature_key, can_view, can_create, can_edit, can_approve in rows:
        for action, allowed in (
            ("view", can_view), ("create", can_create),
            ("edit", can_edit), ("approve", can_approve),
        ):
            if allowed:
                granted.add((feature_key, action))
    return granted


def invalidate_feature_permission_cache(user):
    """Drop the cached grants for `user` -- call after changing the
    permission matrix within a single request."""
    if hasattr(user, _PERMISSION_CACHE_ATTR):
        delattr(user, _PERMISSION_CACHE_ATTR)


def has_feature_permission(user, feature_key, action="view"):
    """Does any of this user's roles (Django Groups) grant `action` access
    to the feature identified by `feature_key`? Backs @feature_required.
    See website/permissions_registry.py for the full feature list and the
    seed data this is checked against.

    The user's grants are cached on the user instance, which lives for one
    request, so a page asking about many features costs one query rather
    than one per question."""
    granted = getattr(user, _PERMISSION_CACHE_ATTR, None)
    if granted is None:
        granted = _load_feature_permissions(user)
        try:
            setattr(user, _PERMISSION_CACHE_ATTR, granted)
        except AttributeError:
            # AnonymousUser and friends may not accept attributes.
            pass
    return (feature_key, action) in granted


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
