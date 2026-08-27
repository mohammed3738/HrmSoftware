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
