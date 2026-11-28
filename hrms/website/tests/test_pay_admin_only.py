"""
TEMPORARY (Nov 2026): while PAY_ADMIN_ONLY is on, salary structure, salary
slips and advances are for Admin / Super Admin only -- hidden from
Employee, HR, HOD and Payroll Officer in the menu, the dashboards and the
employee details page, and their pages answer 403. Switching it off brings
back the normal per-role behaviour.

Run with: python manage.py test website.tests.test_pay_admin_only
"""
from datetime import date

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from website.models import Company, Employee

PAY_PAGES = ["create-salary", "salary_history", "salary_increment", "salary-slips", "advances-list",
             "create-advance"]


@override_settings(PAY_ADMIN_ONLY=True)
class PayAdminOnlyTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(short_name="PAO", name="Pay Co", phone="1", email="p@t.com", address="A")
        self.n = 0

    def login(self, role):
        self.n += 1
        user = User.objects.create_user(username=f"pao{self.n}", password="pass12345")
        user.groups.add(Group.objects.get(name=role))
        emp = Employee.objects.create(company=self.company, user=user, first_name=role, last_name="X",
                                      employee_code=f"PAO{self.n}", date_of_joining=date(2020, 1, 1),
                                      status="Active", force_password_change=False)
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return client, emp

    def test_hidden_roles_get_403_on_every_pay_page(self):
        for role in ("Employee", "HR", "HOD", "Payroll Officer"):
            client, _ = self.login(role)
            for name in PAY_PAGES:
                self.assertEqual(client.get(reverse(name)).status_code, 403, f"{role} {name}")

    def test_admins_are_not_blocked(self):
        for role in ("Admin", "Super Admin"):
            client, _ = self.login(role)
            for name in PAY_PAGES:
                self.assertNotEqual(client.get(reverse(name)).status_code, 403, f"{role} {name}")

    def test_employee_dashboard_and_menu_hide_pay(self):
        client, emp = self.login("Employee")
        resp = client.get(reverse("employee-dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Recent Payslips")
        self.assertNotContains(resp, "Salary Slips")
        self.assertNotContains(resp, reverse("advances-list"))
        self.assertEqual(list(resp.context["recent_payslips"]), [])

    def test_my_details_hides_salary(self):
        for role in ("Employee", "HR"):
            client, emp = self.login(role)
            resp = client.get(reverse("employee_detail", args=[emp.pk]))
            self.assertEqual(resp.status_code, 200, role)
            self.assertNotContains(resp, "Salary Summary")
            self.assertIsNone(resp.context["salary"])

    def test_hr_menu_hides_salary_structure(self):
        client, _ = self.login("HR")
        resp = client.get(reverse("admin-dashboard"))
        self.assertNotContains(resp, 'href="%s"' % reverse("create-salary"))
        self.assertNotContains(resp, 'href="%s"' % reverse("salary_history"))
        self.assertNotContains(resp, reverse("advances-list"))

    def test_admin_still_sees_everything(self):
        client, emp = self.login("Admin")
        resp = client.get(reverse("admin-dashboard"))
        self.assertContains(resp, 'href="%s"' % reverse("create-salary"))
        self.assertContains(resp, reverse("advances-list"))
        resp = client.get(reverse("employee_detail", args=[emp.pk]))
        self.assertContains(resp, "Salary Summary")


@override_settings(PAY_ADMIN_ONLY=False)
class PaySwitchOffTest(TestCase):
    def test_switch_off_restores_employee_self_service(self):
        company = Company.objects.create(short_name="PAF", name="Pay Off", phone="1", email="o@t.com", address="A")
        user = User.objects.create_user(username="paf", password="pass12345")
        user.groups.add(Group.objects.get(name="Employee"))
        Employee.objects.create(company=company, user=user, first_name="E", last_name="X", employee_code="PAF1",
                                date_of_joining=date(2020, 1, 1), status="Active", force_password_change=False)
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        self.assertNotEqual(client.get(reverse("salary-slips")).status_code, 403)
        self.assertContains(client.get(reverse("employee-dashboard")), "Recent Payslips")
