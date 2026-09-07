# middleware.py
from django.http import JsonResponse
from django.shortcuts import redirect


class ForcePasswordChangeMiddleware:
    """Push a user who still has a temporary password to the change-password
    page before they can use anything else."""

    EXEMPT_PATHS = ("/change-password/", "/logout/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and hasattr(request.user, "employee_profile"):
            employee = request.user.employee_profile
            if employee.force_password_change and request.path not in self.EXEMPT_PATHS:
                # A redirect answers an AJAX call with the change-password
                # HTML, which the caller then fails to parse as JSON and
                # reports as a server error -- a misleading dead end. Say
                # what is actually wrong instead.
                if self._is_ajax(request):
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "You must change your temporary password before using this. "
                                     "Open Change Password, set a new one, then try again.",
                            "password_change_required": True,
                        },
                        status=409,
                    )
                return redirect("change-password")

        return self.get_response(request)

    @staticmethod
    def _is_ajax(request):
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return True
        # fetch() sends this on cross-origin-ish requests and most of this
        # app's AJAX posts; Accept is the reliable signal for the rest.
        accept = request.headers.get("accept", "")
        return "application/json" in accept and "text/html" not in accept
