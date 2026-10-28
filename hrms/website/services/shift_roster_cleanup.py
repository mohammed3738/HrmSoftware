"""Clearing finished rotations out of the active Shift Roster.

Night duty rotates, so the roster fills up with entries whose dates have
gone by. Those are history, not plans, and leaving them in the active list
makes "who is on nights this week" harder to read every week.

What this does NOT do is change any attendance. An entry archived here is
flagged auto_archived, and the biometric sync keeps honouring auto-archived
entries for the dates they covered (see services/biometric_sync.py,
NightShiftResolver) -- so recalculating an old night shift still reaches the
same answer it did at the time. That is the whole reason for having a flag
separate from is_active: a MANUAL archive is this app's soft delete and does
take the entry out of the sync's reckoning, because somebody decided it was
wrong.

Entries are left alone for a grace period after their end date, so a
rotation that only just finished stays visible while the sync is still
re-reading those days.
"""
import datetime
import logging

from django.conf import settings
from django.utils.timezone import now

from ..models import ShiftAssignment

logger = logging.getLogger(__name__)

# Long enough that a just-finished rotation stays in the active roster while
# the HRMS is still re-reading those dates (BIOMETRIC_SYNC_LOOKBACK_DAYS),
# with room to spare for a weekend in between.
DEFAULT_GRACE_DAYS = 7


def grace_days():
    return max(0, int(getattr(settings, "SHIFT_ROSTER_ARCHIVE_AFTER_DAYS",
                              DEFAULT_GRACE_DAYS)))


def past_assignments(today=None, grace=None):
    """Active roster entries whose end date went by more than the grace
    period ago."""
    today = today or now().date()
    grace = grace_days() if grace is None else grace
    cutoff = today - datetime.timedelta(days=grace)
    return ShiftAssignment.objects.filter(is_active=True, end_date__lt=cutoff)


def archive_past_assignments(today=None, grace=None, dry_run=False):
    """Move finished rotations out of the active roster.

    Returns (count, rows) -- rows being a short description of each, for a
    command or task to print.
    """
    rows = list(
        past_assignments(today=today, grace=grace)
        .select_related("employee")
        .order_by("end_date", "employee__employee_code")
    )
    described = [
        {
            "id": row.id,
            "employee_code": row.employee.employee_code,
            "employee": str(row.employee),
            "shift_name": row.shift_name,
            "start_date": row.start_date,
            "end_date": row.end_date,
            "is_night_shift": row.is_night_shift,
        }
        for row in rows
    ]
    if dry_run or not rows:
        return len(rows), described

    # update() rather than per-row save(): nothing on this model needs its
    # save() to run, and the roster can hold thousands of past entries.
    ShiftAssignment.objects.filter(id__in=[row.id for row in rows]).update(
        is_active=False, auto_archived=True,
    )
    logger.info("Shift roster: archived %d finished rotation(s)", len(rows))
    return len(rows), described
