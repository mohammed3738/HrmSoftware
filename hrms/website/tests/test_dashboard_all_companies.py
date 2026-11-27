"""Absent Today and Birthdays on the dashboards list people from every
company in the group, for every role -- not only the viewer's own company."""
from datetime import date

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from website.models import Company, Employee, PayrollSettings


class DashboardAllCompaniesTest(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.home = Company.objects.create(short_name="HOME", name="Home Co", phone="1", email="h@t.com", address="A")
        self.other = Company.objects.create(short_name="OTH", name="Other Co", phone="1", email="o@t.com", address="A")
        for c in (self.home, self.other):
            PayrollSettings.objects.create(company=c, weekend_days="none")
        # In the other company: absent today (no punch), birthday today.
        Employee.objects.create(company=self.other, first_name="Faraway", last_name="Absent", employee_code="OTH1",
                                date_of_joining=date(2020, 1, 1), status="Active",
                                date_of_birth=date(1990, self.today.month, min(self.today.day, 28)))

    def login(self, role):
        user = User.objects.create_user(username=f"dash_{role}", password="pass12345")
        user.groups.add(Group.objects.get(name=role))
        Employee.objects.create(company=self.home, user=user, first_name=role, last_name="V",
                                employee_code=f"H{role[:3]}", date_of_joining=date(2020, 1, 1),
                                status="Active", force_password_change=False)
        c = Client()
        c.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return c

    def assert_sees_other_company(self, resp):
        names = [a.employee.employee_code for a in resp.context["absent_employees_today"]]
        self.assertIn("OTH1", names)
        self.assertContains(resp, "Absent Today")
        self.assertContains(resp, "Faraway")
        self.assertContains(resp, "<th>Company</th>", html=True)

    def test_employee_sees_other_companies(self):
        self.assert_sees_other_company(self.login("Employee").get(reverse("employee-dashboard")))

    def test_main_dashboard_roles_see_other_companies(self):
        for role in ("Payroll Officer", "HR", "Admin"):
            with self.subTest(role=role):
                self.assert_sees_other_company(self.login(role).get(reverse("admin-dashboard")))
