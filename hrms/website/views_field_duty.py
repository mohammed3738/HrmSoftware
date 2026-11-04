"""Field Duty: the two buttons a field employee works from, and the log the
office reads.

Kept out of website/views.py for the same reason views_biometric.py is --
that file is already 12,000 lines and this is a self-contained piece.

The shape of the thing
----------------------
One record per trip out (website/models.py, FieldDuty). Start Field Duty
opens it, End Field Duty closes it, and both ends capture the same three
pieces of evidence: the time, the place and a photograph of who it was. A
client meeting additionally stays Pending Report until its minutes are
uploaded; everything else completes when the employee gets back.

What is trusted and what is not
-------------------------------
The timestamps come from the server clock, never from the request. A
browser could claim any `started_at` it liked, and this record's whole
purpose is to be evidence about when somebody was somewhere.

The coordinates and the selfie necessarily come from the device, so they
are evidence of what the device reported, not proof of fact -- which is why
`start_accuracy_m` is kept and shown: a fix with a 2 km accuracy radius was
a network lookup, not GPS, and must not be read as a location. What the
server can enforce is that *something* was captured, and it does: a punch
with no photo or no coordinates is refused rather than stored half-blind.

The selfies are faces and the coordinates are an employee's movements, so
neither is ever served from a raw /media/ URL (nginx serves those with no
authentication at all -- DEPLOYMENT.md, tracker D-23). They go through
field_duty_selfie below, behind a permission check.
"""
import calendar
import datetime
import os
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.images import get_image_dimensions
from django.db import IntegrityError, transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Attendance, Company, FieldDuty
from .services import field_duty as field_duty_service
from .utils.permissions import can_access_employee_record

# A phone selfie is a few hundred KB. The page downscales to 720px wide
# before uploading, so anything near this ceiling is not a selfie.
SELFIE_MAX_BYTES = getattr(settings, "FIELD_DUTY_SELFIE_MAX_BYTES", 5 * 1024 * 1024)
REPORT_MAX_BYTES = getattr(settings, "FIELD_DUTY_REPORT_MAX_BYTES", 10 * 1024 * 1024)

# Minutes of Meeting arrive as a document or a photo of a signed sheet.
# An allow-list rather than a block-list: nothing validates the content of
# an upload, so anything that could execute in this origin stays out
# (_NEVER_INLINE_EXTENSIONS in views.py forces a download for those that
# slip in by another route, but there is no reason to accept them here).
REPORT_EXTENSIONS = frozenset({
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".rtf",
    ".jpg", ".jpeg", ".png", ".webp", ".heic",
})

SELFIE_SIDES = {"start": "start_selfie", "end": "end_selfie"}


# ---------------------------------------------------------------------------
# Request parsing
# ---------------------------------------------------------------------------

class CaptureError(ValidationError):
    """Something the employee can fix, phrased for them rather than for a log."""


def _employee_or_none(user):
    return getattr(user, "employee_profile", None)


def _parse_coordinate(raw, name, limit):
    if raw in (None, ""):
        raise CaptureError(
            "Location is required for a field duty punch. Allow location "
            "access for this site and try again."
        )
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        raise CaptureError(f"{name} is not a number.")
    if not (-limit <= value <= limit):
        raise CaptureError(f"{name} is out of range.")
    # The column is DecimalField(max_digits=9, decimal_places=6): about
    # 10 cm of precision, which is finer than any phone reports.
    return value.quantize(Decimal("0.000001"))


def _parse_accuracy(raw):
    if raw in (None, ""):
        return None
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return None
    if value < 0:
        return None
    # Anything beyond this is a nonsense reading, not a location.
    return min(value, 100000)


def _parse_location(post):
    return {
        "latitude": _parse_coordinate(post.get("latitude"), "Latitude", 90),
        "longitude": _parse_coordinate(post.get("longitude"), "Longitude", 180),
        "accuracy_m": _parse_accuracy(post.get("accuracy")),
    }


def _validated_selfie(files):
    upload = files.get("selfie")
    if not upload:
        raise CaptureError(
            "A selfie is required for a field duty punch. Allow camera "
            "access for this site and try again."
        )
    if upload.size > SELFIE_MAX_BYTES:
        raise CaptureError(
            f"That photo is {upload.size // 1024} KB, over the "
            f"{SELFIE_MAX_BYTES // 1024 // 1024} MB limit."
        )
    # Not the content type the browser claims -- that is caller-supplied
    # text. get_image_dimensions actually decodes the header, so a renamed
    # file fails here.
    try:
        width, height = get_image_dimensions(upload)
    except Exception:
        width = height = None
    if not width or not height:
        raise CaptureError("That file is not an image.")
    upload.seek(0)
    return upload


