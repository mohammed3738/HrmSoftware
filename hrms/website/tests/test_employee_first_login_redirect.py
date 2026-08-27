"""
Regression tests: a new employee's first login used to 403 instead of
reaching the Employee Dashboard.

Root cause: sync_user (website/signals.py), triggered whenever an Employee
is saved without a linked user, auto-provisions a login account but never
assigned it to any Group. login_view's redirect logic only recognizes
Admin/HR/Manager and Employee groups; a group-less user fell through to its
fallback (admin-dashboard), which requires Admin/HR feature permission ->
403 on the very first login.

Fixed in two places: sync_user now assigns the baseline "Employee" group to
every auto-provisioned login, and login_view's fallback now sends any user
who still has no recognized group but IS linked to an Employee record to
employee-dashboard instead of admin-dashboard, as a second line of defense.

Run with: python manage.py test website.tests.test_employee_first_login_redirect
"""
from datetime import date

from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse

from website.models import Company, Employee


class EmployeeFirstLoginRedirectTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="FLR", name="First Login Redirect Co", phone="1", email="flr@test.com", address="Addr",
        )

    def make_employee_without_user(self, code="FLR001"):
        """Mirrors how HR creates an employee without picking a role up
        front -- triggers sync_user's auto-provisioning path."""
        return Employee.objects.create(
            company=self.company, salutation="Mr", first_name="New", last_name="Hire",
            father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email=f"{code}@test.com", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890", employee_code=code,
            designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="New",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
        )

    def test_sync_user_assigns_employee_group_to_auto_provisioned_login(self):
        employee = self.make_employee_without_user()
        self.assertIsNotNone(employee.user)
        self.assertEqual(
            list(employee.user.groups.values_list("name", flat=True)), ["Employee"],
        )

    def test_new_employee_first_login_redirects_to_employee_dashboard_not_403(self):
        employee = self.make_employee_without_user(code="FLR002")
        client = Client()
        resp = client.post(reverse("login"), {
            "username": employee.user.username, "password": "Temp@123",
        })
        # Check the raw redirect target directly rather than assertRedirects,
        # which would also follow through to force_password_change=True's
        # own redirect to /change-password/ (a separate, correctly-working
        # gate, not what this test is about).
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("employee-dashboard"))

        # And the dashboard itself must actually be reachable once past the
        # (unrelated) force-password-change gate.
        employee.force_password_change = False
        employee.save(update_fields=["force_password_change"])
        dash_resp = client.get(reverse("employee-dashboard"))
        self.assertEqual(dash_resp.status_code, 200)

    def test_login_fallback_handles_a_pre_existing_groupless_employee_account(self):
        """Even without the sync_user fix (e.g. an account created before
        this fix shipped), login_view's fallback must not send a
        group-less-but-linked-to-an-employee user to admin-dashboard."""
        employee = self.make_employee_without_user(code="FLR003")
        employee.user.groups.clear()  # simulate a pre-existing, already-broken account
        self.assertEqual(employee.user.groups.count(), 0)

        client = Client()
        resp = client.post(reverse("login"), {
            "username": employee.user.username, "password": "Temp@123",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("employee-dashboard"))

    def test_bare_account_with_no_employee_profile_still_falls_back_to_admin_dashboard(self):
        User.objects.create_user(username="flr_bare", password="pass12345")
        client = Client()
        resp = client.post(reverse("login"), {"username": "flr_bare", "password": "pass12345"})
        # This user has no permissions at all, so admin-dashboard itself
        # correctly 403s them -- only the redirect *target* is under test here.
        self.assertRedirects(resp, reverse("admin-dashboard"), target_status_code=403)
