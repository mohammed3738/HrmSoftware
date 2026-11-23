"""
What people see when a form's CSRF check fails.

This mostly happens for harmless reasons: a login page left open in a tab
for hours, a page from before the browser's cookies changed, or an old copy
restored with the Back button. Django's default answer is a bare
"Forbidden (403)" page that looks like the site is broken. Instead, send
the person back to a fresh copy of the page, with a note to try again.
Fetch/AJAX calls get a JSON 403 that the page's script can show.
"""
from django.contrib import messages
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

MESSAGE = "Your page had expired, so nothing was saved. Please try again."


def _wants_json(request):
    return (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "X-CSRFToken" in request.headers
        or "application/json" in request.headers.get("accept", "")
        or request.content_type == "application/json"
    )


def csrf_failure(request, reason=""):
    if _wants_json(request):
        return JsonResponse(
            {"success": False, "message": "Your page has expired. Please refresh the page and try again."},
            status=403,
        )

    # Go back to the page the form was on (its Referer), else the same URL,
    # but never off-site.
    target = request.headers.get("referer") or request.get_full_path()
    if not url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        target = reverse("login")

    try:
        messages.warning(request, MESSAGE)
    except Exception:  # messages middleware not available on this request
        pass
    response = HttpResponseRedirect(target)
    # Make sure the page they land on is fresh, not a cached copy with the
    # stale token.
    response["Cache-Control"] = "no-store"
    return response
