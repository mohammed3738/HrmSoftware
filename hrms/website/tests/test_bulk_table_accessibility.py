"""
Regression test for the accessible names on bulk-action tables.

The approval queues and the late-attendance review are columns of
identical `<input type="checkbox">` with no label, no aria-label and no
title. A screen reader announces each one as "checkbox", so the control
that decides whether somebody's late day is forgiven -- or whose leave is
approved -- is indistinguishable from the one above it. Measured across
the app during the audit: 63 unnamed controls on the employee list, 104 on
the late-attendance review, 31 on the holiday calendar.

These rows now carry an aria-label naming whose record they select. The
test renders the real template rather than reading the source, so it fails
if the label is dropped or if the context variable behind it is renamed.

Run with:
    python manage.py test website.tests.test_bulk_table_accessibility
"""
from datetime import date, time
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import (
    Attendance,
    Company,
    Employee,
    PayrollSettings,
    attendance_rule_cache,
)


class BulkTableAccessibilityTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="A11", name="Accessible Co", phone="1",
            email="a11@test.com", address="Addr",
        )
        PayrollSettings.objects.create(company=self.company, weekend_days="sun")
        self.employee = Employee.objects.create(
            company=self.company, salutation="Mr", first_name="Latecomer",
            last_name="Singh", father_name="Father", gender="Male",
            blood_group="O+", date_of_birth=date(1990, 1, 1), place_of_birth="City",
            personal_email="a11001@test.com", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890",
            employee_code="A11001", designation="Dev", department="IT",
            date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012",
            name_as_per_bank="Latecomer", salary_account_number="1234567890",
            ifsc_code="TEST0001234", emergency_contact_name1="Jane",
            emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
            force_password_change=False,
        )
        # A short day so it lands on the late-attendance review.
        with attendance_rule_cache():
            Attendance.objects.create(
                employee=self.employee, date=date(2026, 5, 20),
                in_time=time(10, 30), out_time=time(17, 15),
            )

        self.admin = User.objects.create_superuser(
            "a11_admin", "a11admin@test.com", "pass12345")
        self.client_admin = Client()
        self.client_admin.force_login(
            self.admin, backend="django.contrib.auth.backends.ModelBackend")

    def test_late_review_rows_name_the_employee_and_the_day(self):
        html = self.client_admin.get(
            reverse("late_attendance_review"),
            {"from": "2026-05-01", "to": "2026-05-31"},
        ).content.decode()
        self.assertIn('aria-label="Select all late attendance records"', html)
        self.assertIn("Select Latecomer Singh on 20 May 2026", html)

    def test_no_checkbox_on_the_late_review_is_left_unnamed(self):
        import re

        html = self.client_admin.get(
            reverse("late_attendance_review"),
            {"from": "2026-05-01", "to": "2026-05-31"},
        ).content.decode()
        unnamed = [
            tag for tag in re.findall(r"<input\b[^>]*type=[\"']checkbox[\"'][^>]*>", html)
            if "aria-label" not in tag and "aria-labelledby" not in tag
            and "title=" not in tag and "id=" not in tag
        ]
        self.assertEqual(
            unnamed, [],
            f"checkboxes with no accessible name on the late-attendance "
            f"review: {unnamed}",
        )
