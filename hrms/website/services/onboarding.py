"""Onboarding progress for an employee record.

One weighted checklist drives every progress bar (employee list, form,
profile, dashboard) and the edit lock, so they always agree:

    Personal details     25%   Office details        15%
    Bank & IDs           20%   Emergency contact     10%
    Previous employment  10%   Documents (Aadhaar, PAN) 20%

Within a section the weight is split evenly across its items, so a half-
filled section contributes half its weight.
"""
from datetime import date, timedelta

# HR may edit an incomplete onboarding directly for this many days after it
# started; after that (or once it's 100%) HR's edits go for approval.
ONBOARDING_EDIT_DAYS = 15

# Only these KYC documents are required; resume, offer letter, photo and
# any other upload are optional and don't affect the percentage.
REQUIRED_DOCUMENTS = [
    ("aadhaar", "Aadhaar card"),
    ("pan", "PAN card"),
]

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
    uploaded = {a.file_name for a in employee.attachments.all()} if employee.pk else set()
    return _progress(lambda field: getattr(employee, field, None), has_previous, uploaded)


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
    uploaded = {}
    for emp_id, file_name in EmployeeAttachment.objects.filter(employee_id__in=ids).values_list("employee_id", "file_name"):
        uploaded.setdefault(emp_id, set()).add(file_name)
    return {
        r["id"]: _progress(r.get, r["id"] in with_previous, uploaded.get(r["id"], set()))
        for r in rows
    }


def _progress(get, has_previous_employment, uploaded):
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

    docs = [(code, label, code in uploaded) for code, label in REQUIRED_DOCUMENTS]
    todo = [label for _, label, ok in docs if not ok]
    done = len(docs) - len(todo)
    _add(sections, "documents", "Documents", 20, done, len(docs), todo)
    total += 20 * done / len(docs)
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
