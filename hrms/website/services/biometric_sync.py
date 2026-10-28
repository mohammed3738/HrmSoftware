"""Turning raw biometric punches into Attendance in/out times.

The punch machine (eSSL eTimeTrackLite, on its own Windows server) only
knows "user 14 touched the reader at 09:58:12". Deciding which of a day's
punches is the in-time and which is the out-time is policy, and it lives
here so the Windows agent, the scheduled task, the management command and
the Biometric Sync page all apply exactly the same rules.

The rules
---------
Day shift, for date D:
    in-time  = the first punch of D, but only while the day has no in-time
               yet -- an in-time already recorded (uploaded, corrected, or
               set by an earlier run) is never moved.
    out-time = the last punch of D, refreshed on every run: an employee who
               punched out at 18:02 and again at 19:40 gets the later one as
               soon as the next run sees it.

Night shift, for date D (duty starts on D and ends on D+1):
    in-time  = the LAST punch of D
    out-time = the FIRST punch of D+1
    So a 23 Oct night shift is "last punch of 23 Oct -> first punch of
    24 Oct", and 24 Oct then starts again at its own last punch. Which
    employees are on nights comes from the Shift Roster for those dates when
    one covers them, otherwise from Employee.is_night_shift.

What is never touched
---------------------
    - days whose times were set by hand (Attendance.times_locked): an
      approved correction request or an Excel upload
    - days inside a finalized payroll run
    - days before the employee's date of joining
    - employees who have left/are archived

Each of those is counted as "skipped" rather than silently passed over, so
the Biometric Sync page can say why a day did not move.
"""
import datetime
import logging
import re
from collections import defaultdict

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils.timezone import now

from ..models import (
    Attendance,
    BiometricPunch,
    BiometricSyncRun,
    Employee,
    ShiftAssignment,
)
from ..utils.payroll_lock import get_locking_run

logger = logging.getLogger(__name__)

ACTIVE_EMPLOYEE_STATUSES = ("Active", "Pending")


# ── configuration ─────────────────────────────────────────────────────────

def _parse_hhmm(value, fallback):
    """'12:00' -> datetime.time(12, 0). Falls back rather than raising: a
    typo in .env must not take the whole sync down."""
    try:
        hour, minute = (int(part) for part in str(value).split(":", 1))
        return datetime.time(hour, minute)
    except (TypeError, ValueError):
        logger.warning("Biometric sync: ignoring unreadable time %r, using %s", value, fallback)
        return fallback


def lookback_days():
    # Two days is the floor, not a preference: rebuilding 23 Oct for a night
    # employee needs 24 Oct's punches in the window as well.
    return max(2, int(getattr(settings, "BIOMETRIC_SYNC_LOOKBACK_DAYS", 3)))


def max_shift_hours():
    return float(getattr(settings, "BIOMETRIC_MAX_SHIFT_HOURS", 16))


def night_in_from():
    return _parse_hhmm(getattr(settings, "BIOMETRIC_NIGHT_IN_FROM", "12:00"), datetime.time(12, 0))


def night_out_until():
    return _parse_hhmm(getattr(settings, "BIOMETRIC_NIGHT_OUT_UNTIL", "12:00"), datetime.time(12, 0))


# ── employee matching ─────────────────────────────────────────────────────

def _normalize_code(value):
    """Match codes the way a human would: ignoring case, surrounding space
    and the leading zeros the device pads its user IDs with (the reader
    reports '0014' for the employee HR filed as '14')."""
    if not value:
        return ""
    text = str(value).strip().upper()
    stripped = text.lstrip("0")
    return stripped or text


