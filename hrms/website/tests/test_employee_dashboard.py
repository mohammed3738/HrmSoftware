"""
Regression tests for the Employee Dashboard (self-service landing page for
Employee-role logins, reached via login and the "Dashboards" nav link) and
my_profile, which sends the logged-in user to their own employee_detail
profile page ("My Profile" in the nav) -- these are two distinct
destinations for two distinct nav items.

Run with: python manage.py test website.tests.test_employee_dashboard
"""
from datetime import date, time

from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse

from website.models import (
    Company, Employee, Attendance, LeaveBalance, Holiday, HolidayType,
    PayrollRun, PayrollRecord, Branch,
)


class EmployeeDashboardTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="EDT", name="Emp Dashboard Test Co", phone="1", email="edt@test.com", address="Addr",
        )
        self.branch = Branch.objects.create(branch_name="Main Branch")
        self.user = User.objects.create_user(username="emp_dash_user", password="pass12345")
        self.user.groups.add(Group.objects.get(name="Employee"))

        self.employee = Employee.objects.create(
            company=self.company, branch=self.branch, user=self.user,
            salutation="Mr", first_name="Dash", last_name="Board",
            father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email="dash@test.com", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890", employee_code="EDT001",
            designation="Developer", department="IT", date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Dash",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active", force_password_change=False,
        )
        self.client = Client()
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def test_dashboard_loads_and_shows_own_data_only(self):
        Attendance.objects.create(employee=self.employee, date=date.today(), in_time=time(9, 0), out_time=time(18, 0))
        resp = self.client.get(reverse("employee-dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["employee"].id, self.employee.id)

    def test_dashboard_denies_user_with_no_employee_profile(self):
        bare_user = User.objects.create_user(username="no_profile_user", password="pass12345")
        client = Client()
        client.force_login(bare_user, backend="django.contrib.auth.backends.ModelBackend")
        resp = client.get(reverse("employee-dashboard"))
        self.assertEqual(resp.status_code, 302)  # redirected to login, not shown someone else's dashboard

    def test_leave_balance_shown_when_present(self):
        LeaveBalance.objects.create(
            employee=self.employee, period_from_date=date(2026, 1, 1), period_to_date=date(2026, 1, 31),
            final_leave_balance=12,
        )
        resp = self.client.get(reverse("employee-dashboard"))
        self.assertEqual(resp.context["leave_balance"].final_leave_balance, 12)

    def test_upcoming_holiday_shown_when_applicable(self):
        htype = HolidayType.objects.create(name="National", type_category="national")
        user_admin = User.objects.create_superuser("holiday_admin", "ha@test.com", "pass12345")
        Holiday.objects.create(
            holiday_date=date.today().replace(year=date.today().year + 1),
            name="Future Holiday", holiday_type=htype, created_by=user_admin,
        )
        resp = self.client.get(reverse("employee-dashboard"))
        names = [h.name for h in resp.context["upcoming_holidays"]]
        self.assertIn("Future Holiday", names)

    def test_only_finalized_payslips_shown(self):
        draft_run = PayrollRun.objects.create(
            company=self.company, month=date(2026, 1, 1), start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
            status=PayrollRun.STATUS_DRAFT,
        )
        PayrollRecord.objects.create(payroll=draft_run, employee=self.employee, employee_code="EDT001")
        finalized_run = PayrollRun.objects.create(
            company=self.company, month=date(2026, 2, 1), start_date=date(2026, 2, 1), end_date=date(2026, 2, 28),
            status=PayrollRun.STATUS_FINALIZED,
        )
        PayrollRecord.objects.create(payroll=finalized_run, employee=self.employee, employee_code="EDT001")

        resp = self.client.get(reverse("employee-dashboard"))
        self.assertEqual(resp.context["recent_payslips"].count(), 1)
        self.assertEqual(resp.context["recent_payslips"].first().payroll.status, PayrollRun.STATUS_FINALIZED)

    def test_login_redirects_employee_to_dashboard(self):
        client = Client()
        resp = client.post(reverse("login"), {"username": "emp_dash_user", "password": "pass12345"})
        self.assertRedirects(resp, reverse("employee-dashboard"))

    def test_my_profile_redirects_to_own_employee_detail_page(self):
        resp = self.client.get(reverse("my_profile"))
        self.assertRedirects(resp, reverse("employee_detail", args=[self.employee.pk]))
