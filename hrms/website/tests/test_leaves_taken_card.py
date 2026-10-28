"""The "Leaves Taken" card on an employee's attendance page.

The bug this pins: the card counted approved LeaveApplications and nothing
else, as whole calendar days. In this installation almost no leave is
applied for -- the attendance upload marks the day Absent and that is the
whole record -- so the card read 0 for employees with weeks of leave. The
days it did count were calendar days, so a leave spanning a weekend was
charged for the weekend too.

It now uses count_leave_days_in_range, the same rule behind the attendance
register and the leave balance report: unpaid working days plus approved
leave that no attendance row covers, with weekends and holidays excluded.

Run with: python manage.py test website.tests.test_leaves_taken_card
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
    LeaveApplication,
    LeaveBalance,
    PayrollSettings,
)
from website.views import calculate_leave_balance_for_period, count_leave_days_in_range

# 2026-06-01 is a Monday; 06-07, 06-14, 06-21 and 06-28 are Sundays.
FROM_DATE = date(2026, 6, 1)
TO_DATE = date(2026, 6, 30)


class LeavesTakenCardTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Card Co", short_name="CRD")
        # Sunday-only weekend: Saturday is a working day here.
        self.settings = PayrollSettings.objects.create(
            company=self.company, weekend_days="sun",
        )
        self.employee = Employee.objects.create(
            company=self.company, salutation="Mr", first_name="Card", last_name="Holder",
            father_name="F", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email="cd001@test.com", present_address="A",
            permanent_address="A", personal_mobile="1234567890", employee_code="CD001",
            designation="Dev", department="IT", date_of_joining=date(2020, 1, 1),
            location="City", pan_no="ABCDE1234F", aadhar_no="123456789012",
            name_as_per_bank="Card", salary_account_number="1", ifsc_code="TEST0001234",
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

    def absent(self, *days):
        """What the attendance upload leaves behind for a day nobody came in
        -- and, here, how leave is actually recorded."""
        for day in days:
            Attendance.objects.create(employee=self.employee, date=day,
                                      in_time=None, out_time=None)

    def half_day(self, day):
        """Five hours: past half_day_min_hours (4.5) but short of the
        late-present floor, so calculate_status() credits half a day."""
        Attendance.objects.create(employee=self.employee, date=day,
                                  in_time=time(9, 0), out_time=time(14, 0))

    def counted(self, from_date=FROM_DATE, to_date=TO_DATE):
        return count_leave_days_in_range(
            self.employee, from_date, to_date, self.settings)

    # ── the reported bug ────────────────────────────────────────────────
    def test_absent_days_count_even_with_no_leave_application(self):
        """The symptom: plenty of leave, card reads 0."""
        self.absent(date(2026, 6, 3), date(2026, 6, 4), date(2026, 6, 5))
        self.assertEqual(self.counted(), Decimal("3"))

    def test_nothing_taken_is_zero(self):
        self.present(date(2026, 6, 1), date(2026, 6, 2))
        self.assertEqual(self.counted(), Decimal("0"))

    def test_a_half_day_is_half_a_leave_day(self):
        self.half_day(date(2026, 6, 3))
        self.assertEqual(self.counted(), Decimal("0.50"))

    # ── weekends and holidays are not spent ─────────────────────────────
    def test_a_sunday_with_no_attendance_is_not_leave(self):
        self.absent(date(2026, 6, 3))
        # 7 June is a Sunday and has no row at all, as weekends normally do not.
        self.assertEqual(self.counted(), Decimal("1"))

    def test_a_saturday_counts_because_saturday_is_worked_here(self):
        self.absent(date(2026, 6, 6))      # Saturday
        self.assertEqual(self.counted(), Decimal("1"))

    def test_a_saturday_does_not_count_when_the_company_rests_on_it(self):
        PayrollSettings.objects.filter(pk=self.settings.pk).update(
            weekend_days="sat_sun")
        self.settings.refresh_from_db()
        self.absent(date(2026, 6, 6))      # Saturday
        self.assertEqual(self.counted(), Decimal("0"))

    def test_a_holiday_is_not_leave(self):
        holiday_type = HolidayType.objects.create(name="National")
        user = User.objects.create_user("card-admin", password="x")
        Holiday.objects.create(
            name="Test Holiday", holiday_date=date(2026, 6, 10),
            holiday_type=holiday_type, is_national=True, is_active=True,
            created_by=user,
        )
        Attendance.objects.create(
            employee=self.employee, date=date(2026, 6, 10),
            in_time=None, out_time=None, is_holiday=True,
        )
        self.absent(date(2026, 6, 11))
        self.assertEqual(self.counted(), Decimal("1"))

    # ── approved leave with no attendance row still counts ──────────────
    def test_approved_leave_without_a_row_is_counted(self):
        LeaveApplication.objects.create(
            employee=self.employee, start_date=date(2026, 6, 3),
            end_date=date(2026, 6, 5), reason="tested", status="Approved",
        )
        self.assertEqual(self.counted(), Decimal("3"))

    def test_a_leave_day_that_also_has_an_absent_row_counts_once(self):
        self.absent(date(2026, 6, 3))
        LeaveApplication.objects.create(
            employee=self.employee, start_date=date(2026, 6, 3),
            end_date=date(2026, 6, 3), reason="tested", status="Approved",
        )
        self.assertEqual(self.counted(), Decimal("1"))

    def test_an_approved_leave_over_a_sunday_does_not_spend_it(self):
        # Friday 5 June to Monday 8 June, across Sunday the 7th.
        LeaveApplication.objects.create(
            employee=self.employee, start_date=date(2026, 6, 5),
            end_date=date(2026, 6, 8), reason="tested", status="Approved",
        )
        self.assertEqual(self.counted(), Decimal("3"))

    # ── it agrees with the register ─────────────────────────────────────
    def test_it_matches_the_figure_the_register_stores(self):
        """The card and the Leave Taken column are the same number now; they
        were computed two different ways before."""
        self.absent(date(2026, 6, 3), date(2026, 6, 4))
        self.half_day(date(2026, 6, 5))
        LeaveApplication.objects.create(
            employee=self.employee, start_date=date(2026, 6, 15),
            end_date=date(2026, 6, 16), reason="tested", status="Approved",
        )
        calculate_leave_balance_for_period(
            self.employee, self.settings, FROM_DATE, TO_DATE)
        stored = LeaveBalance.objects.get(
            employee=self.employee,
            period_from_date=FROM_DATE, period_to_date=TO_DATE).leave_taken
        self.assertEqual(self.counted(), Decimal(str(stored)))

    # ── edges ───────────────────────────────────────────────────────────
    def test_an_empty_or_backwards_range_is_zero_not_an_error(self):
        self.absent(date(2026, 6, 3))
        self.assertEqual(self.counted(None, None), Decimal("0.00"))
        self.assertEqual(self.counted(TO_DATE, FROM_DATE), Decimal("0.00"))

    def test_days_before_the_employee_joined_are_not_leave(self):
        Employee.objects.filter(pk=self.employee.pk).update(
            date_of_joining=date(2026, 6, 15))
        self.employee.refresh_from_db()
        self.absent(date(2026, 6, 3), date(2026, 6, 16))
        self.assertEqual(self.counted(), Decimal("1"))


class LeavesTakenCardRendersTest(TestCase):
    """The view itself, so the context key and the template agree."""

    def setUp(self):
        self.company = Company.objects.create(name="Render Co", short_name="RCO")
        PayrollSettings.objects.create(company=self.company, weekend_days="sun")
        self.employee = Employee.objects.create(
            company=self.company, salutation="Mr", first_name="Rend", last_name="Erer",
            father_name="F", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email="rc001@test.com", present_address="A",
            permanent_address="A", personal_mobile="1234567890", employee_code="RC001",
            designation="Dev", department="IT", date_of_joining=date(2020, 1, 1),
            location="City", pan_no="ABCDE1234F", aadhar_no="123456789012",
            name_as_per_bank="Rend", salary_account_number="1", ifsc_code="TEST0001234",
            emergency_contact_name1="J", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
        )
        for day in (date(2026, 6, 3), date(2026, 6, 4)):
            Attendance.objects.create(employee=self.employee, date=day,
                                      in_time=None, out_time=None)
        self.admin = User.objects.create_superuser(
            "card-super", "card-super@test.invalid", "x")
        self.client.force_login(
            self.admin, backend="django.contrib.auth.backends.ModelBackend")

    def test_the_page_reports_the_absent_days_not_zero(self):
        response = self.client.get(
            f"/attendance/{self.employee.id}/",
            {"year": "2026", "month": "6"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(str(response.context["leaves_taken"])), Decimal("2"))
        self.assertContains(response, "Leaves Taken")