def build_employee_index():
    """Lookup from every code an employee could be known by to that
    employee. Built once per run -- a month of punches is tens of thousands
    of rows and must not become a query each.

    Explicit mappings win: if somebody filled in
    Employee.biometric_device_user_id, that is the answer, even when another
    employee's code happens to normalize to the same string.
    """
    index = {}
    employees = Employee.objects.filter(status__in=ACTIVE_EMPLOYEE_STATUSES).only(
        "id", "employee_code", "biometric_device_user_id", "is_night_shift",
        "date_of_joining", "company_id", "branch_id", "shift_start_time", "shift_end_time",
        "first_name", "last_name", "status", "week_off_day", "use_department_defaults",
    )
    by_code = []
    for employee in employees:
        if employee.employee_code:
            by_code.append((_normalize_code(employee.employee_code), employee))
        if employee.biometric_device_user_id:
            # Added after the loop so it cannot be overwritten by a code match.
            index[_normalize_code(employee.biometric_device_user_id)] = employee
    for key, employee in by_code:
        index.setdefault(key, employee)
    return index


def match_employee(index, device_user_id, employee_code=""):
    """The employee a punch belongs to, or None. The eSSL employee code is
    tried first: the agent resolves it by joining DeviceLogs to the eSSL
    Employees table, and it is the code HR actually recognises."""
    for candidate in (employee_code, device_user_id):
        employee = index.get(_normalize_code(candidate))
        if employee is not None:
            return employee
    return None


# ── storing punches ───────────────────────────────────────────────────────

def future_punch_cutoff():
    """The latest punch date worth believing.

    A punch dated beyond this is a reader whose clock is wrong, not
    attendance -- this installation's history contains one dated 31 December.
    Storing it would build an attendance row on a date nobody has worked
    yet, which is then easy to miss and awkward to unpick.
    """
    days = int(getattr(settings, "BIOMETRIC_FUTURE_PUNCH_TOLERANCE_DAYS", 1))
    return now().date() + datetime.timedelta(days=max(0, days))


def store_punches(records):
    """Save a batch of punches, ignoring any already held.

    `records` are dicts as the agent sends them: device_user_id,
    employee_code, employee_name, punch_date (YYYY-MM-DD), punch_time
    (HH:MM:SS), device_id, direction, source_log_id.

    Returns (stored, unmatched, dates_by_employee, errors) where
    dates_by_employee maps an Employee to the set of punch dates it gained
    punches on -- the days whose attendance now needs rebuilding.
    """
    index = build_employee_index()
    to_create = []
    dates_by_employee = defaultdict(set)
    unmatched = 0
    errors = []
    cutoff = future_punch_cutoff()
    future = []

    for record in records:
        try:
            device_user_id = str(record.get("device_user_id") or "").strip()
            punch_date = _as_date(record.get("punch_date"))
            punch_time = _as_time(record.get("punch_time"))
            if not device_user_id or punch_date is None or punch_time is None:
                errors.append(f"Incomplete punch skipped: {record!r}")
                continue

            if punch_date > cutoff:
                # Rejected rather than stored: see future_punch_cutoff().
                future.append(f"{device_user_id} @ {punch_date} {punch_time}")
                continue

            employee_code = str(record.get("employee_code") or "").strip()
            employee = match_employee(index, device_user_id, employee_code)
            if employee is None:
                unmatched += 1
            else:
                dates_by_employee[employee].add(punch_date)

            to_create.append(BiometricPunch(
                device_user_id=device_user_id[:50],
                employee_code=employee_code[:50],
                employee_name=str(record.get("employee_name") or "").strip()[:255],
                employee=employee,
                punch_date=punch_date,
                punch_time=punch_time,
                device_id=_as_int(record.get("device_id")),
                direction=str(record.get("direction") or "").strip()[:32],
                source_log_id=_as_int(record.get("source_log_id")),
            ))
        except Exception as exc:  # one malformed row must not lose the batch
            logger.exception("Biometric sync: punch rejected")
            errors.append(f"{exc}")

    stored = 0
    if to_create:
        # ignore_conflicts leans on the (device_user_id, punch_date,
        # punch_time) unique constraint: every run deliberately re-sends an
        # overlapping window, so most of a batch is usually already held.
        # bulk_create's return value says nothing useful about which rows
        # were skipped, so the row count before and after is what gets
        # reported.
        before = BiometricPunch.objects.count()
        BiometricPunch.objects.bulk_create(
            to_create, batch_size=1000, ignore_conflicts=True,
        )
        stored = BiometricPunch.objects.count() - before

    if future:
        errors.append(
            f"{len(future)} punch(es) dated after {cutoff} were rejected -- a punch "
            f"in the future means a device clock is wrong, not attendance. "
            f"First few: {', '.join(future[:5])}"
        )

    return stored, unmatched, dates_by_employee, errors


