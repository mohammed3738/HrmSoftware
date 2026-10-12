"""Employee edits that need approval (see EmployeeChangeRequest).

build_change_request() turns a validated employee form submission into a
pending request without touching the employee; apply_change_request()
writes it once approved; reject_change_request() discards it.
"""
from datetime import date, datetime, time
from decimal import Decimal

from django.db import models, transaction
from django.utils import timezone

from ..models import (
    AuditLog, Employee, EmployeeAttachment, EmployeeChangeRequest, EmployeeChangeRequestFile,
    PreviousEmployment, PreviousEmploymentAttachment,
)
from .audit import log_audit
from .onboarding import onboarding_open_for_direct_edit

PREVIOUS_EMPLOYMENT_FIELDS = ("employer_name", "from_date", "to_date", "last_ctc")


class ChangeRequestError(Exception):
    """A submission that can't become a change request (shown to the user)."""


def can_approve_changes(user):
    """Approvers: holders of employee_change_approval:approve, plus
    superusers/staff -- who pass every other permission check too, even
    with no role assigned."""
    from ..utils.permissions import has_feature_permission
    return user.is_superuser or user.is_staff or has_feature_permission(user, "employee_change_approval", "approve")


def edit_needs_approval(user, employee):
    """Whether `user`'s edits to an existing `employee` must go for approval."""
    if can_approve_changes(user):
        return False
    return not onboarding_open_for_direct_edit(employee)


def pending_request_for(employee):
    return employee.change_requests.filter(status=EmployeeChangeRequest.STATUS_PENDING).first()


# ── value helpers ──────────────────────────────────────────────────────────
def _same_text(a, b):
    """Text from a browser <textarea> arrives with CRLF line breaks while
    the stored copy may have plain LF -- not a change anyone made."""
    def norm(v):
        lines = str(v).replace("\r\n", "\n").replace("\r", "\n").split("\n")
        return "\n".join(line.rstrip() for line in lines).strip()
    return norm(a) == norm(b)


def _raw(value):
    if isinstance(value, models.Model):
        return value.pk
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _display(value):
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, datetime):
        return value.strftime("%d %b %Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d %b %Y")
    if isinstance(value, time):
        return value.strftime("%H:%M")
    return str(value)


def _model_value(model, name, raw):
    field = model._meta.get_field(name)
    return raw if field.is_relation else field.to_python(raw)


# ── build ──────────────────────────────────────────────────────────────────
def build_change_request(original, form, formset, attachment_formset, request):
    """Create a pending EmployeeChangeRequest from validated forms.

    `original` must be a fresh copy of the employee from the database:
    form.is_valid() has already copied the submitted values onto the
    form's own instance. Returns None when nothing actually changed."""
    cr = EmployeeChangeRequest(employee=original, requested_by=request.user)
    files = []

    # Employee fields
    for name in form.changed_data:
        if name == "photo":
            continue
        new = form.cleaned_data.get(name)
        old = getattr(original, name, None)
        if _raw(new) == _raw(old) or (new in (None, "") and old in (None, "")):
            continue
        if isinstance(new, str) and isinstance(old, str) and _same_text(new, old):
            continue
        cr.field_changes[name] = {
            "label": str(form.fields[name].label or name.replace("_", " ").title()),
            "old": _display(old),
            "new": _display(new),
            "raw": _raw(new),
        }
    if "photo" in form.changed_data:
        photo = form.cleaned_data.get("photo")
        if photo is False:
            cr.clear_photo = original.photo.name != ""
        elif photo and hasattr(photo, "image"):
            cr.photo = photo

    # Previous employment rows, and documents uploaded against them
    prev = {"create": [], "update": [], "delete": []}
    for f in formset.forms:
        idx = f.prefix.split("-")[-1]
        cd = getattr(f, "cleaned_data", None) or {}
        pk = f.instance.pk
        row_files = [
            (key, request.FILES[key], request.POST.get(f"attach-{idx}-{key.split('-')[2]}-document_name", ""))
            for key in request.FILES if key.startswith(f"attach-{idx}-")
        ]
        data = {k: _raw(cd.get(k)) for k in PREVIOUS_EMPLOYMENT_FIELDS}
        label = cd.get("employer_name") or getattr(f.instance, "employer_name", "") or "Previous employment"
        if pk and cd.get("DELETE"):
            prev["delete"].append({"id": pk, "label": f.instance.employer_name})
            continue
        if pk:
            key = f"id:{pk}"
            if f.has_changed():
                old = PreviousEmployment.objects.filter(pk=pk).first()
                prev["update"].append({
                    "id": pk, "label": label, "data": data,
                    "old": {k: _display(getattr(old, k, None)) for k in PREVIOUS_EMPLOYMENT_FIELDS},
                    "new": {k: _display(cd.get(k)) for k in PREVIOUS_EMPLOYMENT_FIELDS},
                })
        elif cd and f.has_changed() and not cd.get("DELETE"):
            key = f"new:{idx}"
            prev["create"].append({
                "key": key, "label": label, "data": data,
                "new": {k: _display(cd.get(k)) for k in PREVIOUS_EMPLOYMENT_FIELDS},
            })
        else:
            continue
        for _, upload, doc_name in row_files:
            files.append(EmployeeChangeRequestFile(
                kind=EmployeeChangeRequestFile.KIND_PREVIOUS_EMPLOYMENT, file=upload,
                prev_key=key, document_name=doc_name,
            ))
    if any(prev.values()):
        cr.previous_employment = prev

    # KYC documents
    for af in attachment_formset.forms:
        cd = getattr(af, "cleaned_data", None) or {}
        pk = af.instance.pk
        if pk and cd.get("DELETE"):
            cr.documents_to_delete.append({"id": pk, "label": af.instance.get_display_name() if hasattr(af.instance, "get_display_name") else str(af.instance)})
            continue
        if not af.has_changed() or not cd:
            continue
        if cd.get("file_name") == "other" and not cd.get("other_file_name"):
            raise ChangeRequestError("Please enter a document name for the 'Other' file type in KYC tab.")
        upload = cd.get("file")
        if pk:
            files.append(EmployeeChangeRequestFile(
                kind=EmployeeChangeRequestFile.KIND_KYC,
                file=upload if upload else af.instance.file.name,
                file_name=cd.get("file_name"), other_file_name=cd.get("other_file_name"),
                replaces_attachment_id=pk,
            ))
        elif upload:
            files.append(EmployeeChangeRequestFile(
                kind=EmployeeChangeRequestFile.KIND_KYC, file=upload,
                file_name=cd.get("file_name"), other_file_name=cd.get("other_file_name"),
            ))

    if not (cr.field_changes or cr.photo or cr.clear_photo or cr.previous_employment
            or cr.documents_to_delete or files):
        return None

    with transaction.atomic():
        cr.save()
        for f in files:
            f.request = cr
            f.save()
        log_audit(request.user, AuditLog.Action.EMPLOYEE_CHANGE_REQUESTED, original, employee=original,
                  summary=f"Requested changes to {original} for approval")
    return cr


