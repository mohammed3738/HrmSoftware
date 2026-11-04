"""Field duty -> attendance.

A field employee may never touch a punch machine. Their day exists only as
the duty they logged, so the duty has to be able to stand in for the punch:

    "if there is no in punch then the starting time would become the punch
     in time, and the end time if latest would become the punch out time"

That is the whole of this module, and the two words that carry the weight
are *no* and *latest*. It fills gaps and extends the day; it never
overwrites. Four things are therefore left strictly alone:

* an in-time that already exists, from any source. Somebody who punched in
  at the office at 09:30 and left for a site at 11:00 worked from 09:30.
* an out-time that is already later than this duty's end. A duty that ended
  at 16:00 must not shorten a day that already ran to 18:40.
* a row with `times_locked` set -- an approved correction or an Excel
  upload, i.e. a decision a human made deliberately (see
  services/biometric_sync.py, which skips these for the same reason).
* any date inside a finalized payroll run. Those periods are history and
  every write path in this app consults utils/payroll_lock.

The reverse direction needs no special handling. biometric_sync's
derive_day_times already honours "an in-time once set never moves" and "an
out-time only moves forward", so a time written here survives a later sync,
while a real device punch can still extend the day's out-time past it.
"""
import datetime
import logging

from django.db import transaction
from django.utils import timezone

from ..models import Attendance
from ..utils.payroll_lock import get_locking_run

logger = logging.getLogger(__name__)

MIDNIGHT = datetime.time(0, 0, 0)


def _is_blank_time_pair(in_time, out_time):
    """This app's attendance uploads write 00:00/00:00 to mean "no punch".

    calculate_status() already recognises that pair as absent, so a field
    duty should treat it as the gap it is rather than as an in-time of
    midnight it must not overwrite.
    """
    return in_time == MIDNIGHT and out_time == MIDNIGHT


def _local_time(moment):
    """The clock time to write onto an attendance row.

    Truncated to the second: every other source of a punch time here (the
    Excel upload, the biometric feed, an approved correction) is whole
    seconds, and a 10:09:43.078158 in-time among them reads as a glitch
    rather than as a more precise measurement.
    """
    return timezone.localtime(moment).time().replace(microsecond=0)


def apply_to_attendance(duty):
    """Fill the day's missing punch times from `duty`.

    Safe to call repeatedly -- it is called once when a duty starts and
    again when it ends, and calling it twice with the same duty changes
    nothing the second time.

    Returns a dict describing what happened, for the caller to report:

        {"applied": bool, "in_time": time|None, "out_time": time|None,
         "skipped": str|None}

    `skipped` is a short human-readable reason when nothing was written,
    so a view can say "your attendance was not updated, because ..."
    instead of silently doing nothing.
    """
    result = {"applied": False, "in_time": None, "out_time": None, "skipped": None}

    employee = duty.employee
    day = duty.duty_date

    locking_run = get_locking_run(employee.company, day)
    if locking_run:
        result["skipped"] = (
            f"{day:%d %b %Y} is inside the finalized payroll run for "
            f"{locking_run.start_date:%d %b %Y}-{locking_run.end_date:%d %b %Y}, "
            "which is locked."
        )
        return result

    with transaction.atomic():
        attendance, _created = Attendance.objects.select_for_update().get_or_create(
            employee=employee, date=day,
        )

        if attendance.times_locked:
            result["skipped"] = (
                "the attendance for this day was set by hand (an approved "
                "correction or an upload), so it was left as it is."
            )
            return result

        current_in = attendance.in_time
        current_out = attendance.out_time
        if _is_blank_time_pair(current_in, current_out):
            current_in = current_out = None

        new_in, new_out = current_in, current_out

        # -- in-time: only when there is none ---------------------------
        if current_in is None:
            new_in = _local_time(duty.started_at)

        # -- out-time: only forward -------------------------------------
        if duty.ended_at is not None:
            ended_local = timezone.localtime(duty.ended_at)
            if ended_local.date() != day:
                # The duty ran past midnight. Writing its end clock time onto
                # the start date would read as an out-time *before* the
                # in-time, and overnight handling for real shifts belongs to
                # the shift roster, not here. Leave the out-time alone and say
                # so rather than record something misleading.
                result["skipped"] = (
                    "the duty ended on the next day, so the out-time was left "
                    "for the shift roster to resolve."
                )
            else:
                candidate = ended_local.time().replace(microsecond=0)
                if current_out is None or candidate > current_out:
                    new_out = candidate

        if (new_in, new_out) == (current_in, current_out):
            if result["skipped"] is None:
                result["skipped"] = "the day already had its punch times."
            return result

        attendance.in_time = new_in
        attendance.out_time = new_out
        # Deliberately NOT times_locked: a real device punch is better
        # evidence than a self-reported one, and biometric_sync can only
        # extend what is written here, never shorten it.
        attendance.save()  # recomputes status via Attendance.save()

        duty.filled_attendance_in = duty.filled_attendance_in or (
            current_in is None and new_in is not None
        )
        duty.filled_attendance_out = duty.filled_attendance_out or (
            new_out != current_out and new_out is not None
        )
        duty.save(update_fields=["filled_attendance_in", "filled_attendance_out",
                                 "status", "updated_at"])

        result.update({
            "applied": True,
            "in_time": new_in,
            "out_time": new_out,
            "skipped": None,
        })

    # Attendance counts feed the leave balance, so it is refreshed after the
    # write -- outside the transaction, and never allowed to fail the punch
    # the employee just made.
    try:
        from ..signals import recalculate_leave_balance_for_employee
        recalculate_leave_balance_for_employee(employee, day)
    except Exception:
        logger.exception("Field duty: leave balance recalc failed for %s", employee)

    return result
