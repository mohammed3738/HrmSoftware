"""
Salary History: Admin / Super Admin / Payroll Officer see everyone's; HR
sees only their own -- on the list, the export, the detail popup, the
compare view and the chart data.

Run with: python manage.py test website.tests.test_salary_history_scope
"""
import io
from datetime import date

import openpyxl
from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import Company, Employee, SalaryHistory


class SalaryHistoryScopeTest(TestCase):
    def setUp(self):
        company = Company.objects.create(name="Sal Co", short_name="SAL", address="A")
        self.hr_user = User.objects.create_user(username="sal_hr", password="pass12345")
        self.hr_user.groups.add(Group.objects.get(name="HR"))
        self.hr_emp = Employee.objects.create(company=company, user=self.hr_user, first_name="Hr", last_name="Person",
                                              employee_code="SALHR", status="Active", force_password_change=False)
        self.colleague = Employee.objects.create(company=company, first_name="Col", last_name="League",
                                                 employee_code="SALCO", status="Active")
        data = {"salary": {"net_salary_pm": "1000"}}
        self.mine = SalaryHistory.objects.create(employee=self.hr_emp, data=data,
                                                 start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
        self.theirs = SalaryHistory.objects.create(employee=self.colleague, data=data,
                                                   start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
        self.hr = Client()
        self.hr.force_login(self.hr_user, backend="django.contrib.auth.backends.ModelBackend")
        admin = User.objects.create_user(username="sal_admin", password="pass12345")
        admin.groups.add(Group.objects.get(name="Admin"))
        self.admin = Client()
        self.admin.force_login(admin, backend="django.contrib.auth.backends.ModelBackend")

    def _codes(self, client):
        resp = client.get(reverse("salary_history"))
        self.assertEqual(resp.status_code, 200)
        return {h.employee.employee_code for h in resp.context["history"]}

    def test_hr_list_shows_only_their_own(self):
        self.assertEqual(self._codes(self.hr), {"SALHR"})
        resp = self.hr.get(reverse("salary_history"))
        self.assertEqual([e.employee_code for e in resp.context["employees"]], ["SALHR"])

    def test_admin_list_shows_everyone(self):
        self.assertEqual(self._codes(self.admin), {"SALHR", "SALCO"})

    def test_hr_export_contains_only_their_own(self):
        resp = self.hr.get(reverse("salary_history_export_excel"))
        ws = openpyxl.load_workbook(io.BytesIO(resp.content)).active
        self.assertEqual([r[0] for r in ws.iter_rows(min_row=2, values_only=True)], ["SALHR"])

    def test_hr_cannot_open_a_colleagues_history(self):
        self.assertEqual(self.hr.get(reverse("salary_history_detail", args=[self.theirs.pk])).status_code, 403)
        self.assertEqual(self.hr.get(reverse("salary_compare", args=[self.theirs.pk, self.colleague.pk])).status_code, 403)
        self.assertEqual(self.hr.get(reverse("salary_timeline_data", args=[self.colleague.pk])).status_code, 403)
        self.assertEqual(self.hr.get(reverse("salary_history_detail", args=[self.mine.pk])).status_code, 200)
        self.assertEqual(self.hr.get(reverse("salary_timeline_data", args=[self.hr_emp.pk])).status_code, 200)

    def test_admin_opens_anyones_history(self):
        self.assertEqual(self.admin.get(reverse("salary_history_detail", args=[self.theirs.pk])).status_code, 200)
        self.assertEqual(self.admin.get(reverse("salary_compare", args=[self.theirs.pk, self.colleague.pk])).status_code, 200)

    def test_current_salary_lookup_needs_salary_edit_rights(self):
        url = reverse("employee_details_ajax") + f"?employee_id={self.colleague.pk}"
        self.assertEqual(self.hr.get(url).status_code, 403)
        self.assertEqual(self.admin.get(url).status_code, 200)
