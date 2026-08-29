"""
Single write path for AuditLog rows -- every instrumented view calls
log_audit(...) instead of creating AuditLog objects directly, so the
field-population rules (actor bypass for anonymous, employee/company
inference) stay in one place. See website/models.py (AuditLog) for the
field list this backs, and website/permissions_registry.py for the
"audit_log" feature that gates who can view these.
"""
from website.models import AuditLog


def snapshot(instance, field_names):
    """Capture {field: current_value} BEFORE a mutation, to diff() later."""
    return {f: getattr(instance, f) for f in field_names}


def diff(before, instance, field_names):
    """Compare a snapshot() dict against instance's current field values.
    Returns {field: {"old": ..., "new": ...}} for fields that changed,
    skipping unchanged ones. Compares via `!=` (not str()) so
    Decimal('0.00') vs Decimal('0') -- numerically equal, differently
    represented -- doesn't register as a false change; values are only
    stringified afterward, for JSON storage."""
    changed = {}
    for f in field_names:
        old = before.get(f)
        new = getattr(instance, f)
        if old != new:
            changed[f] = {
                "old": str(old) if old is not None else None,
                "new": str(new) if new is not None else None,
            }
    return changed


def log_audit(actor, action, target, *, summary, employee=None, company=None, changes=None):
    """Write one AuditLog row.

    `target` is the model instance the action applies to -- its class name
    and pk become target_type/target_id, and str(target) becomes
    target_repr (captured now so it survives a later rename/delete of the
    target itself).

    `employee`/`company` are inferred from `target` when omitted: if
    `target` has an `employee` attribute that's used, else `target` itself
    if it IS an Employee; company falls back to that employee's company.
    Pass them explicitly for targets (Group, PayrollRun, User) where that
    inference doesn't apply or isn't precise enough.
    """
    if employee is None:
        target_employee_attr = getattr(target, "employee", None)
        if target_employee_attr is not None:
            employee = target_employee_attr
        elif target.__class__.__name__ == "Employee":
            employee = target
    if company is None:
        company = getattr(employee, "company", None) if employee is not None else getattr(target, "company", None)

    AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        target_type=target.__class__.__name__,
        target_id=getattr(target, "pk", None),
        target_repr=str(target)[:200],
        employee=employee,
        company=company,
        summary=summary,
        changes=changes or {},
    )