def relink_unmatched():
    """Attach punches that arrived before their employee existed (or before
    somebody filled in the right code). Returns
    (linked, dates_by_employee)."""
    index = build_employee_index()
    pending = BiometricPunch.objects.filter(employee__isnull=True)
    dates_by_employee = defaultdict(set)
    linked = []
    for punch in pending.iterator(chunk_size=2000):
        employee = match_employee(index, punch.device_user_id, punch.employee_code)
        if employee is None:
            continue
        punch.employee = employee
        linked.append(punch)
        dates_by_employee[employee].add(punch.punch_date)
    if linked:
        BiometricPunch.objects.bulk_update(linked, ["employee"], batch_size=1000)
    return len(linked), dates_by_employee


def _as_date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if not value:
        return None
    return datetime.date.fromisoformat(str(value)[:10])


def _as_time(value):
    if isinstance(value, datetime.datetime):
        return value.time().replace(microsecond=0)
    if isinstance(value, datetime.time):
        return value.replace(microsecond=0)
    if not value:
        return None
    text = str(value).strip()
    if " " in text:  # a whole "YYYY-MM-DD HH:MM:SS" came through
        text = text.split(" ", 1)[1]
    if "T" in text:
        text = text.split("T", 1)[1]
    return datetime.time.fromisoformat(text[:8]).replace(microsecond=0)


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ── night shift resolution ────────────────────────────────────────────────

def _crosses_midnight(start, end):
    return bool(start and end and start > end)


# Words that mark a rostered shift as overnight when nothing more definite
# is available. A fallback for rosters entered before ShiftAssignment grew
# its own is_night_shift tick -- not something to rely on for new ones,
# since "B Shift" or "Shift 3" say nothing either way.
_NIGHT_NAME_HINTS = ("night", "overnight", "graveyard", "nite")


class NightShiftResolver:
    """Whether an employee is on nights on a given date.

    THE SHIFT ROSTER WINS wherever it covers the date. That is the whole
    point of rostering: night duty rotates, so who is on nights changes week
    to week, and a standing tick on the employee cannot express that.
    Employee.is_night_shift is only the fallback for staff who are
    permanently on nights and are never rostered.

    Within a roster entry the checks run most-definite first:

        1. its own is_night_shift tick      -- HR said so outright
        2. timings that cross midnight      -- 22:00-07:00 says so itself
        3. a name containing "night" etc.   -- legacy entries, best effort
        4. ordinary daytime timings         -- a positive "not nights",
                                               which overrides the standing
                                               tick for these dates

    An entry that matches none of those is no answer at all, so the next
    entry is tried and then the employee's own setting -- rather than
    silently reading it as a day shift, which would hand a night employee a
    nonsense in-time.

    Rosters are fetched once for the whole window, not per employee-day.
    """

    def __init__(self, employees, from_date, to_date):
        self._assignments = defaultdict(list)
        if not employees:
            return
        # is_active OR auto_archived, deliberately. An entry archived by the
        # nightly tidy-up (its dates have simply gone by) is still the true
        # record of what the roster said for those dates, and recalculating
        # them later must reach the same answer. Only a MANUAL archive --
        # this app's soft delete, meaning somebody decided the entry was
        # wrong -- takes an entry out of the sync's reckoning.
        rows = ShiftAssignment.objects.filter(
            Q(is_active=True) | Q(auto_archived=True),
            employee__in=employees,
            start_date__lte=to_date,
            end_date__gte=from_date,
        ).only("employee_id", "shift_name", "start_date", "end_date",
               "shift_start_time", "shift_end_time", "is_night_shift")
        for assignment in rows:
            self._assignments[assignment.employee_id].append(assignment)

    @staticmethod
    def _from_assignment(assignment):
        """True/False from a roster entry, or None when it does not say."""
        if assignment.is_night_shift:
            return True
        if _crosses_midnight(assignment.shift_start_time, assignment.shift_end_time):
            return True
        name = (assignment.shift_name or "").lower()
        if any(hint in name for hint in _NIGHT_NAME_HINTS):
            return True
        if assignment.shift_start_time and assignment.shift_end_time:
            return False
        return None

    def is_night(self, employee, day):
        for assignment in self._assignments.get(employee.id, ()):
            if assignment.start_date <= day <= assignment.end_date:
                answer = self._from_assignment(assignment)
                if answer is not None:
                    return answer
        if employee.is_night_shift:
            return True
        return _crosses_midnight(employee.shift_start_time, employee.shift_end_time)


