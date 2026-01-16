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
