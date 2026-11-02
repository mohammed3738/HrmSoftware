"""
Writing a Weekend / Holiday row must not change what payroll counts.

The eSSL sync now records the days it used to leave blank -- absences
first, and weekends, weekly offs and holidays after this change -- so that
the attendance list shows a complete month instead of gaps. That is a
display change, and it must stay one: the same employee, the same month,
the same punches has to produce the same present_days and leave_taken
whether or not those rows happen to exist.

It is not obvious that it does. get_attendance_summary() counts free
weekend days by walking the calendar, not by reading rows, and it filters
`is_holiday=False`; Holiday.backfill_attendance() already writes Holiday
rows for some days and not others, so the two states coexist in live data
today. If writing a row moved a figure, this change would silently re-cut
everyone's payslip the first time the sync ran.

Each test computes the summary twice over identical punches -- once with
the non-working days left blank, once with them recorded -- and requires
the two to agree.

Run with:
    python manage.py test website.tests.test_marked_days_do_not_change_payroll
"""
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from website.models import (
    Attendance,
    Company,
    Employee,
    Holiday,
    HolidayType,
    PayrollSettings,
    ShiftAssignment,
    attendance_rule_cache,
)
from website.services import get_attendance_summary

# Mon 1 June 2026 .. Sun 7 June 2026.
MON = date(2026, 6, 1)
TUE = MON + timedelta(days=1)
WED = MON + timedelta(days=2)
SUN = MON + timedelta(days=6)


class MarkedDaysDoNotChangePayrollTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="MKD", name="Marked Days Co", phone="1",
            email="mkd@test.com", address="Addr",
        )
        self.settings = PayrollSettings.objects.create(
            company=self.company, weekend_days="sun")
        self.author = User.objects.create_superuser(
            "mkd_admin", "mkd@test.com", "pass12345")
        self.employee = Employee.objects.create(
            company=self.company, salutation="Mr", first_name="Marked", last_name="Doe",
            father_name="Father", gender="Male", blood_group="O+",
            date_of_birth=date(1990, 1, 1), place_of_birth="City",
            personal_email="mkd001@test.com", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890",
            employee_code="MKD001", designation="Dev", department="IT",
            date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Marked",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
            force_password_change=False,
        )

    def _work(self, days):
        with attendance_rule_cache():
            for day in days:
                Attendance.objects.create(
                    employee=self.employee, date=day,
                    in_time=time(9, 0), out_time=time(18, 30))

    def _mark(self, days):
        """Record a non-working day the way the sync now does: build the
        row and let calculate_status() name it."""
        with attendance_rule_cache():
            for day in days:
                Attendance.objects.create(employee=self.employee, date=day)

    def _summary(self):
        return get_attendance_summary(self.employee, MON, SUN, self.settings)

    def _all_days_except(self, excluded):
        day, days = MON, []
        while day <= SUN:
            if day not in excluded:
                days.append(day)
            day += timedelta(days=1)
        return days

    # ── the company weekend ──────────────────────────────────────────────

    def test_recording_the_sunday_changes_nothing(self):
        self._work(self._all_days_except({SUN}))
        before = self._summary()

        self._mark([SUN])
        after = self._summary()

        self.assertEqual(Attendance.objects.get(employee=self.employee, date=SUN).status,
                         "Weekend")
        self.assertEqual(after, before)
        self.assertEqual(after["present_days"], Decimal("7.00"))
        self.assertEqual(after["leave_taken"], Decimal("0.00"))

    # ── a rostered weekly off ────────────────────────────────────────────

    def test_recording_a_rostered_weekly_off_changes_nothing(self):
        ShiftAssignment.objects.create(
            employee=self.employee, shift_name="Night", start_date=MON,
            end_date=SUN, week_off_day=WED.weekday(),
        )
        self._work(self._all_days_except({WED}))
        before = self._summary()

        self._mark([WED])
        after = self._summary()

        self.assertEqual(Attendance.objects.get(employee=self.employee, date=WED).status,
                         "Weekend")
        self.assertEqual(after, before)
        self.assertEqual(after["leave_taken"], Decimal("0.00"))

    # ── a declared holiday ───────────────────────────────────────────────

    def _declare_holiday(self, day):
        holiday_type = HolidayType.objects.create(name="National", type_category="national")
        Holiday.objects.create(
            holiday_date=day, name="Test Holiday", holiday_type=holiday_type,
            status="declared", is_national=True, created_by=self.author,
        )

    def test_recording_a_holiday_changes_nothing(self):
        self._declare_holiday(TUE)
        self._work(self._all_days_except({TUE, SUN}))
        before = self._summary()

        self._mark([TUE])
        after = self._summary()

        row = Attendance.objects.get(employee=self.employee, date=TUE)
        self.assertEqual(row.status, "Holiday")
        self.assertTrue(row.is_holiday)
        self.assertEqual(
            after, before,
            "recording the holiday moved a payroll figure",
        )

    def test_a_holiday_is_not_leave_but_is_not_a_present_day_either(self):
        """Pins the behaviour as it actually is, which is not quite what it
        should be.

        A declared holiday correctly does NOT read as leave -- the employee
        is not docked for it. But it is not counted in present_days either:
        get_attendance_summary filters `is_holiday=False`, so a Holiday row
        never reaches paid_days, and holidays are not weekend days, so they
        reach free_weekend_days either. An employee present every working
        day of a week containing one holiday reads 6.00 of 7, not 7.00.

        This predates the marking change and is unaffected by it -- the
        figure is 6.00 whether or not the Holiday row exists, which
        test_recording_a_holiday_changes_nothing asserts directly. It is
        recorded here rather than quietly fixed because present_days is a
        payroll figure, and moving it is the user's decision. See
        HRMS_QUALITY_TRACKER.md D-32."""
        self._declare_holiday(TUE)
        self._work(self._all_days_except({TUE, SUN}))
        self._mark([TUE])

        summary = self._summary()
        self.assertEqual(
            summary["leave_taken"], Decimal("0.00"),
            "a declared holiday was counted as leave",
        )
        self.assertEqual(summary["present_days"], Decimal("6.00"))

    # ── everything at once, which is what a real month looks like ────────

    def test_a_week_with_a_holiday_a_weekly_off_and_a_real_absence(self):
        self._declare_holiday(TUE)
        thursday = MON + timedelta(days=3)
        self._work(self._all_days_except({TUE, WED, SUN, thursday}))
        self._mark([thursday])          # a genuine absence
        before = self._summary()

        self._mark([TUE, SUN])          # holiday and weekend, now recorded
        after = self._summary()

        self.assertEqual(after, before)
        self.assertEqual(after["leave_taken"], Decimal("1.00"))
