"""
A working day with no punch is now an absence, not a blank.

Until now the biometric sync only ever created an Attendance row for a day
it could derive an in-time for. A day nobody punched on produced no row at
all, so it was neither present nor absent -- simply missing. Payroll counts
working days from the rows that exist, so a genuine absence nobody noticed
cost the employee nothing and showed up on no report.

The dangerous way to fix that is to mark every employee absent for every
working day with no punch. If the agent is not running, the device is
offline or the network is down, no punches arrive at all -- and that would
quietly take a day's pay from the whole company. So a day only counts when
at least one punch was matched to an employee on it: proof the device, the
agent, the network and the employee-code mapping all worked that day.

Two further limits, both of which are about not calling something an
absence before it is one:

  * only days strictly before today, because a night employee punches in at
    21:45 and a late shift later still;
  * weekends, weekly offs, holidays and half-day scenarios are not
    absences. Rather than re-deriving which is which, the row is built and
    calculate_status() is asked -- the same rules the register uses -- and
    only a row that comes back "Absent" is kept.

Run with:
    python manage.py test website.tests.test_absent_backfill
"""
from datetime import date, time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils.timezone import now

from website.models import (
    Attendance,
    Company,
    Holiday,
    HolidayType,
    PayrollSettings,
    ShiftAssignment,
)
from website.services import biometric_sync
from website.tests.test_biometric_sync import make_employee, punch


def _recent(weekday, weeks_back=1):
    """A date with the given weekday, comfortably in the past but recent
    enough to stay inside any lookback window."""
    day = now().date() - timedelta(days=7 * weeks_back)
    while day.weekday() != weekday:
        day -= timedelta(days=1)
    return day


MON = _recent(0)
TUE = MON + timedelta(days=1)


class AbsentBackfillTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="ABS", name="Absent Co", phone="1",
            email="abs@test.com", address="Addr",
        )
        # Sunday-only weekends, so Monday and Tuesday are plain working days.
        PayrollSettings.objects.create(company=self.company, weekend_days="sun")
        self.present = make_employee(self.company, "ABS001")
        self.absentee = make_employee(self.company, "ABS002")

    def row(self, employee, day):
        return Attendance.objects.filter(employee=employee, date=day).first()

    # ── the headline behaviour ───────────────────────────────────────────

    def test_an_employee_who_did_not_punch_is_marked_absent(self):
        biometric_sync.ingest([
            punch("ABS001", MON, "09:05:00"),
            punch("ABS001", MON, "18:10:00"),
        ])
        row = self.row(self.absentee, MON)
        self.assertIsNotNone(row, "the employee who never punched has no row at all")
        self.assertEqual(row.status, "Absent")
        self.assertEqual(row.count, 0)
        self.assertIsNone(row.in_time)

    def test_the_employee_who_did_punch_is_untouched(self):
        biometric_sync.ingest([
            punch("ABS001", MON, "09:05:00"),
            punch("ABS001", MON, "18:10:00"),
        ])
        row = self.row(self.present, MON)
        self.assertEqual(row.status, "Present")
        self.assertEqual(row.in_time, time(9, 5))

    def test_each_reported_day_is_judged_on_its_own(self):
        biometric_sync.ingest([
            punch("ABS001", MON, "09:00:00"), punch("ABS001", MON, "18:00:00"),
            punch("ABS001", TUE, "09:00:00"), punch("ABS001", TUE, "18:00:00"),
            punch("ABS002", TUE, "09:30:00"), punch("ABS002", TUE, "18:30:00"),
        ])
        self.assertEqual(self.row(self.absentee, MON).status, "Absent")
        self.assertEqual(self.row(self.absentee, TUE).status, "Present")

    # ── the guard against a sync outage ──────────────────────────────────

    def test_a_day_the_machine_reported_nothing_for_marks_nobody_absent(self):
        """The whole point of the guard: no punches at all is a sync
        failure, not an office-wide absence."""
        biometric_sync.ingest([])
        self.assertIsNone(self.row(self.present, MON))
        self.assertIsNone(self.row(self.absentee, MON))

    def test_a_day_whose_punches_all_failed_to_match_marks_nobody_absent(self):
        """Punches arrived but matched no employee -- a broken code
        mapping, which is exactly what must not cost everyone a day."""
        biometric_sync.ingest([punch("NOT-AN-EMPLOYEE", MON, "09:00:00")])
        self.assertIsNone(self.row(self.present, MON))
        self.assertIsNone(self.row(self.absentee, MON))

    def test_today_is_not_marked_absent_while_it_is_still_running(self):
        today = now().date()
        biometric_sync.ingest([punch("ABS001", today, "09:00:00")])
        self.assertIsNone(
            self.row(self.absentee, today),
            "today was called an absence before it had finished",
        )

    # ── days that are not absences ───────────────────────────────────────

    def test_a_weekly_off_is_not_an_absence(self):
        sunday = MON - timedelta(days=1)
        biometric_sync.ingest([punch("ABS001", sunday, "10:00:00")])
        row = self.row(self.absentee, sunday)
        self.assertIsNone(row, "a Sunday was recorded as an absence")

    def test_a_holiday_is_not_an_absence(self):
        author = User.objects.create_user("abs_hr", "abs_hr@test.com", "pass12345")
        holiday_type = HolidayType.objects.create(name="National", type_category="national")
        Holiday.objects.create(
            holiday_date=MON, name="Test Holiday", holiday_type=holiday_type,
            status="declared", is_national=True, created_by=author,
        )
        biometric_sync.ingest([punch("ABS001", MON, "09:00:00")])
        row = self.row(self.absentee, MON)
        self.assertIsNone(row, "a declared holiday was recorded as an absence")

    def test_a_rostered_weekly_off_is_not_an_absence(self):
        ShiftAssignment.objects.create(
            employee=self.absentee, shift_name="Rotating", start_date=MON - timedelta(days=7),
            end_date=MON + timedelta(days=7), week_off_day=MON.weekday(),
        )
        biometric_sync.ingest([punch("ABS001", MON, "09:00:00")])
        self.assertIsNone(
            self.row(self.absentee, MON),
            "the roster's weekly off was recorded as an absence",
        )

    def test_a_day_before_the_employee_joined_is_not_an_absence(self):
        self.absentee.date_of_joining = MON + timedelta(days=1)
        self.absentee.save(update_fields=["date_of_joining"])
        biometric_sync.ingest([punch("ABS001", MON, "09:00:00")])
        self.assertIsNone(self.row(self.absentee, MON))

    # ── existing rows win ────────────────────────────────────────────────

    def test_an_existing_row_is_never_overwritten(self):
        Attendance.objects.create(
            employee=self.absentee, date=MON, in_time=time(10, 0), out_time=time(19, 0),
        )
        biometric_sync.ingest([punch("ABS001", MON, "09:00:00")])
        row = self.row(self.absentee, MON)
        self.assertEqual(row.in_time, time(10, 0))
        self.assertNotEqual(row.status, "Absent")

    def test_running_the_sync_twice_creates_one_row(self):
        batch = [punch("ABS001", MON, "09:00:00"), punch("ABS001", MON, "18:00:00")]
        biometric_sync.ingest(batch)
        biometric_sync.ingest(batch)
        self.assertEqual(
            Attendance.objects.filter(employee=self.absentee, date=MON).count(), 1,
        )

    def test_the_run_reports_how_many_days_it_marked(self):
        run = biometric_sync.ingest([
            punch("ABS001", MON, "09:00:00"), punch("ABS001", MON, "18:00:00"),
        ])
        self.assertIn("marked Absent", run.message)
