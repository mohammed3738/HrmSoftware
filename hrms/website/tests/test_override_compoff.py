"""
Regression tests for the Comp Off override (used by the Attendance
Register's Comp Off cell, and available wherever a LeaveBalance row is
shown). Comp Off feeds into the same balance formula as LWP, so overriding
it must also recompute LWP/Balance/Closing/Final -- unless LWP was itself
already manually overridden, in which case LWP stays fixed. Mirrors the
pre-existing override_lwp_view/test_leave_balance_lwp_edit_permission.py
pattern closely.

Run with: python manage.py test website.tests.test_override_compoff
"""
from datetime import date

from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse

from website.models import Company, Employee, LeaveBalance, PayrollRun, PayrollSettings


class OverrideCompoffTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="OCT", name="Override Compoff Test Co", phone="1", email="oct@test.com", address="Addr",
        )
        PayrollSettings.objects.create(company=self.company)

        self.employee_user = User.objects.create_user(username="oct_emp", password="pass12345")
        self.employee_user.groups.add(Group.objects.get(name="Employee"))
        self.employee = Employee.objects.create(
            company=self.company, user=self.employee_user, salutation="Mr", first_name="Emp", last_name="Doe",
            father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email="oct@test.com", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890", employee_code="OCT001",
            designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Emp",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active", force_password_change=False,
        )

        self.hr_user = User.objects.create_user(username="oct_hr", password="pass12345")
        self.hr_user.groups.add(Group.objects.get(name="HR"))

        # opening(2) + compoff(0) - leave_taken(5) - late_days(0) = -3
        # -> leave_without_pay=3, leave_balance=0; monthly_credit=1 (closing - leave_balance)
        self.lb = LeaveBalance.objects.create(
            employee=self.employee, period_from_date=date(2026, 1, 1), period_to_date=date(2026, 1, 31),
            opening_balance=2, leave_taken=5, late=0, compoff=0,
            leave_without_pay=3, leave_balance=0, closing_balance=1, final_leave_balance=1,
        )

    def _client_as(self, user):
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return client

    def test_employee_cannot_override_compoff(self):
        resp = self._client_as(self.employee_user).post(reverse("override-compoff"), {
            "lb_id": self.lb.id, "compoff_value": "3",
        })
        self.assertEqual(resp.status_code, 403)
        self.lb.refresh_from_db()
        self.assertEqual(self.lb.compoff, 0)
        self.assertFalse(self.lb.compoff_overridden)

    def test_hr_override_recomputes_lwp_when_lwp_not_overridden(self):
        resp = self._client_as(self.hr_user).post(reverse("override-compoff"), {
            "lb_id": self.lb.id, "compoff_value": "3",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["compoff"], "3.00")
        self.assertEqual(data["lwp"], "0.00")  # 2 + 3 - 5 - 0 = 0 -> no shortfall
        self.assertEqual(data["closing_balance"], "1.00")  # leave_balance(0) + monthly_credit(1)
        self.assertEqual(data["final_leave_balance"], "1.00")

        self.lb.refresh_from_db()
        self.assertEqual(self.lb.compoff, 3)
        self.assertEqual(self.lb.leave_without_pay, 0)
        self.assertTrue(self.lb.compoff_overridden)

    def test_hr_override_preserves_manually_set_lwp(self):
        self.lb.lwp_overridden = True
        self.lb.leave_without_pay = 2
        self.lb.save(update_fields=["lwp_overridden", "leave_without_pay"])

        resp = self._client_as(self.hr_user).post(reverse("override-compoff"), {
            "lb_id": self.lb.id, "compoff_value": "3",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # LWP stays fixed at the manually-set 2.00, not recomputed to 0.
        self.assertEqual(data["lwp"], "2.00")

        self.lb.refresh_from_db()
        self.assertEqual(self.lb.leave_without_pay, 2)

    def test_negative_compoff_rejected(self):
        resp = self._client_as(self.hr_user).post(reverse("override-compoff"), {
            "lb_id": self.lb.id, "compoff_value": "-1",
        })
        self.assertEqual(resp.status_code, 400)
        self.lb.refresh_from_db()
        self.assertEqual(self.lb.compoff, 0)

    def test_locked_period_blocks_override(self):
        PayrollRun.objects.create(
            company=self.company, month=date(2026, 1, 1), start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
            status=PayrollRun.STATUS_FINALIZED,
        )
        resp = self._client_as(self.hr_user).post(reverse("override-compoff"), {
            "lb_id": self.lb.id, "compoff_value": "3",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])
        self.lb.refresh_from_db()
        self.assertEqual(self.lb.compoff, 0)

    def test_recalculation_preserves_overridden_compoff(self):
        """calculate_leave_balance_for_period must not silently overwrite a
        manually-overridden Comp Off value back to the auto-summed total."""
        from website.views import calculate_leave_balance_for_period

        self._client_as(self.hr_user).post(reverse("override-compoff"), {
            "lb_id": self.lb.id, "compoff_value": "3",
        })
        payroll_settings = PayrollSettings.objects.get(company=self.company)
        calculate_leave_balance_for_period(self.employee, payroll_settings, date(2026, 1, 1), date(2026, 1, 31))

        self.lb.refresh_from_db()
        self.assertEqual(self.lb.compoff, 3)
        self.assertTrue(self.lb.compoff_overridden)
