from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    if dictionary and key in dictionary:
        return dictionary.get(key)
    return 0

@register.filter
def to_float(value):
    try:
        return float(value)
    except:
        return 0

@register.filter
def subtract(a, b):
    """Return numeric difference (a - b)"""
    try:
        return float(a) - float(b)
    except:
        return 0




@register.filter
def getattribute(obj, attr_name):
    return getattr(obj, attr_name, "")


@register.filter
def is_employee_role(user):
    """True if this user should land on the Employee Dashboard rather than
    the Admin Dashboard -- mirrors login_view's post-login redirect logic,
    so the "Dashboards" nav link goes somewhere the user can actually open
    instead of 403ing for an Employee-role user."""
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or user.is_staff:
        return False
    if user.groups.filter(name__in=["Admin", "HR", "Manager"]).exists():
        return False
    return user.groups.filter(name="Employee").exists()


@register.filter
def has_feature(user, feature_key_and_action):
    """General-purpose permission check for templates: does this user's
    role grant them `action` on `feature_key`? Usage:
    {% if request.user|has_feature:"announcements:edit" %}...{% endif %}
    Backed by the same Roles & Permissions matrix as @feature_required."""
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or user.is_staff:
        return True
    try:
        feature_key, action = feature_key_and_action.split(":", 1)
    except ValueError:
        return False
    from website.utils.permissions import has_feature_permission
    return has_feature_permission(user, feature_key, action)


@register.filter
def has_reportees(user):
    """Does anyone report to this user? Drives the 'My Approvals' nav item,
    which has to appear for plain Employee-role logins who happen to be a
    department's reporting person -- a role-based check can't see that."""
    if not getattr(user, "is_authenticated", False):
        return False
    approver = getattr(user, "employee_profile", None)
    if approver is None:
        return False
    from django.db.models import Q
    from website.models import Employee
    return Employee.objects.filter(
        Q(reporting_person_id=approver.id) | Q(manager_id=approver.id)
    ).exclude(pk=approver.pk).exists()
