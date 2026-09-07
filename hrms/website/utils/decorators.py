from django.core.exceptions import PermissionDenied
from django.conf import settings
from functools import wraps


def group_required(*group_names):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
            if request.user.is_superuser or request.user.is_staff:
                return view_func(request, *args, **kwargs)
            if request.user.groups.filter(name__in=group_names).exists():
                return view_func(request, *args, **kwargs)
            raise PermissionDenied
        return _wrapped_view
    return decorator


def feature_required(feature_key, action="view"):
    """Database-driven replacement for group_required: checks the
    RoleFeaturePermission matrix (see website/models.py, managed from the
    Roles & Permissions settings page) instead of a hardcoded group-name
    list. Superuser/staff bypass and the not-authenticated redirect are
    identical to group_required, so migrating a view from one decorator to
    the other never changes behavior for those accounts."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
            if request.user.is_superuser or request.user.is_staff:
                return view_func(request, *args, **kwargs)
            from .permissions import has_feature_permission
            if has_feature_permission(request.user, feature_key, action):
                return view_func(request, *args, **kwargs)
            raise PermissionDenied
        return _wrapped_view
    return decorator


# Ordered weakest to strongest: holding an action implies every action to
# its left, so an editor can also create and read.
_ACTION_LADDER = ("view", "create", "edit")


def create_or_edit_required(feature_key, resolve_action):
    """Gate a view that does more than one thing depending on the request:
    reading a list, adding a record, or changing an existing one.

    Several pages in this app are a single view for all three (the employee
    form, the offboarding page, the salary structure form), and a role can
    legitimately be allowed to add without being allowed to change what's
    already there -- HR onboarding an employee, say. `resolve_action` is a
    callable given (request, *args, **kwargs) returning "view", "create" or
    "edit" for this particular request.

    Stronger actions satisfy weaker ones, so a role with `edit` never has to
    also be granted `create` for the same feature."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
            if request.user.is_superuser or request.user.is_staff:
                return view_func(request, *args, **kwargs)

            from .permissions import has_feature_permission
            required = resolve_action(request, *args, **kwargs)
            acceptable = _ACTION_LADDER[_ACTION_LADDER.index(required):]
            if any(has_feature_permission(request.user, feature_key, a) for a in acceptable):
                return view_func(request, *args, **kwargs)
            raise PermissionDenied
        return _wrapped_view
    return decorator


def approval_required(feature_key):
    """Coarse gate for the approve/reject endpoints: lets through anyone the
    role matrix grants `approve` on (Admin/HR/Manager, unchanged) *plus*
    anyone who sits on some employee's reporting line.

    Deliberately coarse -- it only answers "are you an approver at all?".
    Whether the user may act on a *particular* request is an object-level
    question answered per record inside the view by
    can_approve_for_employee(), since it depends on whose request it is."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
            if request.user.is_superuser or request.user.is_staff:
                return view_func(request, *args, **kwargs)
            from .permissions import has_feature_permission, is_reporting_approver
            if has_feature_permission(request.user, feature_key, "approve"):
                return view_func(request, *args, **kwargs)
            if is_reporting_approver(request.user):
                return view_func(request, *args, **kwargs)
            raise PermissionDenied
        return _wrapped_view
    return decorator
