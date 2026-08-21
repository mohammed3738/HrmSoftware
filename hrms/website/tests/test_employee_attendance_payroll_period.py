"""
Regression test: the employee attendance detail page must filter by the
company's configured payroll cycle (e.g. 27th to 26th) instead of the naive
calendar month, when one is configured.
Run with: python manage.py test website.tests.test_employee_attendance_payroll_period
"""
from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from website.models import Company, Employee, Attendance, PayrollSettings, LeaveApplication


class EmployeeAttendancePayrollPeriodTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Test Co")
        # 27th-to-26th payroll cycle, as described by the user.
        PayrollSettings.objects.create(company=self.company, from_date=27, to_date=26)
        self.employee = Employee.objects.create(
            company=self.company,
            salutation="Mr", first_name="John", last_name="Doe",
            father_name="Robert Doe", gender="Male", blood_group="O+",
            date_of_birth=date(1990, 1, 1), place_of_birth="Test City",
            personal_email="john@test.com", present_address="123 Test St",
            permanent_address="123 Test St", personal_mobile="1234567890",
            employee_code="EMP001", designation="Developer", department="IT",
            date_of_joining=date(2020, 1, 1), location="Test Location",
            pan_no="ABCDE1234F", aadhar_no="123456789012",
            name_as_per_bank="John Doe", salary_account_number="1234567890",
            ifsc_code="TEST0001234", emergency_contact_name1="Jane Doe",
            emergency_contact_relation1="Spouse", emergency_contact_mobile1="0987654321",
            status="Active",
        )

        # One day just before the "June" period (27 May - 26 Jun), one at
        # each boundary, and one just after — to prove the cutoff is exact.
        self.before_period = Attendance.objects.create(
            employee=self.employee, date=date(2026, 5, 26), in_time=time(9, 0), out_time=time(18, 0),
        )
        self.period_start = Attendance.objects.create(
            employee=self.employee, date=date(2026, 5, 27), in_time=time(9, 0), out_time=time(18, 0),
        )
        self.mid_period = Attendance.objects.create(
            employee=self.employee, date=date(2026, 6, 10), in_time=time(9, 0), out_time=time(18, 0),
        )
        self.period_end = Attendance.objects.create(
            employee=self.employee, date=date(2026, 6, 26), in_time=time(9, 0), out_time=time(18, 0),
        )
        self.after_period = Attendance.objects.create(
            employee=self.employee, date=date(2026, 6, 27), in_time=time(9, 0), out_time=time(18, 0),
        )

        self.user = User.objects.create_superuser("admin", "admin@test.com", "pass12345")
        self.client = Client()
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def test_period_filter_uses_27_to_26_cycle_not_calendar_month(self):
        resp = self.client.get(reverse("employee_attendance_detail", args=[self.employee.id]))
        self.assertTrue(resp.context["uses_custom_period"])

        periods = resp.context["payroll_periods"]
        june_period = next(p for p in periods if p["to_date"] == date(2026, 6, 26))
        self.assertEqual(june_period["from_date"], date(2026, 5, 27))

        resp = self.client.get(
            reverse("employee_attendance_detail", args=[self.employee.id]),
            {"period": "2026-06-26"},
        )
        dates_shown = {r.date for r in resp.context["attendance_records"]}
        self.assertEqual(dates_shown, {date(2026, 5, 27), date(2026, 6, 10), date(2026, 6, 26)})
        self.assertNotIn(date(2026, 5, 26), dates_shown)
        self.assertNotIn(date(2026, 6, 27), dates_shown)

    def test_falls_back_to_calendar_month_when_no_custom_period_configured(self):
        other_company = Company.objects.create(name="Calendar Co", short_name="CALC")
        # No PayrollSettings row at all for this company -> naive calendar month.
        other_employee = Employee.objects.create(
            company=other_company,
            salutation="Mr", first_name="Jane", last_name="Roe",
            father_name="Bob Roe", gender="Female", blood_group="O+",
            date_of_birth=date(1990, 1, 1), place_of_birth="Test City",
            personal_email="jane@test.com", present_address="123 Test St",
            permanent_address="123 Test St", personal_mobile="1234567892",
            employee_code="EMP002", designation="Developer", department="IT",
            date_of_joining=date(2020, 1, 1), location="Test Location",
            pan_no="ABCDE1236F", aadhar_no="123456789014",
            name_as_per_bank="Jane Roe", salary_account_number="1234567892",
            ifsc_code="TEST0001234", emergency_contact_name1="Jane Doe",
            emergency_contact_relation1="Spouse", emergency_contact_mobile1="0987654323",
            status="Active",
        )
        Attendance.objects.create(
            employee=other_employee, date=date(2026, 6, 1), in_time=time(9, 0), out_time=time(18, 0),
        )

        resp = self.client.get(reverse("employee_attendance_detail", args=[other_employee.id]))
        self.assertFalse(resp.context["uses_custom_period"])

    def test_summary_stats_scoped_to_selected_payroll_period(self):
        """Days Present / Late Remarks / Half Days / Leaves Taken must be
        computed only from the currently selected payroll period, and a
        leave that only partially overlaps the period must be counted by
        its overlapping days, not its full length."""
        Attendance.objects.create(
            employee=self.employee, date=date(2026, 6, 5), in_time=time(9, 0), out_time=time(15, 0),
        )  # 6h worked -> Half Day
        Attendance.objects.create(
            employee=self.employee, date=date(2026, 6, 12), in_time=time(9, 0), out_time=time(16, 0),
        )  # 7h worked -> Late Present

        LeaveApplication.objects.create(
            employee=self.employee, leave_type="CL", start_date=date(2026, 6, 15),
            end_date=date(2026, 6, 17), reason="test", status="Approved",
        )  # 3 days, fully inside the 27 May - 26 Jun period

        LeaveApplication.objects.create(
            employee=self.employee, leave_type="CL", start_date=date(2026, 5, 25),
            end_date=date(2026, 5, 28), reason="test", status="Approved",
        )  # starts before the period; only 27-28 May (2 days) overlap it

        LeaveApplication.objects.create(
            employee=self.employee, leave_type="CL", start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 3), reason="test", status="Approved",
        )  # entirely outside the period -> must not be counted

        resp = self.client.get(
            reverse("employee_attendance_detail", args=[self.employee.id]),
            {"period": "2026-06-26"},
        )
        # Present (baseline): 27 May, 10 Jun, 26 Jun + the new Late Present (12 Jun) = 4
        self.assertEqual(resp.context["days_present_count"], 4)
        self.assertEqual(resp.context["late_remarks_count"], 1)
        self.assertEqual(resp.context["half_days_count"], 1)
        self.assertEqual(resp.context["leaves_taken"], 5)  # 3 + 2 (partial overlap), excludes the April leave

    def test_summary_stats_unfiltered_covers_all_time(self):
        """With no period/year/month selected, the summary must cover the
        employee's whole history, not just one period."""
        LeaveApplication.objects.create(
            employee=self.employee, leave_type="CL", start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 3), reason="test", status="Approved",
        )

        resp = self.client.get(reverse("employee_attendance_detail", args=[self.employee.id]))
        # 4 of the 5 setUp records are "Present" (9h worked each); the 5th
        # (27 Jun 2026) falls on a Saturday, so it's "Weekend" regardless of
        # its punch times — weekend status takes priority in calculate_status().
        self.assertEqual(resp.context["days_present_count"], 4)
        self.assertEqual(resp.context["leaves_taken"], 3)
