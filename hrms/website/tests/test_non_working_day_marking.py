"""
The eSSL sync records weekends, weekly offs and holidays too, not just
absences.

The punch pass only writes a row for a day it can derive an in-time for,
so everything else was blank -- and on the attendance list a weekly off, a
holiday, a genuine absence and a day the device was unplugged all looked
identical: nothing at all. The point of an automated sync is that the
month comes out complete.

The rule that makes this work, and the one most easily got wrong: a
non-working day is marked on EVERY day in the window, with no requirement
that punches arrived. Requiring one would mean Sundays and holidays were
never marked, since those are precisely the days nobody punches on -- the
exact gap this closes. Absences keep the stricter rule, because an absence
is a pay question and a sync outage must not cost everyone a day.

What each day is called is decided by calculate_status(), not re-derived
here, so the company weekend setting, the employee's own weekly off, the
shift roster, branch-specific holidays and half-day scenarios all keep
their single definition.

That these rows do not move a payroll figure is asserted separately, in
test_marked_days_do_not_change_payroll.

Run with:
    python manage.py test website.tests.test_non_working_day_marking
"""
from datetime import date, timedelta

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


def _last_sunday():
    day = now().date() - timedelta(days=1)
    while day.weekday() != 6:
        day -= timedelta(days=1)
    return day


SUNDAY = _last_sunday()
MONDAY = SUNDAY + timedelta(days=1)       # may be today; guarded per test
PREV_WED = SUNDAY - timedelta(days=4)
PREV_THU = SUNDAY - timedelta(days=3)


class NonWorkingDayMarkingTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="NWD", name="Non Working Co", phone="1",
            email="nwd@test.com", address="Addr",
        )
        PayrollSettings.objects.create(company=self.company, weekend_days="sun")
        self.author = User.objects.create_superuser(
            "nwd_admin", "nwd@test.com", "pass12345")
        self.employee = make_employee(self.company, "NWD001")

    def row(self, day, employee=None):
        return Attendance.objects.filter(
            employee=employee or self.employee, date=day).first()

    def _sync(self, from_date, to_date):
        """Rebuild the window from stored punches, which is the scheduled
        task's own path."""
        return biometric_sync.resync_window(from_date=from_date, to_date=to_date)

    # ── the headline: days with no punches get marked ────────────────────

    def test_a_sunday_nobody_punched_on_is_recorded_as_a_weekend(self):
        self._sync(SUNDAY, SUNDAY)
        row = self.row(SUNDAY)
        self.assertIsNotNone(row, "the Sunday is still blank")
        self.assertEqual(row.status, "Weekend")

    def test_a_holiday_nobody_punched_on_is_recorded_as_a_holiday(self):
        holiday_type = HolidayType.objects.create(name="National", type_category="national")
        Holiday.objects.create(
            holiday_date=PREV_WED, name="Test Holiday", holiday_type=holiday_type,
            status="declared", is_national=True, created_by=self.author,
        )
        self._sync(PREV_WED, PREV_WED)
        row = self.row(PREV_WED)
        self.assertIsNotNone(row, "the holiday is still blank")
        self.assertEqual(row.status, "Holiday")
        self.assertTrue(row.is_holiday)

    def test_a_rostered_weekly_off_is_recorded(self):
        ShiftAssignment.objects.create(
            employee=self.employee, shift_name="Rotating",
            start_date=PREV_WED - timedelta(days=7), end_date=SUNDAY,
            week_off_day=PREV_WED.weekday(),
        )
        self._sync(PREV_WED, PREV_WED)
        row = self.row(PREV_WED)
        self.assertIsNotNone(row)
        self.assertEqual(row.status, "Weekend")

    def test_no_punches_anywhere_still_records_the_non_working_days(self):
        """The crux. A weekend has no punches by definition, so the
        'only days the machine reported' rule must not apply to it --
        otherwise weekends would never be marked at all."""
        self.assertFalse(biometric_sync.BiometricPunch.objects.exists())
        self._sync(SUNDAY, SUNDAY)
        self.assertEqual(self.row(SUNDAY).status, "Weekend")

    def test_but_a_working_day_with_no_punches_anywhere_is_still_not_an_absence(self):
        """The other half of the same rule: the absence guard stays."""
        self.assertFalse(biometric_sync.BiometricPunch.objects.exists())
        self._sync(PREV_WED, PREV_WED)
        self.assertIsNone(
            self.row(PREV_WED),
            "a working day was marked Absent with no evidence the machine ran",
        )

    # ── a whole window comes out complete ────────────────────────────────

    def test_a_week_is_filled_in_end_to_end(self):
        """A realistic week: a colleague keeps punching all week, so every
        working day is a reported day, while this employee punches only on
        Wednesday. The holiday and the Sunday are recorded for both.

        The colleague matters. The absence guard is per DAY, not per
        window: a working day on which nobody in the company punched is
        indistinguishable from the device being unplugged, so it is left
        blank rather than marking everyone absent."""
        colleague = make_employee(self.company, "NWD002")

        holiday_type = HolidayType.objects.create(name="National", type_category="national")
        Holiday.objects.create(
            holiday_date=PREV_THU, name="Test Holiday", holiday_type=holiday_type,
            status="declared", is_national=True, created_by=self.author,
        )

        punches = [punch("NWD001", PREV_WED, "09:05:00"),
                   punch("NWD001", PREV_WED, "18:10:00")]
        day = PREV_WED
        while day <= SUNDAY:
            punches.append(punch("NWD002", day, "09:00:00"))
            punches.append(punch("NWD002", day, "18:00:00"))
            day += timedelta(days=1)
        biometric_sync.store_punches(punches)

        self._sync(PREV_WED, SUNDAY)

        statuses = {
            row.date: row.status
            for row in Attendance.objects.filter(employee=self.employee)
        }
        self.assertEqual(statuses.get(PREV_WED), "Present")
        self.assertEqual(statuses.get(PREV_THU), "Holiday")
        self.assertEqual(statuses.get(SUNDAY), "Weekend")

        friday = SUNDAY - timedelta(days=2)
        saturday = SUNDAY - timedelta(days=1)
        self.assertEqual(statuses.get(friday), "Absent")
        self.assertEqual(statuses.get(saturday), "Absent")

        # Not a single completed day in the window is left blank.
        day, blank = PREV_WED, []
        while day <= SUNDAY:
            if day not in statuses:
                blank.append(day)
            day += timedelta(days=1)
        self.assertEqual(blank, [], f"days still blank: {blank}")

    # ── limits ───────────────────────────────────────────────────────────

    def test_today_is_left_alone(self):
        today = now().date()
        self._sync(today, today)
        self.assertIsNone(self.row(today), "today was marked before it finished")

    def test_an_existing_row_is_never_overwritten(self):
        Attendance.objects.create(
            employee=self.employee, date=SUNDAY, status_overridden=True,
            status="Present", count=1,
        )
        self._sync(SUNDAY, SUNDAY)
        row = self.row(SUNDAY)
        self.assertEqual(row.status, "Present", "an override was overwritten")

    def test_running_twice_creates_one_row(self):
        self._sync(SUNDAY, SUNDAY)
        self._sync(SUNDAY, SUNDAY)
        self.assertEqual(
            Attendance.objects.filter(employee=self.employee, date=SUNDAY).count(), 1)

    def test_a_day_before_the_employee_joined_is_left_alone(self):
        self.employee.date_of_joining = MONDAY
        self.employee.save(update_fields=["date_of_joining"])
        self._sync(SUNDAY, SUNDAY)
        self.assertIsNone(self.row(SUNDAY))

    def test_the_run_says_what_it_recorded(self):
        run = self._sync(SUNDAY, SUNDAY)
        self.assertIn("non-working day", run.message)
