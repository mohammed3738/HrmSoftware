"""Leave Taken has to count approved leave, not just infer it from attendance.

The bug this pins: calculate_leave_balance_for_period() derived Leave Taken
purely from Attendance rows (working_days - paid_days), while approving a
LeaveApplication never creates one. An approved leave day was therefore in
neither total, the subtraction was unaffected, and Leave Taken stayed 0
however much leave had been granted.

The two ways a naive fix goes wrong, both covered below: counting a day
twice when an unpaid attendance row already exists for it, and spending
weekend or holiday days that a leave merely spanned.

Run with: python manage.py test website.tests.test_leave_taken_from_applications
"""
from datetime import date, time, timedelta
from decimal import Decimal

from django.test import TestCase

from website.models import (
    Attendance,
    Company,
    Employee,
    Holiday,
    HolidayType,
    LeaveApplication,
    LeaveBalance,
    PayrollSettings,
)
from website.views import calculate_leave_balance_for_period

# A calendar month, so the weekday maths is easy to follow.
# 2026-06-01 is a Monday; 2026-06-06/07 are Sat/Sun.
PERIOD = (date(2026, 6, 1), date(2026, 6, 30))


class LeaveTakenFromApplicationsTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Leave Co", short_name="LVC")
        # Sunday-only weekend, matching this installation (Saturday is worked).
        self.settings = PayrollSettings.objects.create(
            company=self.company, weekend_days="sun",
        )
        self.employee = Employee.objects.create(
            company=self.company, salutation="Mr", first_name="Leave", last_name="Taker",
            father_name="F", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email="lv001@test.com", present_address="A",
            permanent_address="A", personal_mobile="1234567890", employee_code="LV001",
            designation="Dev", department="IT", date_of_joining=date(2020, 1, 1),
            location="City", pan_no="ABCDE1234F", aadhar_no="123456789012",
            name_as_per_bank="Leave", salary_account_number="1", ifsc_code="TEST0001234",
            emergency_contact_name1="J", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
        )

    # ── helpers ─────────────────────────────────────────────────────────
    def present(self, *days):
        for day in days:
            Attendance.objects.create(
                employee=self.employee, date=day,
                in_time=time(9, 0), out_time=time(18, 30),
            )

    def absent_row(self, day):
        """An attendance row that pays nothing -- what an Excel upload leaves
        behind for a day somebody did not come in."""
        Attendance.objects.create(employee=self.employee, date=day,
                                  in_time=None, out_time=None)

    def leave(self, start, end, status="Approved"):
        return LeaveApplication.objects.create(
            employee=self.employee, start_date=start, end_date=end,
            reason="tested", status=status,
        )

    def leave_taken(self):
        """calculate_leave_balance_for_period returns the closing balance and
        writes the detail to LeaveBalance, so Leave Taken is read back from
        the row it stored -- the same value the Attendance Register and the
        leave-balance report show."""
        calculate_leave_balance_for_period(
            self.employee, self.settings, PERIOD[0], PERIOD[1],
        )
        row = LeaveBalance.objects.filter(
            employee=self.employee,
            period_from_date=PERIOD[0], period_to_date=PERIOD[1],
        ).first()
        self.assertIsNotNone(row, "expected a LeaveBalance row for the period")
        return Decimal(str(row.leave_taken))

    # ── the bug ─────────────────────────────────────────────────────────
    def test_approved_leave_with_no_attendance_row_is_counted(self):
        """The reported symptom: leave granted, Leave Taken still 0."""
        self.present(date(2026, 6, 1), date(2026, 6, 2))
        self.leave(date(2026, 6, 3), date(2026, 6, 5))      # Wed, Thu, Fri
        self.assertEqual(self.leave_taken(), Decimal("3"))

    def test_a_single_leave_day_counts_as_one(self):
        self.leave(date(2026, 6, 3), date(2026, 6, 3))
        self.assertEqual(self.leave_taken(), Decimal("1"))

    def test_no_leave_and_full_attendance_is_still_zero(self):
        day = PERIOD[0]
        while day <= PERIOD[1]:
            if day.weekday() != 6:
                self.present(day)
            day += timedelta(days=1)
        self.assertEqual(self.leave_taken(), Decimal("0"))

    # ── not counted twice ───────────────────────────────────────────────
    def test_a_leave_day_that_already_has_an_unpaid_row_counts_once(self):
        """The double-count trap. An Absent row for 3 June already shows up
        in working_days - paid_days; the leave must not add a second day."""
        self.absent_row(date(2026, 6, 3))
        self.leave(date(2026, 6, 3), date(2026, 6, 3))
        self.assertEqual(self.leave_taken(), Decimal("1"))

    def test_a_mixed_leave_counts_each_day_exactly_once(self):
        # 3 June has a row, 4 and 5 June do not.
        self.absent_row(date(2026, 6, 3))
        self.leave(date(2026, 6, 3), date(2026, 6, 5))
        self.assertEqual(self.leave_taken(), Decimal("3"))

    # ── days that were free anyway ──────────────────────────────────────
    def test_a_leave_spanning_a_sunday_does_not_spend_it(self):
        # Fri 5 -> Mon 8 June. Saturday 6 IS worked here; Sunday 7 is not.
        self.leave(date(2026, 6, 5), date(2026, 6, 8))
        self.assertEqual(self.leave_taken(), Decimal("3"))

    def test_a_leave_over_a_holiday_does_not_spend_it(self):
        from django.contrib.auth.models import User
        author = User.objects.create_user("holiday-author")
        holiday_type = HolidayType.objects.create(name="National")
        # is_national so it applies regardless of branch -- this employee has
        # none, and branch scoping is not what this test is about.
        Holiday.objects.create(
            name="Test Holiday", holiday_date=date(2026, 6, 4),
            holiday_type=holiday_type, is_active=True, is_national=True,
            applies_to_all_employees=True, created_by=author,
        )
        self.leave(date(2026, 6, 3), date(2026, 6, 5))      # Wed, Thu(holiday), Fri
        self.assertEqual(self.leave_taken(), Decimal("2"))

    def test_the_employees_own_weekly_off_is_respected(self):
        """A night-shift employee whose week off is Saturday, not Sunday."""
        self.employee.week_off_day = 5          # Saturday
        self.employee.save()
        self.leave(date(2026, 6, 5), date(2026, 6, 8))      # Fri, Sat(off), Sun, Mon
        self.assertEqual(self.leave_taken(), Decimal("3"))

    # ── only approved leave ─────────────────────────────────────────────
    def test_pending_leave_is_not_counted(self):
        self.leave(date(2026, 6, 3), date(2026, 6, 5), status="Pending")
        self.assertEqual(self.leave_taken(), Decimal("0"))

    def test_rejected_leave_is_not_counted(self):
        self.leave(date(2026, 6, 3), date(2026, 6, 5), status="Rejected")
        self.assertEqual(self.leave_taken(), Decimal("0"))

    # ── period boundaries ───────────────────────────────────────────────
    def test_only_the_part_of_a_leave_inside_the_period_counts(self):
        # 29 May -> 2 June: only 1 and 2 June are in the period.
        self.leave(date(2026, 5, 29), date(2026, 6, 2))
        self.assertEqual(self.leave_taken(), Decimal("2"))

    def test_a_leave_entirely_outside_the_period_counts_nothing(self):
        self.leave(date(2026, 7, 1), date(2026, 7, 3))
        self.assertEqual(self.leave_taken(), Decimal("0"))

    def test_leave_before_joining_is_not_counted_twice(self):
        """Pre-joining days are already folded in as a flat gap, so a leave
        overlapping them must not add to it."""
        self.employee.date_of_joining = date(2026, 6, 10)
        self.employee.save()
        self.leave(date(2026, 6, 3), date(2026, 6, 5))      # all before joining
        taken = self.leave_taken()
        # The pre-joining gap is 1-9 June = 9 days, and the leave adds nothing.
        self.assertEqual(taken, Decimal("9"))
