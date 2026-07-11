"""Centralized payroll-period locking.

Once a PayrollRun is finalized, every record inside its date range becomes
historical and must not be mutated by any other workflow (attendance edits,
correction requests, comp-off requests, leave approvals, LWP overrides, etc.).
This module is the single source of truth that all write paths consult.

Design notes:
    - One company can have many PayrollRuns; a date is "locked" iff at least
      one finalized run for that company covers it.
    - Period overlap uses the standard "ranges overlap when start <= other_end
      AND end >= other_start" rule.
    - Helpers return either the locking run (so callers can include its
      identifier in error messages) or a ready-made JsonResponse.
"""
from django.http import JsonResponse

from ..models import PayrollRun


def get_locking_run(company, check_date):
    """Return the finalized PayrollRun that covers ``check_date`` for
    ``company``, or ``None`` if the date is free to modify.

    A single date is treated as covered when ``start_date <= check_date <= end_date``.
    """
    if not company or not check_date:
        return None
    return (
        PayrollRun.objects
        .filter(
            company=company,
            status=PayrollRun.STATUS_FINALIZED,
            start_date__lte=check_date,
            end_date__gte=check_date,
        )
        .order_by("-end_date")
        .first()
    )


def get_locking_run_for_period(company, start_date, end_date):
    """Return the finalized PayrollRun whose date range overlaps
    ``[start_date, end_date]`` for ``company``, or ``None``.
    """
    if not company or not start_date or not end_date:
        return None
    return (
        PayrollRun.objects
        .filter(
            company=company,
            status=PayrollRun.STATUS_FINALIZED,
            start_date__lte=end_date,
            end_date__gte=start_date,
        )
        .order_by("-end_date")
        .first()
    )


def is_date_locked(company, check_date):
    """Boolean wrapper around :func:`get_locking_run`."""
    return get_locking_run(company, check_date) is not None


def is_period_locked(company, start_date, end_date):
    """Boolean wrapper around :func:`get_locking_run_for_period`."""
    return get_locking_run_for_period(company, start_date, end_date) is not None


def _lock_message(run, action="modify"):
    """Build a consistent, human-readable error message that names the
    locking payroll run."""
    return (
        f"Cannot {action}: this date falls inside the finalized payroll run "
        f"for {run.start_date:%d %b %Y}–{run.end_date:%d %b %Y}. "
        f"Finalized periods are locked and cannot be changed."
    )


def lock_response(run, action="modify", status=400, extra=None):
    """Return a uniform JsonResponse for any view that detects a lock hit.

    Callers should ``return lock_response(run)`` immediately on a hit so the
    rest of the view never runs.
    """
    payload = {
        "success": False,
        "locked": True,
        "error": _lock_message(run, action=action),
        "payroll_run_id": run.id,
    }
    if extra:
        payload.update(extra)
    return JsonResponse(payload, status=status)


def build_date_locked_cache(company_ids):
    """Return a dict mapping ``company_id -> list[(start_date, end_date)]``
    for use inside hot loops (e.g. bulk Excel imports) so each row check is
    O(number-of-finalized-runs) instead of a database query.
    """
    cache = {cid: [] for cid in company_ids if cid}
    if not cache:
        return cache
    rows = PayrollRun.objects.filter(
        company_id__in=cache.keys(),
        status=PayrollRun.STATUS_FINALIZED,
    ).values_list("company_id", "start_date", "end_date")
    for cid, start, end in rows:
        cache.setdefault(cid, []).append((start, end))
    return cache


def date_in_cache(cache, company_id, check_date):
    """Check ``check_date`` against the cache returned by
    :func:`build_date_locked_cache`."""
    if not company_id or not check_date:
        return False
    for start, end in cache.get(company_id, ()):
        if start <= check_date <= end:
            return True
    return False