# ── apply / reject ─────────────────────────────────────────────────────────
@transaction.atomic
def apply_change_request(cr, actor, note=""):
    employee = Employee.objects.select_for_update().get(pk=cr.employee_id)

    for name, change in cr.field_changes.items():
        field = Employee._meta.get_field(name)
        setattr(employee, field.attname, _model_value(Employee, name, change["raw"]))
    if cr.photo:
        employee.photo = cr.photo.name
    elif cr.clear_photo:
        employee.photo = None
    employee.save()

    prev = cr.previous_employment or {}
    created = {}
    for row in prev.get("delete", []):
        PreviousEmployment.objects.filter(pk=row["id"], employee=employee).delete()
    for row in prev.get("update", []):
        record = PreviousEmployment.objects.filter(pk=row["id"], employee=employee).first()
        if record:
            for k, v in row["data"].items():
                setattr(record, k, _model_value(PreviousEmployment, k, v))
            record.save()
    for row in prev.get("create", []):
        created[row["key"]] = PreviousEmployment.objects.create(
            employee=employee,
            **{k: _model_value(PreviousEmployment, k, v) for k, v in row["data"].items()},
        )

    for f in cr.files.all():
        if f.kind == EmployeeChangeRequestFile.KIND_PREVIOUS_EMPLOYMENT:
            if f.prev_key in created:
                target = created[f.prev_key]
            else:
                target = PreviousEmployment.objects.filter(
                    pk=f.prev_key.split(":", 1)[1] if f.prev_key else None, employee=employee,
                ).first()
            if target:
                PreviousEmploymentAttachment.objects.create(
                    previous_employment=target, file=f.file.name, document_name=f.document_name,
                )
        else:
            att = None
            if f.replaces_attachment_id:
                att = EmployeeAttachment.objects.filter(pk=f.replaces_attachment_id, employee=employee).first()
            att = att or EmployeeAttachment(employee=employee)
            att.file = f.file.name
            att.file_name = f.file_name
            att.other_file_name = f.other_file_name
            att.save()

    ids = [d["id"] for d in cr.documents_to_delete]
    if ids:
        EmployeeAttachment.objects.filter(pk__in=ids, employee=employee).delete()

    cr.status = EmployeeChangeRequest.STATUS_APPROVED
    cr.decided_by = actor
    cr.decided_at = timezone.now()
    cr.decision_note = note
    cr.save()
    log_audit(actor, AuditLog.Action.EMPLOYEE_CHANGE_APPROVED, employee, employee=employee,
              summary=f"Approved changes to {employee}",
              changes={k: {"old": v["old"], "new": v["new"]} for k, v in cr.field_changes.items()})
    return employee


@transaction.atomic
def reject_change_request(cr, actor, note=""):
    cr.status = EmployeeChangeRequest.STATUS_REJECTED
    cr.decided_by = actor
    cr.decided_at = timezone.now()
    cr.decision_note = note
    cr.save()
    # Uploaded files were never attached to anything -- remove them.
    for f in cr.files.all():
        if f.file and f.file.name.startswith("employee_change_requests/"):
            f.file.delete(save=False)
    if cr.photo:
        cr.photo.delete(save=False)
    log_audit(actor, AuditLog.Action.EMPLOYEE_CHANGE_REJECTED, cr.employee, employee=cr.employee,
              summary=f"Rejected changes to {cr.employee}" + (f": {note}" if note else ""))
