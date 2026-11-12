"""
The logo in the header takes you to your own dashboard (it used to point at
a leftover theme file, index.html, which 404s).

Run with: python manage.py test website.tests.test_logo_link
"""
import re
from datetime import date

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import Company, Employee


class LogoLinkTest(TestCase):
    def setUp(self):
        company = Company.objects.create(short_name="LGO", name="Logo Co", phone="1", email="l@t.com", address="A")
        self.emp_user = User.objects.create_user(username="lgo_emp", password="pass12345")
        self.emp_user.groups.add(Group.objects.get(name="Employee"))
        Employee.objects.create(company=company, user=self.emp_user, first_name="L", last_name="E", employee_code="LGO1",
                                date_of_joining=date(2020, 1, 1), status="Active", force_password_change=False)
        self.admin = User.objects.create_user(username="lgo_admin", password="pass12345")
        self.admin.groups.add(Group.objects.get(name="Admin"))

    def _logo_href(self, user, url_name):
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        html = client.get(reverse(url_name), follow=True).content.decode()
        return re.search(r'<a href="([^"]*)" class="app-brand-link', html).group(1)

    def test_employee_logo_goes_to_employee_dashboard(self):
        self.assertEqual(self._logo_href(self.emp_user, "my_attendance"), reverse("employee-dashboard"))

    def test_admin_logo_goes_to_admin_dashboard(self):
        self.assertEqual(self._logo_href(self.admin, "admin-dashboard"), reverse("admin-dashboard"))