def _validated_report(files):
    upload = files.get("report")
    if not upload:
        raise CaptureError("Choose the file to upload.")
    if upload.size > REPORT_MAX_BYTES:
        raise CaptureError(
            f"That file is over the {REPORT_MAX_BYTES // 1024 // 1024} MB limit."
        )
    extension = os.path.splitext(upload.name)[1].lower()
    if extension not in REPORT_EXTENSIONS:
        raise CaptureError(
            "That file type isn't accepted. Upload a PDF, Word or Excel "
            "document, or a photo."
        )
    return upload


def _error(exc, status=400):
    message = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
    return JsonResponse({"success": False, "error": message}, status=status)


def _attendance_note(outcome):
    """One sentence about what the punch did to the day's attendance."""
    if outcome.get("applied"):
        parts = []
        if outcome.get("in_time"):
            parts.append(f"in-time {outcome['in_time']:%H:%M}")
        if outcome.get("out_time"):
            parts.append(f"out-time {outcome['out_time']:%H:%M}")
        return "Today's attendance now shows " + " and ".join(parts) + "."
    if outcome.get("skipped"):
        return "Attendance was not changed: " + outcome["skipped"]
    return ""


# ---------------------------------------------------------------------------
# The employee's own page
# ---------------------------------------------------------------------------

@login_required
def field_duty_home(request):
    """Start / End Field Duty, plus this employee's own recent duties.

    Not feature-gated: like My Attendance and Leave Apply, this is
    self-service and only ever reads request.user's own records, so there is
    no other employee's data here to get wrong.
    """
    employee = _employee_or_none(request.user)
    if employee is None:
        from django.contrib import messages
        messages.error(request, "Your account isn't linked to an employee profile.")
        return redirect("login")

    today = timezone.localdate()
    duties = FieldDuty.objects.filter(employee=employee)

    # The history is browsed a month at a time. The open duty and anything
    # awaiting a report are deliberately *not* month-filtered: they are
    # live work, and hiding them because the employee was looking at last
    # month would hide the End button itself.
    month_start, month_end, month_value = month_range(request.GET.get("month"))

    return render(request, "field_duty/home.html", {
        "employee": employee,
        "open_duty": duties.filter(ended_at__isnull=True).first(),
        "month_duties": list(duties.filter(
            duty_date__gte=month_start, duty_date__lte=month_end,
        )),
        "month_value": month_value,
        "month_start": month_start,
        "awaiting_report": list(duties.filter(status=FieldDuty.Status.PENDING_REPORT)),
        "today_attendance": Attendance.objects.filter(employee=employee, date=today).first(),
        "activities": FieldDuty.Activity.choices,
        "report_required_activities": [a.value for a in FieldDuty.REPORT_REQUIRED_ACTIVITIES],
        "today": today,
    })


@login_required
@require_POST
def field_duty_start(request):
    """Open a duty. Server clock, device location, live selfie."""
    employee = _employee_or_none(request.user)
    if employee is None:
        return JsonResponse(
            {"success": False, "error": "Your account isn't linked to an employee profile."},
            status=403,
        )

    activity = (request.POST.get("activity") or "").strip()
    if activity not in FieldDuty.Activity.values:
        return JsonResponse({"success": False, "error": "Choose what you are going out for."}, status=400)

    try:
        location = _parse_location(request.POST)
        selfie = _validated_selfie(request.FILES)
    except ValidationError as exc:
        return _error(exc)

    started_at = timezone.now()

    try:
        with transaction.atomic():
            duty = FieldDuty(
                employee=employee,
                activity=activity,
                purpose=(request.POST.get("purpose") or "").strip()[:255],
                notes=(request.POST.get("notes") or "").strip(),
                started_at=started_at,
                start_latitude=location["latitude"],
                start_longitude=location["longitude"],
                start_accuracy_m=location["accuracy_m"],
                start_selfie=selfie,
            )
            duty.save()
    except IntegrityError:
        # one_open_field_duty_per_employee. Two taps, or a second device.
        return JsonResponse({
            "success": False,
            "error": "You already have a field duty running. End that one first.",
        }, status=409)

    outcome = field_duty_service.apply_to_attendance(duty)

    return JsonResponse({
        "success": True,
        "duty_id": duty.id,
        "message": f"{duty.get_activity_display()} started at "
                   f"{timezone.localtime(duty.started_at):%H:%M}.",
        "attendance_note": _attendance_note(outcome),
        "redirect": "",
    })