# ── deriving in/out times ─────────────────────────────────────────────────

def _span_hours(day, in_time, out_day, out_time):
    start = datetime.datetime.combine(day, in_time)
    end = datetime.datetime.combine(out_day, out_time)
    return (end - start).total_seconds() / 3600.0


def derive_day_times(day, punches_by_date, is_night, existing_in=None, existing_out=None):
    """The in/out time a date should end up with, as (in_time, out_time).

    `punches_by_date` maps a date to that date's punch times, sorted.
    (None, None) means "no usable punch" -- the caller leaves the day alone
    rather than blanking it.
    """
    today_punches = punches_by_date.get(day) or []

    if is_night:
        if not today_punches:
            return None, None
        in_time = today_punches[-1]
        # A lone morning punch is the previous night's out-punch, already
        # consumed by that date; it is not an in-time for this one.
        if in_time < night_in_from():
            return None, None

        out_time = None
        next_punches = punches_by_date.get(day + datetime.timedelta(days=1)) or []
        if next_punches:
            candidate = next_punches[0]
            if candidate < night_out_until() and _span_hours(
                day, in_time, day + datetime.timedelta(days=1), candidate
            ) <= max_shift_hours():
                out_time = candidate
        # An out-time already recorded is never thrown away because this
        # run could not derive one -- that would turn a complete day back
        # into a missing out-punch.
        return in_time, out_time or existing_out

    if not today_punches:
        return None, None

    # Day shift. An in-time already on the record stands -- only the first
    # run of a day establishes it.
    in_time = existing_in or today_punches[0]
    out_time = existing_out
    last = today_punches[-1]
    if last > in_time and _span_hours(day, in_time, day, last) <= max_shift_hours():
        # Refresh the out-time whenever a later punch has appeared; an
        # earlier one is a re-read of the same window and changes nothing.
        if out_time is None or last > out_time:
            out_time = last
    return in_time, out_time


# ── rebuilding attendance ─────────────────────────────────────────────────

def _punches_for(employees, from_date, to_date):
    """{employee_id: {date: [time, ...]}} over the window, plus one extra
    day at the end so a night shift starting on to_date can still find its
    out-punch."""
    rows = BiometricPunch.objects.filter(
        employee__in=employees,
        punch_date__gte=from_date,
        punch_date__lte=to_date + datetime.timedelta(days=1),
    ).values_list("employee_id", "punch_date", "punch_time").order_by("punch_date", "punch_time")

    by_employee = defaultdict(lambda: defaultdict(list))
    for employee_id, punch_date, punch_time in rows:
        by_employee[employee_id][punch_date].append(punch_time)
    return by_employee


