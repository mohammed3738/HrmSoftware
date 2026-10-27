"""Biometric (eSSL / eTimeTrackLite) attendance sync: the push endpoint the
Windows agent talks to, and the page HR watches it on.

Kept out of website/views.py, which is already half a megabyte, for the same
reason the sync rules live in services/biometric_sync.py: the punch feed is
a self-contained piece and reads better on its own.

The endpoint is machine-to-machine. It carries no session and no CSRF token
-- the agent is a scheduled script on another network, not a browser -- so
it authenticates on a shared secret in the X-HRMS-Sync-Token header,
compared in constant time. With BIOMETRIC_SYNC_TOKEN unset the endpoint
refuses everything: an open punch feed would let anyone on the internet
write attendance.
"""
import datetime
import hmac
import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import BiometricPunch, BiometricSyncRun, Employee
from .services import biometric_sync
from .utils.decorators import feature_required

logger = logging.getLogger(__name__)

MAX_PUNCHES_PER_REQUEST = 20000


def _token_ok(request):
    expected = getattr(settings, "BIOMETRIC_SYNC_TOKEN", "") or ""
    if not expected:
        return False
    presented = request.headers.get("X-HRMS-Sync-Token", "")
    return hmac.compare_digest(presented, expected)


def _unauthorised():
    # Deliberately the same answer whether the token is missing, wrong, or
    # not configured at all -- the caller learns nothing about the server.
    return JsonResponse({"ok": False, "error": "Unauthorised."}, status=401)


@csrf_exempt
@require_POST
def biometric_punches_api(request):
    """POST /api/biometric/punches/

    Body: {"device": "<agent name>", "punches": [{...}, ...]}
    Each punch: device_user_id, employee_code, employee_name, punch_date
    ("YYYY-MM-DD"), punch_time ("HH:MM:SS"), device_id, direction,
    source_log_id. Only device_user_id, punch_date and punch_time are
    required; the rest make the audit trail readable.

    Punches already held are ignored, so the agent is free to re-send an
    overlapping window on every run -- and it should, because that is how a
    punch written late to the device database still gets picked up.
    """
    if not _token_ok(request):
        return _unauthorised()

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return JsonResponse({"ok": False, "error": f"Malformed JSON: {exc}"}, status=400)

    punches = payload.get("punches")
    if not isinstance(punches, list):
        return JsonResponse({"ok": False, "error": "'punches' must be a list."}, status=400)
    if len(punches) > MAX_PUNCHES_PER_REQUEST:
        return JsonResponse(
            {"ok": False, "error": f"Send at most {MAX_PUNCHES_PER_REQUEST} punches per request."},
            status=413,
        )

    try:
        run = biometric_sync.ingest(punches, source=BiometricSyncRun.SOURCE_AGENT)
    except Exception as exc:
        logger.exception("Biometric push from %s failed", payload.get("device") or "unknown agent")
        return JsonResponse({"ok": False, "error": str(exc)}, status=500)

    return JsonResponse({
        "ok": True,
        "run_id": run.id,
        "received": run.punches_received,
        "stored": run.punches_stored,
        "unmatched": run.punches_unmatched,
        "attendance_created": run.attendance_created,
        "attendance_updated": run.attendance_updated,
        "attendance_skipped": run.attendance_skipped,
        "message": run.message,
    })


@csrf_exempt
@require_GET
def biometric_status_api(request):
    """GET /api/biometric/status/ — where the agent should resume from when
    it has lost its own state file (a rebuilt machine, a cleared temp
    folder). Same token as the push endpoint."""
    if not _token_ok(request):
        return _unauthorised()

    last_run = BiometricSyncRun.objects.first()  # ordering is -started_at
    latest_punch = biometric_sync.latest_punch_date()
    return JsonResponse({
        "ok": True,
        "server_date": now().date().isoformat(),
        "latest_punch_date": latest_punch.isoformat() if latest_punch else None,
        "lookback_days": biometric_sync.lookback_days(),
        "last_run": None if last_run is None else {
            "source": last_run.source,
            "status": last_run.status,
            "started_at": last_run.started_at.isoformat(),
            "punches_stored": last_run.punches_stored,
        },
    })


