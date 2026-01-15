# middleware.py
from django.shortcuts import redirect
from django.urls import reverse

class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            if hasattr(request.user, "employee_profile"):   # ✅ FIX
                employee = request.user.employee_profile    # ✅ FIX
                if employee.force_password_change:
                    if request.path not in ["/change-password/", "/logout/"]:
                        return redirect("change-password")

        return self.get_response(request)