def rebuild_attendance(dates_by_employee, force=False):
    """Recompute in/out times for the given employee -> {dates} mapping.

    Returns a dict of counters: created, updated, skipped, unchanged.
    """
    counters = {"created": 0, "updated": 0, "skipped": 0, "unchanged": 0}
    if not dates_by_employee:
        return counters

    employees = list(dates_by_employee.keys())
    all_dates = {day for days in dates_by_employee.values() for day in days}
    if not all_dates:
        return counters
    from_date, to_date = min(all_dates), max(all_dates)

    punches = _punches_for(employees, from_date, to_date)
    resolver = NightShiftResolver(employees, from_date, to_date)

    existing = {
        (row.employee_id, row.date): row
        for row in Attendance.objects.filter(
            employee__in=employees, date__gte=from_date, date__lte=to_date,
        ).select_related("employee", "employee__company", "employee__branch")
    }

    # Deferred so the import graph stays one-directional (signals imports
    # from services, not the other way round).
    from ..signals import recalculate_leave_balance_for_employee, suspend_leave_balance_auto_recalc

    touched = {}
    with transaction.atomic(), suspend_leave_balance_auto_recalc():
        for employee in employees:
            employee_punches = punches.get(employee.id, {})
            for day in sorted(dates_by_employee[employee]):
                attendance = existing.get((employee.id, day))

                if attendance is not None and attendance.times_locked and not force:
                    counters["skipped"] += 1
                    continue
                if employee.date_of_joining and day < employee.date_of_joining:
                    counters["skipped"] += 1
                    continue
                if get_locking_run(employee.company, day):
                    counters["skipped"] += 1
                    continue

                is_night = resolver.is_night(employee, day)
                # Forcing means "redo this day from the punches alone". The
                # times already on the record are not passed in, so neither
                # the "an in-time once set never moves" rule nor the
                # "an out-time only moves forward" rule can preserve the
                # manual values the caller asked to discard -- otherwise
                # --force would clear the lock and change nothing.
                in_time, out_time = derive_day_times(
                    day,
                    employee_punches,
                    is_night,
                    existing_in=None if attendance is None or force else attendance.in_time,
                    existing_out=None if attendance is None or force else attendance.out_time,
                )
                if in_time is None:
                    counters["unchanged"] += 1
                    continue

                if attendance is None:
                    attendance = Attendance(employee=employee, date=day)
                    attendance.in_time = in_time
                    attendance.out_time = out_time
                    attendance.save()
                    existing[(employee.id, day)] = attendance
                    counters["created"] += 1
                elif (attendance.in_time, attendance.out_time) != (in_time, out_time):
                    attendance.in_time = in_time
                    attendance.out_time = out_time
                    attendance.save()
                    counters["updated"] += 1
                else:
                    counters["unchanged"] += 1
                    continue

                previous = touched.get(employee.id)
                if previous is None or day < previous[1]:
                    touched[employee.id] = (employee, day)

    # Leave balance depends on attendance counts, so it is refreshed once
    # per employee touched rather than on every save above.
    for employee, min_date in touched.values():
        try:
            recalculate_leave_balance_for_employee(employee, min_date)
        except Exception:
            logger.exception("Biometric sync: leave balance recalc failed for %s", employee)

    return counters


# ── entry points ──────────────────────────────────────────────────────────

def ingest(records, source=BiometricSyncRun.SOURCE_AGENT, force=False):
    """Store a batch of punches and rebuild the attendance they affect.
    This is what the agent's POST, the scheduled task and the management
    command all end up calling. Returns the BiometricSyncRun it recorded."""
    run = BiometricSyncRun.objects.create(source=source, status=BiometricSyncRun.STATUS_RUNNING)
    records = list(records or [])
    run.punches_received = len(records)
    try:
        stored, unmatched, dates_by_employee, errors = store_punches(records)

        # Punches whose employee showed up later still need their day built.
        relinked, relinked_dates = relink_unmatched()
        for employee, days in relinked_dates.items():
            dates_by_employee[employee].update(days)

        # Rebuilding date D for a night employee also settles D-1, whose
        # out-time is D's first punch.
        expanded = {
            employee: _with_neighbours(days)
            for employee, days in dates_by_employee.items()
        }
        counters = rebuild_attendance(expanded, force=force)

        if records:
            dates = [_as_date(r.get("punch_date")) for r in records]
            dates = [day for day in dates if day]
            if dates:
                run.from_date, run.to_date = min(dates), max(dates)

        run.punches_stored = stored
        run.punches_unmatched = BiometricPunch.objects.filter(employee__isnull=True).count()
        run.attendance_created = counters["created"]
        run.attendance_updated = counters["updated"]
        run.attendance_skipped = counters["skipped"]
        run.status = BiometricSyncRun.STATUS_SUCCESS
        notes = []
        if unmatched:
            notes.append(f"{unmatched} punch(es) in this batch matched no employee.")
        if relinked:
            notes.append(f"{relinked} earlier unmatched punch(es) linked to an employee.")
        notes.extend(errors[:20])
        run.message = "\n".join(notes)
    except Exception as exc:
        logger.exception("Biometric sync failed")
        run.status = BiometricSyncRun.STATUS_FAILED
        run.message = str(exc)
        raise
    finally:
        run.finished_at = now()
        run.save()
    return run


