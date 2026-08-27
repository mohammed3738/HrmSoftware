"""
Regression tests: LWP directly determines pay, so only Admin/HR should be
able to override it on the leave balance report -- previously the edit
button rendered unconditionally in the template, and the save endpoint
(override_lwp_view) only checked that the record belonged to the same
company, letting any Employee-role user (including editing their own row)
submit an LWP override.

Run with: python manage.py test website.tests.test_leave_balance_lwp_edit_permission
"""
from datetime import date, time

from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse

from website.models import Company, Employee, PayrollSettings, LeaveBalance, Attendance


class LeaveBalanceLwpEditPermissionTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="LWE", name="LWP Edit Test Co", phone="1", email="lwe@test.com", address="Addr",
        )
        PayrollSettings.objects.create(company=self.company)

        # Pass user= directly at creation -- Employee's post_save signal
        # (sync_user, in website/signals.py) auto-creates a DIFFERENT user
        # and forces force_password_change back to True whenever an
        # Employee is saved without a user already set.
        self.employee_user = User.objects.create_user(username="lwe_emp", password="pass12345")
        self.employee_user.groups.add(Group.objects.get(name="Employee"))

        self.employee = Employee.objects.create(
            company=self.company, user=self.employee_user, salutation="Mr", first_name="Emp", last_name="Doe",
            father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email="lwe@test.com", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890", employee_code="LWE001",
            designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Emp",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active", force_password_change=False,
        )

        self.hr_user = User.objects.create_user(username="lwe_hr", password="pass12345")
        self.hr_user.groups.add(Group.objects.get(name="HR"))

        self.lb = LeaveBalance.objects.create(
            employee=self.employee, period_from_date=date(2026, 1, 1), period_to_date=date(2026, 1, 31),
            leave_without_pay=0, opening_balance=10, leave_taken=0, compoff=0,
            closing_balance=10, leave_balance=10, final_leave_balance=10,
        )
        # get_all_payroll_periods_from_attendance() needs at least one
        # Attendance record to derive a period at all -- without this,
        # leave_balance_view never resolves a selected_period, so `lb` stays
        # None for every row and the whole data row (including the LWP
        # cell) is skipped by the template regardless of permissions.
        Attendance.objects.create(
            employee=self.employee, date=date(2026, 1, 15), in_time=time(9, 0), out_time=time(18, 0),
        )

    def _client_as(self, user):
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return client

    def test_employee_does_not_get_edit_permission_in_context(self):
        resp = self._client_as(self.employee_user).get(reverse("leave_balance"))
        self.assertFalse(resp.context["can_edit_lwp"])

    def test_employee_edit_button_not_rendered(self):
        resp = self._client_as(self.employee_user).get(reverse("leave_balance"))
        # "lwp-edit-btn" alone also matches the always-present CSS selector
        # in the page's <style> block -- check for the actual button markup.
        self.assertNotContains(resp, 'onclick="startLwpEdit')

    def test_hr_gets_edit_permission_and_button_rendered(self):
        resp = self._client_as(self.hr_user).get(reverse("leave_balance"), {"company_id": self.company.id})
        self.assertTrue(resp.context["can_edit_lwp"])
        self.assertContains(resp, 'onclick="startLwpEdit')

    def test_employee_cannot_post_lwp_override_even_for_own_record(self):
        resp = self._client_as(self.employee_user).post(reverse("override-lwp"), {
            "lb_id": self.lb.id, "lwp_value": "5",
        })
        self.assertEqual(resp.status_code, 403)
        self.lb.refresh_from_db()
        self.assertEqual(self.lb.leave_without_pay, 0)

    def test_hr_can_post_lwp_override(self):
        resp = self._client_as(self.hr_user).post(reverse("override-lwp"), {
            "lb_id": self.lb.id, "lwp_value": "3",
        })
        self.assertEqual(resp.status_code, 200)
        self.lb.refresh_from_db()
        self.assertEqual(self.lb.leave_without_pay, 3)
