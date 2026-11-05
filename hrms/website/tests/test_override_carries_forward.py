"""
Editing a month's Comp Off or LWP cell changes that month's closing
balance, and the next month opens with it. Before this was fixed, only the
edited month was saved, so the following month kept the old opening
balance (e.g. July closed at 4 but August still opened at 3).

Run with: python manage.py test website.tests.test_override_carries_forward
"""
from datetime import date, time
from io import StringIO

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from website.models import Attendance, Company, Employee, LeaveBalance, PayrollSettings
from website.signals import recalculate_leave_balance_for_employee

# 27th-26th pay cycle, as on the live site: "July" = 27 Jun - 26 Jul.
JUL = (date(2026, 6, 27), date(2026, 7, 26))
AUG = (date(2026, 7, 27), date(2026, 8, 26))


class OverrideCarriesForwardTest(TestCase):
    def setUp(self):
        company = Company.objects.create(short_name="OCF", name="Carry Co", phone="1", email="o@t.com", address="A")
        PayrollSettings.objects.create(company=company, from_date=27, to_date=26)
        self.employee = Employee.objects.create(company=company, first_name="Vai", last_name="J",
                                                employee_code="OCF1", date_of_joining=date(2020, 1, 1), status="Active")
        for d in (date(2026, 7, 6), date(2026, 8, 4)):
            Attendance.objects.create(employee=self.employee, date=d, in_time=time(9), out_time=time(18))
        recalculate_leave_balance_for_employee(self.employee, JUL[0])

        admin = User.objects.create_user(username="ocf_admin", password="pass12345")
        admin.groups.add(Group.objects.get(name="Admin"))
        self.client = Client()
        self.client.force_login(admin, backend="django.contrib.auth.backends.ModelBackend")

    def _lb(self, period):
        return LeaveBalance.objects.get(employee=self.employee, period_from_date=period[0], period_to_date=period[1])

    def _assert_aug_opens_with_jul(self):
        self.assertEqual(self._lb(AUG).opening_balance, self._lb(JUL).final_leave_balance)

    def test_months_chain_before_any_edit(self):
        self._assert_aug_opens_with_jul()

    def test_compoff_edit_reaches_next_month(self):
        before = self._lb(JUL).final_leave_balance
        resp = self.client.post(reverse("override-compoff"), {"lb_id": self._lb(JUL).id, "compoff_value": "1"})
        self.assertTrue(resp.json()["success"])
        self.assertEqual(self._lb(JUL).final_leave_balance, before + 1)
        self._assert_aug_opens_with_jul()
        self.assertEqual(self._lb(JUL).compoff, 1)  # the edit itself survives the refresh
        self.assertTrue(self._lb(JUL).compoff_overridden)

    def test_lwp_edit_reaches_next_month(self):
        resp = self.client.post(reverse("override-compoff"), {"lb_id": self._lb(JUL).id, "compoff_value": "3"})
        resp = self.client.post(reverse("override-lwp"), {"lb_id": self._lb(JUL).id, "lwp_value": "2"})
        self.assertTrue(resp.json()["success"])
        self._assert_aug_opens_with_jul()
        self.assertEqual(self._lb(JUL).leave_without_pay, 2)

    def test_check_leave_chain_finds_and_fixes_a_stale_month(self):
        """Data broken before this fix (August left at the old opening) is
        listed by check_leave_chain and repaired by --fix."""
        LeaveBalance.objects.filter(pk=self._lb(AUG).pk).update(opening_balance=0)
        out = StringIO()
        call_command("check_leave_chain", stdout=out)
        self.assertIn("OCF1", out.getvalue())
        self.assertIn("1 employee(s)", out.getvalue())
        self.assertNotEqual(self._lb(AUG).opening_balance, self._lb(JUL).final_leave_balance)  # read-only

        call_command("check_leave_chain", "--fix", stdout=StringIO())
        self._assert_aug_opens_with_jul()
        out = StringIO()
        call_command("check_leave_chain", stdout=out)
        self.assertIn("0 employee(s)", out.getvalue())