def _with_neighbours(days):
    """The day before each date as well. A punch on 24 Oct is the out-time
    of a night employee's 23 Oct, so 23 Oct has to be rebuilt too."""
    expanded = set()
    for day in days:
        expanded.add(day)
        expanded.add(day - datetime.timedelta(days=1))
    return expanded


def resync_window(from_date=None, to_date=None, employees=None, source=BiometricSyncRun.SOURCE_MANUAL, force=False):
    """Rebuild attendance from punches already stored, without fetching
    anything. This is the "Rebuild from stored punches" button and what the
    scheduled task falls back to: the agent pushes punches on its own
    timetable, and this turns whatever has arrived into attendance.
    """
    today = now().date()
    if to_date is None:
        to_date = today
    if from_date is None:
        from_date = to_date - datetime.timedelta(days=lookback_days())

    run = BiometricSyncRun.objects.create(
        source=source, status=BiometricSyncRun.STATUS_RUNNING,
        from_date=from_date, to_date=to_date,
    )
    try:
        relinked, _ = relink_unmatched()

        punch_rows = BiometricPunch.objects.filter(
            employee__isnull=False,
            punch_date__gte=from_date,
            punch_date__lte=to_date + datetime.timedelta(days=1),
        )
        if employees:
            punch_rows = punch_rows.filter(employee__in=employees)

        dates_by_employee = defaultdict(set)
        employee_cache = {}
        for employee_id, punch_date in punch_rows.values_list("employee_id", "punch_date").distinct():
            dates_by_employee[employee_id].add(punch_date)
        if dates_by_employee:
            employee_cache = {
                employee.id: employee
                for employee in Employee.objects.filter(
                    id__in=dates_by_employee.keys(), status__in=ACTIVE_EMPLOYEE_STATUSES,
                )
            }

        work = {}
        for employee_id, days in dates_by_employee.items():
            employee = employee_cache.get(employee_id)
            if employee is None:  # left / archived since the punch landed
                continue
            in_window = {day for day in _with_neighbours(days) if from_date <= day <= to_date}
            if in_window:
                work[employee] = in_window

        counters = rebuild_attendance(work, force=force)

        run.punches_received = punch_rows.count()
        run.punches_unmatched = BiometricPunch.objects.filter(employee__isnull=True).count()
        run.attendance_created = counters["created"]
        run.attendance_updated = counters["updated"]
        run.attendance_skipped = counters["skipped"]
        run.status = BiometricSyncRun.STATUS_SUCCESS
        run.message = f"{relinked} unmatched punch(es) linked." if relinked else ""
    except Exception as exc:
        logger.exception("Biometric resync failed")
        run.status = BiometricSyncRun.STATUS_FAILED
        run.message = str(exc)
        raise
    finally:
        run.finished_at = now()
        run.save()
    return run


def latest_punch_date():
    """The newest punch date held, so the agent can ask where to resume
    after it loses its own state file."""
    newest = BiometricPunch.objects.order_by("-punch_date", "-punch_time").first()
    return newest.punch_date if newest else None


