"""Onboarding progress for an employee record.

One weighted checklist drives every progress bar (employee list, form,
profile, dashboard) and the edit lock, so they always agree:

    Personal details     25%   Office details        15%
    Bank & IDs           20%   Emergency contact     10%
    Previous employment  10%   Documents (any 2)     20%

Within a section the weight is split evenly across its items, so a half-
filled section contributes half its weight.
"""
from datetime import date, timedelta

# HR may edit an incomplete onboarding directly for this many days after it
# started; after that (or once it's 100%) HR's edits go for approval.
ONBOARDING_EDIT_DAYS = 15

# No particular KYC document is required: any two attached documents
# (Aadhaar, PAN, resume, offer letter or "other") complete the section.
# The photo doesn't count towards it.
REQUIRED_DOCUMENT_COUNT = 2

SECTIONS = [
    ("personal", "Personal details", 25, [
        ("first_name", "First name"), ("last_name", "Last name"), ("father_name", "Father's name"),
        ("gender", "Gender"), ("date_of_birth", "Date of birth"), ("personal_mobile", "Mobile number"),
        ("personal_email", "Personal email"), ("present_address", "Present address"),
        ("permanent_address", "Permanent address"),
    ]),
    ("office", "Office details", 15, [
        ("company_id", "Company"), ("branch_id", "Branch"), ("employee_code", "Employee code"),
        ("designation", "Designation"), ("department", "Department"), ("date_of_joining", "Date of joining"),
    ]),
    ("bank", "Bank & IDs", 20, [
        ("pan_no", "PAN number"), ("aadhar_no", "Aadhaar number"), ("name_as_per_bank", "Name as per bank"),
        ("salary_account_number", "Bank account number"), ("ifsc_code", "IFSC code"),
    ]),
    ("emergency", "Emergency contact", 10, [
        ("emergency_contact_name1", "Emergency contact name"),
        ("emergency_contact_relation1", "Emergency contact relation"),
        ("emergency_contact_mobile1", "Emergency contact mobile"),
    ]),
]


def _filled(value):
    return value is not None and str(value).strip() != ""


def onboarding_progress(employee):
    """{"percent": int 0-100, "remaining": 100 - percent, "complete": bool, "sections": [...], "missing": [labels]}.

    For many employees at once use bulk_onboarding_progress(), which
    doesn't build a model object per employee."""
    has_previous = bool(employee.pk and list(employee.previous_employments.all()))
    documents = sum(1 for a in employee.attachments.all() if a.file) if employee.pk else 0
    return _progress(lambda field: getattr(employee, field, None), has_previous, documents)


def bulk_onboarding_progress(qs):
    """{employee id: onboarding_progress()} for every employee in `qs`, in
    three flat queries -- for lists and the dashboard, where building a
    model object (and prefetching two relations) per employee was the
    slow part at a thousand employees."""
    from ..models import EmployeeAttachment, PreviousEmployment

    fields = ["id", "is_fresher", "photo"] + [name for *_, items in SECTIONS for name, _ in items]
    rows = list(qs.values(*fields))
    ids = [r["id"] for r in rows]
    with_previous = set(PreviousEmployment.objects.filter(employee_id__in=ids).values_list("employee_id", flat=True))
    documents = {}
    for emp_id in EmployeeAttachment.objects.filter(employee_id__in=ids).exclude(file="").values_list("employee_id", flat=True):
        documents[emp_id] = documents.get(emp_id, 0) + 1
    return {
        r["id"]: _progress(r.get, r["id"] in with_previous, documents.get(r["id"], 0))
        for r in rows
    }


def _progress(get, has_previous_employment, document_count):
    sections, total, missing = [], 0.0, []

    for key, title, weight, fields in SECTIONS:
        done = [label for field, label in fields if _filled(get(field))]
        todo = [label for field, label in fields if label not in done]
        _add(sections, key, title, weight, len(done), len(fields), todo)
        total += weight * len(done) / len(fields)
        missing += todo

    has_previous = bool(get("is_fresher")) or has_previous_employment
    todo = [] if has_previous else ["Previous employment (or tick Fresher)"]
    _add(sections, "previous", "Previous employment", 10, int(has_previous), 1, todo)
    total += 10 * int(has_previous)
    missing += todo

    done = min(document_count, REQUIRED_DOCUMENT_COUNT)
    still_needed = REQUIRED_DOCUMENT_COUNT - done
    todo = ([f"KYC documents ({still_needed} more of any {REQUIRED_DOCUMENT_COUNT})"] if still_needed else [])
    _add(sections, "documents", "Documents", 20, done, REQUIRED_DOCUMENT_COUNT, todo)
    total += 20 * done / REQUIRED_DOCUMENT_COUNT
    missing += todo

    percent = 100 if not missing else min(99, int(total))
    return {"percent": percent, "remaining": 100 - percent, "complete": not missing,
            "sections": sections, "missing": missing}


def _add(sections, key, title, weight, done, count, todo):
    sections.append({
        "key": key, "title": title, "weight": weight, "done": done, "count": count,
        "percent": round(100 * done / count) if count else 100, "missing": todo,
    })


def onboarding_edit_deadline(employee):
    start = employee.onboarding_started_at or date.today()
    return start + timedelta(days=ONBOARDING_EDIT_DAYS)


def onboarding_open_for_direct_edit(employee, progress=None):
    """Whether someone without approval rights may still save changes to
    this employee directly: onboarding is incomplete and started less than
    ONBOARDING_EDIT_DAYS ago."""
    progress = progress or onboarding_progress(employee)
    return not progress["complete"] and date.today() < onboarding_edit_deadline(employee)
