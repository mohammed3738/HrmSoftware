"""
The "Reporting Line" card on the employee dashboard and profile page.

Run with: python manage.py test website.tests.test_reporting_line_card
"""
from datetime import date

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import Company, Employee


class ReportingLineCardTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Line Co", short_name="LNC")
        self.boss = self._employee("RL001", "Rita", "Boss", designation="Team Lead")
        self.big_boss = self._employee("RL002", "Manny", "Ger", designation="Head of Sales")
        self.user = User.objects.create_user("rl_emp", password="pass12345")
        self.user.groups.add(Group.objects.get(name="Employee"))
        self.me = self._employee("RL003", "Emma", "Ploy", user=self.user)
        self.client = Client()
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def _employee(self, code, first, last, user=None, designation="Dev"):
        return Employee.objects.create(
            company=self.company, user=user, first_name=first, last_name=last, employee_code=code,
            designation=designation, status="Active", date_of_joining=date(2020, 1, 1),
            use_department_defaults=False, force_password_change=False,
        )

    def _set(self, rp, mgr):
        Employee.objects.filter(pk=self.me.pk).update(reporting_person=rp, manager=mgr)

    def test_dashboard_shows_both_people(self):
        self._set(self.boss, self.big_boss)
        resp = self.client.get(reverse("employee-dashboard"))
        self.assertContains(resp, "My Reporting Line")
        self.assertContains(resp, "Rita Boss")
        self.assertContains(resp, "Team Lead")
        self.assertContains(resp, "Manny Ger")
        self.assertContains(resp, "Set individually")

    def test_same_person_shown_once(self):
        self._set(self.boss, self.boss)
        resp = self.client.get(reverse("employee-dashboard"))
        self.assertContains(resp, "Reporting Person &amp; Manager")
        self.assertContains(resp, "Rita Boss", count=1)

    def test_nothing_set(self):
        self._set(None, None)
        resp = self.client.get(reverse("employee-dashboard"))
        self.assertContains(resp, "No reporting person or manager has been set yet")

    def test_profile_page_shows_reporting_line(self):
        self._set(self.boss, self.big_boss)
        resp = self.client.get(reverse("employee_detail", args=[self.me.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Reporting Line")
        self.assertContains(resp, "Manny Ger")
