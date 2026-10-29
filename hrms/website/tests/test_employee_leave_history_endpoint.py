"""
Regression tests for employee_leave_history (views.py), which was broken in
two independent ways.

1. The queryset ordered by "-recorded_on", a field LeaveBalanceHistory has
   never had. Django raises FieldError when the queryset is evaluated, so
   every single request to employees/<id>/leave-history/ returned an
   unhandled 500 -- the endpoint had no working path at all. The model
   declares `ordering = ['-month', 'employee']` and `month` is the
   first-of-month DateField the snapshot is keyed on, so newest-first is
   "-month".

2. templates/leave_balance/_leave_history_table.html read
   `rec.days_present`, but the field is `number_of_days_present`. An
   unknown attribute renders as the empty string in a Django template, so
   the Days Present column was silently blank for every row. The same
   template also printed `closing_balance` in both the "Closing" and the
   "Leave Balance" column, ignoring the separate `leave_balance` field.

Both are asserted on real values here rather than on the absence of an
exception, so a regression shows up as a wrong number and not just a 500.

Run with:
    python manage.py test website.tests.test_employee_leave_history_endpoint
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import Company, Employee, LeaveBalanceHistory


class EmployeeLeaveHistoryEndpointTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="ELH", name="Leave History Co", phone="1",
            email="elh@test.com", address="Addr",
        )
        self.employee = Employee.objects.create(
            company=self.company, salutation="Mr", first_name="Hist", last_name="Doe",
            father_name="Father", gender="Male", blood_group="O+",
            date_of_birth=date(1990, 1, 1), place_of_birth="City",
            personal_email="elh001@test.com", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890",
            employee_code="ELH001", designation="Dev", department="IT",
            date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Hist",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
            force_password_change=False,
        )

        # Three months, created out of order so "newest first" is a real
        # assertion and not an artefact of insertion order.
        self.march = LeaveBalanceHistory.objects.create(
            employee=self.employee, month=date(2026, 3, 1),
            opening_balance=Decimal("4.00"), number_of_days_present=Decimal("20.00"),
            closing_balance=Decimal("5.00"), leave_balance=Decimal("7.00"),
            final_leave_balance=Decimal("6.00"),
        )
        self.may = LeaveBalanceHistory.objects.create(
            employee=self.employee, month=date(2026, 5, 1),
            opening_balance=Decimal("6.00"), number_of_days_present=Decimal("22.00"),
            closing_balance=Decimal("7.00"), leave_balance=Decimal("9.00"),
            final_leave_balance=Decimal("8.00"),
        )
        self.april = LeaveBalanceHistory.objects.create(
            employee=self.employee, month=date(2026, 4, 1),
            opening_balance=Decimal("5.00"), number_of_days_present=Decimal("21.00"),
            closing_balance=Decimal("6.00"), leave_balance=Decimal("8.00"),
            final_leave_balance=Decimal("7.00"),
        )

        self.hr_user = User.objects.create_user(username="elh_hr", password="pass12345")
        self.hr_user.groups.add(Group.objects.get(name="HR"))
        self.client_hr = Client()
        self.client_hr.force_login(
            self.hr_user, backend="django.contrib.auth.backends.ModelBackend",
        )

    def _get(self):
        return self.client_hr.get(
            reverse("employee_leave_history", args=[self.employee.pk]),
        )

    def test_endpoint_returns_200_instead_of_raising_fielderror(self):
        self.assertEqual(self._get().status_code, 200)

    def test_rows_come_back_newest_month_first(self):
        html = self._get().json()["html"]
        positions = [
            html.index("May"),
            html.index("April"),
            html.index("March"),
        ]
        self.assertEqual(
            positions, sorted(positions),
            "leave history is not ordered newest month first",
        )

    def test_days_present_column_shows_the_real_value(self):
        """number_of_days_present, not the non-existent days_present."""
        html = self._get().json()["html"]
        for expected in ("22", "21", "20"):
            with self.subTest(days_present=expected):
                self.assertIn(expected, html)

    def test_leave_balance_column_is_not_a_copy_of_closing_balance(self):
        html = self._get().json()["html"]
        # May: closing 7.00, leave_balance 9.00. The old template printed
        # closing_balance twice, so 9.00 never appeared anywhere.
        self.assertIn("9.00", html)
        self.assertIn("8.00", html)  # April's leave_balance

    def test_no_history_renders_the_empty_state(self):
        LeaveBalanceHistory.objects.all().delete()
        html = self._get().json()["html"]
        self.assertIn("No leave history found", html)