@login_required
@require_POST
def field_duty_end(request):
    """Close the caller's own open duty."""
    employee = _employee_or_none(request.user)
    if employee is None:
        return JsonResponse(
            {"success": False, "error": "Your account isn't linked to an employee profile."},
            status=403,
        )

    duty = FieldDuty.objects.filter(employee=employee, ended_at__isnull=True).first()
    if duty is None:
        return JsonResponse(
            {"success": False, "error": "You have no field duty running."}, status=404,
        )

    try:
        location = _parse_location(request.POST)
        selfie = _validated_selfie(request.FILES)
    except ValidationError as exc:
        return _error(exc)

    duty.ended_at = timezone.now()
    duty.end_latitude = location["latitude"]
    duty.end_longitude = location["longitude"]
    duty.end_accuracy_m = location["accuracy_m"]
    duty.end_selfie = selfie
    closing_notes = (request.POST.get("notes") or "").strip()
    if closing_notes:
        duty.notes = (duty.notes + "\n" if duty.notes else "") + closing_notes
    duty.save()

    outcome = field_duty_service.apply_to_attendance(duty)

    pending = duty.status == FieldDuty.Status.PENDING_REPORT
    message = f"{duty.get_activity_display()} ended at {timezone.localtime(duty.ended_at):%H:%M} ({duty.duration_display})."
    if pending:
        message += f" Upload the {duty.report_label} to close it."

    return JsonResponse({
        "success": True,
        "duty_id": duty.id,
        "status": duty.status,
        "pending_report": pending,
        "report_label": duty.report_label,
        "message": message,
        "attendance_note": _attendance_note(outcome),
    })


@login_required
@require_POST
def field_duty_upload_report(request, pk):
    """Attach the Minutes of Meeting (or field report) that closes a duty.

    The employee uploads their own; whoever may edit the field duty log can
    upload on anyone's behalf, for the employee who sends the minutes by
    email instead.
    """
    duty = get_object_or_404(FieldDuty.objects.select_related("employee"), pk=pk)

    own = _employee_or_none(request.user) == duty.employee
    if not own and not can_access_employee_record(
        request.user, duty.employee, "field_duty", "edit",
    ):
        raise PermissionDenied

    if duty.is_open:
        return JsonResponse({
            "success": False,
            "error": "End the field duty before uploading its report.",
        }, status=400)

    try:
        upload = _validated_report(request.FILES)
    except ValidationError as exc:
        return _error(exc)

    duty.report = upload
    duty.report_notes = (request.POST.get("report_notes") or "").strip()
    duty.report_uploaded_at = timezone.now()
    duty.save()

    return JsonResponse({
        "success": True,
        "status": duty.status,
        "message": f"{duty.report_label} uploaded. This duty is now {duty.get_status_display().lower()}.",
    })


# ---------------------------------------------------------------------------
# The office's log
# ---------------------------------------------------------------------------

def month_range(raw):
    """'YYYY-MM' -> (first day, last day, 'YYYY-MM'), defaulting to this month.

    Returned as a triple so the template can put the value straight back
    into its <input type="month"> without reformatting it, and a junk or
    missing value quietly becomes this month rather than an error page --
    this is a filter, not a form submission.
    """
    today = timezone.localdate()
    year, month = today.year, today.month
    if raw:
        try:
            parsed = datetime.datetime.strptime(raw.strip(), "%Y-%m")
            year, month = parsed.year, parsed.month
        except (ValueError, AttributeError):
            pass
    first = datetime.date(year, month, 1)
    last = datetime.date(year, month, calendar.monthrange(year, month)[1])
    return first, last, f"{year:04d}-{month:02d}"


# Who a Field Duty Log reader may see.
SCOPE_EVERYONE = "everyone"
SCOPE_TEAM = "team"


def log_scope(user):
    """(scope, viewer) for the log, or (None, None) for somebody who may not
    open it at all.

    Two separate ways in, and they answer different questions:

    * `field_duty:view` is a company-wide grant -- Admin, HR, Payroll
      Officer. It is a role decision, taken on the Roles & Permissions page.
    * sitting on somebody's reporting line is not a role at all. A team
      leader or manager is whoever a department or an employee record points
      at, so it cannot be granted from the permission matrix, and giving
      HOD the company-wide right instead would show one team's leader every
      other team as well. They get their own reportees, from the same
      reporting line that already routes approvals to them.
    """
    if user.is_superuser or user.is_staff:
        return SCOPE_EVERYONE, None
    from .utils.permissions import has_feature_permission
    if has_feature_permission(user, "field_duty", "view"):
        return SCOPE_EVERYONE, None

    viewer = _employee_or_none(user)
    if viewer is not None and _reportee_filter(viewer, exclude_self=True).exists():
        return SCOPE_TEAM, viewer
    return None, None


def _reportee_filter(viewer, exclude_self=False):
    from django.db.models import Q

    from .models import Employee

    reportees = Employee.objects.filter(
        Q(reporting_person_id=viewer.id) | Q(manager_id=viewer.id)
    )
    return reportees.exclude(pk=viewer.pk) if exclude_self else reportees


