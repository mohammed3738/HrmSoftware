# middleware.py
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.cache import patch_vary_headers


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


class PrivateCacheControlMiddleware:
    """Tell caches not to store anything this application generates.

    Django sends no Cache-Control header of its own, so every page this
    app produced -- a salary slip, a KYC scan, a 403 -- left the server
    with no instruction at all. What happens next is then up to whatever
    is in front of it: a browser's disk cache, an nginx `proxy_cache`, a
    CDN. Two consequences, both seen in practice:

    * a stored 403 is replayed for later requests, so one refusal looks
      like the whole site is forbidden until the cache is cleared. The
      refusal itself is per-user and per-request -- nothing on the server
      remembers it -- which is why only clearing a cache helps;
    * an employee's own pages can be served to whoever uses that browser
      or that shared cache next, after they have logged out.

    `Vary: Cookie` already went out on most responses, but it only helps a
    cache that honours it, and it says nothing about storing the response
    in the first place. This says it plainly instead.

    A response that sets its own Cache-Control is left alone, so a view
    that genuinely wants to be cached can say so.
    """

    #: Paths Django only serves in development; nginx serves them in
    #: production and sets its own expiry. No point marking them no-store.
    EXEMPT_PREFIXES = ("/static/",)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.path.startswith(self.EXEMPT_PREFIXES):
            return response
        if response.has_header("Cache-Control"):
            return response

        response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        # For HTTP/1.0 caches and proxies that ignore Cache-Control.
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"
        # Belt and braces for a shared cache that stores despite the above:
        # at least make it key on the session cookie rather than serving
        # one user's page to another.
        patch_vary_headers(response, ("Cookie",))
        return response
