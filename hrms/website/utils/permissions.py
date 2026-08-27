from django.core.exceptions import PermissionDenied

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