# ── optional direct pull (same-LAN machines only) ─────────────────────────

_MONTH_TABLE_RE = re.compile(r"^DeviceLogs(_\d{1,2}_\d{4})?$", re.I)


def _month_table_names(since, until):
    """DeviceLogs_<month>_<year> names covering the window, inclusive."""
    names = []
    year, month = since.year, since.month
    while (year, month) <= (until.year, until.month):
        names.append("DeviceLogs_%d_%d" % (month, year))
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return names


def _punch_tables_present(cursor):
    """{lowercased name: actual name} for every real punch table. Names come
    from the server and are re-checked against _MONTH_TABLE_RE, so nothing
    but a real DeviceLogs table can reach the query text."""
    cursor.execute(
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_SCHEMA = 'dbo' AND TABLE_TYPE = 'BASE TABLE' "
        "AND (TABLE_NAME = 'DeviceLogs' OR TABLE_NAME LIKE 'DeviceLogs[_]%')"
    )
    present = {row[0] for row in cursor.fetchall() if _MONTH_TABLE_RE.match(row[0])}
    return {name.lower(): name for name in present}


def _existing_punch_tables(cursor, since, until, include_buffer=False):
    """The punch tables to read for this window.

    Only the monthly DeviceLogs_<month>_<year> tables by default, matching
    the agent: that is where eTimeTrackLite keeps punches, and
    dbo.DeviceLogs is a staging buffer it empties as it archives.
    BIOMETRIC_MSSQL_READ_BUFFER adds the buffer back for an installation
    that leaves punches sitting in it.
    """
    lowered = _punch_tables_present(cursor)

    tables = []
    if include_buffer and "devicelogs" in lowered:
        tables.append(lowered["devicelogs"])
    for wanted in _month_table_names(since, until):
        actual = lowered.get(wanted.lower())
        if actual:
            tables.append(actual)
    return tables


def _stranded_buffer_rows(cursor):
    """Punches sitting unarchived in dbo.DeviceLogs, or None if that table is
    absent. Normally 0; worth checking so that skipping the buffer can never
    be the silent reason a punch went missing."""
    if "devicelogs" not in _punch_tables_present(cursor):
        return None
    cursor.execute("SELECT COUNT(*) FROM dbo.DeviceLogs")
    return cursor.fetchone()[0]


def mssql_connection_string():
    """ODBC connection string for the eSSL SQL Server, from the
    BIOMETRIC_MSSQL_* settings.

    Nothing has to be created on the eSSL side to use this: either Windows
    Authentication (BIOMETRIC_MSSQL_TRUSTED_CONNECTION, which stores no
    password but only works where the Windows account is trusted, i.e. on
    the machine itself) or the SQL login eTimeTrackLite already uses --
    its own Settings.txt names it, and reusing it adds no new user.
    """
    host = getattr(settings, "BIOMETRIC_MSSQL_HOST", "")
    if not host:
        raise RuntimeError("BIOMETRIC_MSSQL_HOST is not set, so there is no SQL Server to pull from.")

    parts = [
        f"DRIVER={{{settings.BIOMETRIC_MSSQL_DRIVER}}}",
        f"SERVER={host}",
        f"DATABASE={settings.BIOMETRIC_MSSQL_DATABASE}",
        # The eSSL instance uses a self-signed certificate; driver 18
        # encrypts by default and would otherwise refuse it.
        "TrustServerCertificate=yes",
    ]
    if getattr(settings, "BIOMETRIC_MSSQL_TRUSTED_CONNECTION", False):
        parts.append("Trusted_Connection=yes")
    else:
        parts.append(f"UID={settings.BIOMETRIC_MSSQL_USER}")
        parts.append(f"PWD={settings.BIOMETRIC_MSSQL_PASSWORD}")
    return ";".join(parts)


