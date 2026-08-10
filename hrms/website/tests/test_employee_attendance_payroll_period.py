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

from website.models import Company, Employee, Attendance, PayrollSettings


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
