"""
HR neither sees nor changes company settings, and neither creates nor
manages advances -- only reads their own. Admin keeps both.

Run with: python manage.py test website.tests.test_hr_settings_and_advances
"""
from datetime import date

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import AdvanceMaster, Company, Employee, PayrollSettings


class HrSettingsAndAdvancesTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Set Co", short_name="SET", address="A")
        PayrollSettings.objects.create(company=self.company, weekend_days="sat_sun")
        self.hr_user = User.objects.create_user(username="set_hr", password="pass12345")
        self.hr_user.groups.add(Group.objects.get(name="HR"))
        self.hr_emp = Employee.objects.create(company=self.company, user=self.hr_user, first_name="Hr", last_name="One",
                                              employee_code="SETHR", status="Active", force_password_change=False)
        self.colleague = Employee.objects.create(company=self.company, first_name="Col", last_name="Two",
                                                 employee_code="SETCO", status="Active")
        self.hr = self._client(self.hr_user)
        admin = User.objects.create_user(username="set_admin", password="pass12345")
        admin.groups.add(Group.objects.get(name="Admin"))
        self.admin = self._client(admin)
        emp_user = User.objects.create_user(username="set_emp", password="pass12345")
        emp_user.groups.add(Group.objects.get(name="Employee"))
        Employee.objects.filter(pk=self.colleague.pk).update(user=emp_user, force_password_change=False)
        self.employee = self._client(emp_user)

    @staticmethod
    def _client(user):
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return client

    # ── settings ──────────────────────────────────────────────────────
    def test_hr_cannot_open_settings(self):
        self.assertEqual(self.hr.get(reverse("company-settings-hub")).status_code, 403)
        self.assertEqual(self.hr.get(reverse("settings-page")).status_code, 403)

    def test_hr_and_employees_cannot_save_settings(self):
        for client in (self.hr, self.employee):
            for name in ("save-payroll-settings", "save-leave-settings", "save-leave-credit-policy"):
                with self.subTest(url=name):
                    resp = client.post(reverse(name), {"company_id": self.company.pk, "weekend_days": "sun"})
                    self.assertEqual(resp.status_code, 403)
        self.assertEqual(PayrollSettings.objects.get(company=self.company).weekend_days, "sat_sun")

    def test_admin_still_manages_settings(self):
        self.assertEqual(self.admin.get(reverse("company-settings-hub")).status_code, 200)
        resp = self.admin.post(reverse("save-payroll-settings"), {"company_id": self.company.pk, "weekend_days": "sun"})
        self.assertTrue(resp.json()["success"])

    def test_hr_menu_has_no_settings_or_roles(self):
        page = self.hr.get(reverse("admin-dashboard")).content.decode()
        self.assertNotIn(reverse("company-settings-hub"), page)
        self.assertNotIn(reverse("roles-permissions-hub"), page)
        admin_page = self.admin.get(reverse("admin-dashboard")).content.decode()
        self.assertIn(reverse("company-settings-hub"), admin_page)
        self.assertIn(reverse("roles-permissions-hub"), admin_page)

    # ── advances ──────────────────────────────────────────────────────
    def test_hr_cannot_create_advances(self):
        self.assertEqual(self.hr.get(reverse("create-advance")).status_code, 403)
        resp = self.hr.post(reverse("create-advance"), {
            "employee": self.colleague.pk, "advance_amount": "1000", "default_months": "2", "start_date": "2026-11-01",
        })
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(AdvanceMaster.objects.exists())

    def test_hr_sees_only_their_own_advances_and_no_create_buttons(self):
        mine = AdvanceMaster.objects.create(employee=self.hr_emp, advance_amount=1000, outstanding_amount=1000, default_months=2,
                                            start_date=date(2026, 11, 1))
        theirs = AdvanceMaster.objects.create(employee=self.colleague, advance_amount=2000, outstanding_amount=2000, default_months=2,
                                              start_date=date(2026, 11, 1))
        page = self.hr.get(reverse("advances-list"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, reverse("advance-detail", args=[mine.pk]))
        self.assertNotContains(page, reverse("advance-detail", args=[theirs.pk]))
        self.assertNotContains(page, reverse("create-advance"))
        self.assertEqual(self.hr.get(reverse("advance-detail", args=[theirs.pk])).status_code, 403)