def pull_from_sql_server(from_date=None, to_date=None, source=BiometricSyncRun.SOURCE_COMMAND, force=False):
    """Read punches straight out of the eSSL SQL Server and ingest them.

    Only usable from a machine that can actually reach that SQL Server (the
    development PC on the same LAN) and that has pyodbc plus an ODBC driver.
    The production Ubuntu server has no route to it, which is why the
    Windows agent pushes instead -- see ESSL_INTEGRATION_GUIDE.txt.
    """
    try:
        import pyodbc
    except ImportError as exc:
        raise RuntimeError(
            "Direct pull needs pyodbc (pip install pyodbc) and an ODBC driver. "
            "On the Ubuntu server use the Windows agent push instead."
        ) from exc

    today = now().date()
    if to_date is None:
        to_date = today
    if from_date is None:
        from_date = to_date - datetime.timedelta(days=lookback_days())

    # eTimeTrackLite keeps punches in dbo.DeviceLogs only until they are
    # archived into a table per month (dbo.DeviceLogs_10_2026 and so on),
    # whose primary key is (UserId, LogDate) -- the punch identity. On a
    # tidy installation dbo.DeviceLogs is empty, so reading it alone finds
    # nothing at all. Both are read, and a punch that appears in both is
    # de-duplicated by BiometricPunch's unique constraint.
    #
    # The agent (scripts/essl_agent/essl_punch_agent.py) does the same thing
    # for the same reason. It is deliberately a separate copy: the agent runs
    # standalone on the Windows server with no Django on it.
    branch = """
        SELECT  l.UserId, l.LogDate, l.DeviceId,
                COALESCE(l.Direction, l.AttDirection) AS Direction,
                l.DeviceLogId
        FROM    dbo.[{table}] AS l
        WHERE   l.LogDate >= ? AND l.LogDate < ?
    """
    records = []
    until = to_date + datetime.timedelta(days=2)
    with pyodbc.connect(mssql_connection_string(), timeout=30) as connection:
        cursor = connection.cursor()

        include_buffer = getattr(settings, "BIOMETRIC_MSSQL_READ_BUFFER", False)
        tables = _existing_punch_tables(cursor, from_date, until, include_buffer)

        if not include_buffer:
            stranded = _stranded_buffer_rows(cursor)
            if stranded:
                logger.warning(
                    "Biometric pull: dbo.DeviceLogs holds %d unarchived punch(es), "
                    "and BIOMETRIC_MSSQL_READ_BUFFER is off, so they are skipped. "
                    "They arrive once eTimeTrackLite archives them.", stranded)

        if not tables:
            if not any(name != "devicelogs" for name in _punch_tables_present(cursor)):
                raise RuntimeError(
                    "No DeviceLogs_<month>_<year> table exists in %s, so there is "
                    "nowhere for punches to be -- check BIOMETRIC_MSSQL_DATABASE."
                    % settings.BIOMETRIC_MSSQL_DATABASE
                )
            logger.info("Biometric pull: no monthly table covers %s .. %s.",
                        from_date, until)
            return ingest([], source=source, force=force)

        logger.info("Biometric pull reading from: %s", ", ".join(tables))

        sql = """
            SELECT  p.UserId, e.EmployeeCode, e.EmployeeName, p.LogDate,
                    p.DeviceId, p.Direction, p.DeviceLogId
            FROM    (%s
            ) AS p
            LEFT JOIN dbo.Employees AS e ON e.EmployeeCodeInDevice = p.UserId
            ORDER BY p.LogDate, p.UserId
        """ % "\n            UNION ALL".join(
            branch.format(table=table) for table in tables)

        params = []
        for _ in tables:
            params.extend((from_date, until))
        cursor.execute(sql, *params)

        for row in cursor.fetchall():
            records.append({
                "device_user_id": row.UserId,
                "employee_code": row.EmployeeCode or "",
                "employee_name": row.EmployeeName or "",
                "punch_date": row.LogDate.date().isoformat(),
                "punch_time": row.LogDate.time().replace(microsecond=0).isoformat(),
                "device_id": row.DeviceId,
                "direction": row.Direction or "",
                "source_log_id": row.DeviceLogId,
            })

    return ingest(records, source=source, force=force)