# ── the page HR watches it on ─────────────────────────────────────────────

@login_required
@feature_required("attendance_data", "edit")
def biometric_sync_dashboard(request):
    """Attendance → Biometric Sync: is the feed alive, what came in, which
    punches match nobody, and a button to rebuild a date range by hand."""
    today = now().date()
    window_start = today - datetime.timedelta(days=13)

    runs = list(BiometricSyncRun.objects.all()[:20])
    # One row per day with its punch count, newest first.
    daily = (
        BiometricPunch.objects
        .filter(punch_date__gte=window_start, punch_date__lte=today)
        .values("punch_date")
        .annotate(punches=Count("id"))
        .order_by("-punch_date")
    )

    unmatched = (
        BiometricPunch.objects
        .filter(employee__isnull=True)
        .values("device_user_id", "employee_code", "employee_name")
        .annotate(punches=Count("id"))
        .order_by("-punches")[:50]
    )

    night_shift_employees = Employee.objects.filter(
        is_night_shift=True, status__in=biometric_sync.ACTIVE_EMPLOYEE_STATUSES,
    ).order_by("employee_code").only("employee_code", "first_name", "last_name", "department")

    return render(request, "attendance/biometric_sync.html", {
        "runs": runs,
        "daily_counts": daily,
        "unmatched": unmatched,
        "night_shift_employees": night_shift_employees,
        "total_punches": BiometricPunch.objects.count(),
        "unmatched_total": BiometricPunch.objects.filter(employee__isnull=True).count(),
        "token_configured": bool(getattr(settings, "BIOMETRIC_SYNC_TOKEN", "")),
        "lookback_days": biometric_sync.lookback_days(),
        "sync_hours": getattr(settings, "BIOMETRIC_SYNC_HOURS", ""),
        "max_shift_hours": biometric_sync.max_shift_hours(),
        "night_in_from": biometric_sync.night_in_from(),
        "night_out_until": biometric_sync.night_out_until(),
        "default_from": (today - datetime.timedelta(days=biometric_sync.lookback_days())).isoformat(),
        "default_to": today.isoformat(),
    })


@login_required
@feature_required("attendance_data", "edit")
@require_POST
def biometric_resync(request):
    """Rebuild attendance for a date range from punches already stored.
    Fetches nothing -- the agent owns that -- so it is safe to press at any
    time and is the fix for "the punches are there but the day looks
    wrong"."""
    def _date(name, default):
        raw = (request.POST.get(name) or "").strip()
        if not raw:
            return default
        try:
            return datetime.date.fromisoformat(raw)
        except ValueError:
            return None

    today = now().date()
    to_date = _date("to_date", today)
    from_date = _date("from_date", today - datetime.timedelta(days=biometric_sync.lookback_days()))

    if from_date is None or to_date is None:
        messages.error(request, "Enter both dates as YYYY-MM-DD.")
        return redirect("biometric-sync")
    if from_date > to_date:
        messages.error(request, "'From' date cannot be after the 'To' date.")
        return redirect("biometric-sync")
    if (to_date - from_date).days > 92:
        messages.error(request, "Rebuild at most three months at a time.")
        return redirect("biometric-sync")

    try:
        run = biometric_sync.resync_window(
            from_date=from_date, to_date=to_date,
            source=BiometricSyncRun.SOURCE_MANUAL,
        )
    except Exception as exc:
        logger.exception("Manual biometric resync failed")
        messages.error(request, f"Rebuild failed: {exc}")
        return redirect("biometric-sync")

    messages.success(
        request,
        f"Rebuilt {from_date:%d %b %Y} – {to_date:%d %b %Y} from {run.punches_received} stored punch(es): "
        f"{run.attendance_created} day(s) created, {run.attendance_updated} updated, "
        f"{run.attendance_skipped} left alone (manual times, finalized payroll or before joining).",
    )
    return redirect("biometric-sync")