def _can_see_employees_duty(user, employee):
    """Own record, the company-wide grant, or being this employee's own
    reporting person or manager."""
    if can_access_employee_record(user, employee, "field_duty", "view"):
        return True
    viewer = _employee_or_none(user)
    if viewer is None:
        return False
    return viewer.id in {employee.reporting_person_id, employee.manager_id}


@login_required
def field_duty_log(request):
    """Field duty for everybody, or for one leader's own team.

    Not `@feature_required`: that decorator can only ask about the role
    matrix, and a team leader's authority here comes from the reporting
    line instead. `log_scope` answers both, and refuses anyone with
    neither -- an ordinary employee reads their own duties on the Field
    Duty page, which needs no grant at all.
    """
    from django.db.models import Q

    scope, viewer = log_scope(request.user)
    if scope is None:
        raise PermissionDenied

    duties = FieldDuty.objects.select_related("employee", "employee__company")
    if scope == SCOPE_TEAM:
        # Their own duties belong on their team's list too -- a team leader
        # goes out to meetings like everyone else.
        duties = duties.filter(
            Q(employee__reporting_person_id=viewer.id)
            | Q(employee__manager_id=viewer.id)
            | Q(employee_id=viewer.id)
        )

    month_start, month_end, month_value = month_range(request.GET.get("month"))
    duties = duties.filter(duty_date__gte=month_start, duty_date__lte=month_end)

    employee_id = request.GET.get("employee") or ""
    if employee_id.isdigit():
        duties = duties.filter(employee_id=int(employee_id))

    status = request.GET.get("status") or ""
    if status in FieldDuty.Status.values:
        duties = duties.filter(status=status)

    activity = request.GET.get("activity") or ""
    if activity in FieldDuty.Activity.values:
        duties = duties.filter(activity=activity)

    company_id = request.GET.get("company") or ""
    if company_id.isdigit():
        duties = duties.filter(employee__company_id=int(company_id))

    search = (request.GET.get("q") or "").strip()
    if search:
        from django.db.models import Q
        duties = duties.filter(
            Q(employee__first_name__icontains=search)
            | Q(employee__last_name__icontains=search)
            | Q(employee__employee_code__icontains=search)
            | Q(purpose__icontains=search)
        )

    duties = list(duties[:500])

    # The employee dropdown lists exactly who this reader may see, so it
    # cannot be used to probe for people outside their scope.
    if scope == SCOPE_TEAM:
        people = _reportee_filter(viewer).order_by("first_name", "last_name")
    else:
        from .models import Employee
        people = Employee.objects.filter(status="Active").order_by("first_name", "last_name")

    return render(request, "field_duty/log.html", {
        "duties": duties,
        "scope": scope,
        "is_team_scope": scope == SCOPE_TEAM,
        "month_value": month_value,
        "month_start": month_start,
        "selected_employee": employee_id,
        "selected_status": status,
        "selected_activity": activity,
        "selected_company": company_id,
        "search": search,
        "people": people,
        "statuses": FieldDuty.Status.choices,
        "activities": FieldDuty.Activity.choices,
        "companies": Company.objects.all().order_by("name"),
        "counts": {
            "total": len(duties),
            "open": sum(1 for d in duties if d.status == FieldDuty.Status.IN_PROGRESS),
            "pending": sum(1 for d in duties if d.status == FieldDuty.Status.PENDING_REPORT),
        },
    })


def _visible_duty_or_403(request, pk):
    """A duty the caller may see: their own, one the company-wide grant
    covers, or one belonging to somebody who reports to them.

    Deliberately the same three answers as the log itself -- otherwise a
    row a team leader can see in the list would refuse to open, or worse,
    a selfie would open for somebody the list would never have shown."""
    duty = get_object_or_404(
        FieldDuty.objects.select_related("employee", "employee__company"), pk=pk,
    )
    if not _can_see_employees_duty(request.user, duty.employee):
        raise PermissionDenied
    return duty


@login_required
def field_duty_detail(request, pk):
    """One duty, as the modal on either page reads it."""
    duty = _visible_duty_or_403(request, pk)
    return render(request, "field_duty/_detail.html", {"duty": duty})


@login_required
def field_duty_selfie(request, pk, side):
    """A start or end selfie.

    Deliberately not FieldFile.url: that is a raw /media/ path, which nginx
    serves to anybody who has it. These are photographs of employees'
    faces.
    """
    field_name = SELFIE_SIDES.get(side)
    if field_name is None:
        raise Http404("Unknown selfie")
    duty = _visible_duty_or_403(request, pk)
    from .views import _stream_protected_file
    return _stream_protected_file(request, getattr(duty, field_name))


@login_required
def field_duty_report(request, pk):
    """The Minutes of Meeting / field report attached to a duty."""
    duty = _visible_duty_or_403(request, pk)
    from .views import _stream_protected_file
    return _stream_protected_file(request, duty.report)
