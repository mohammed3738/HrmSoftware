"""
The "Search employee" box on an attendance page jumps to someone else's
attendance, so an employee looking at their own (My Attendance) must not
get it; someone who can view everyone's attendance still does.

Run with: python manage.py test website.tests.test_attendance_detail_search_box
"""
from datetime import date

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import Company, Employee

BOX = 'id="employeeSearch"'


class AttendanceDetailSearchBoxTest(TestCase):
    def setUp(self):
        company = Company.objects.create(short_name="ASB", name="Search Box Co", phone="1", email="a@t.com", address="A")
        self.emp_user = User.objects.create_user(username="asb_emp", password="pass12345")
        self.emp_user.groups.add(Group.objects.get(name="Employee"))
        self.employee = Employee.objects.create(company=company, user=self.emp_user, first_name="Own", last_name="E",
                                                employee_code="ASB1", date_of_joining=date(2020, 1, 1),
                                                status="Active", force_password_change=False)

    def _page(self, user):
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return client.get(reverse("my_attendance"), follow=True) if user == self.emp_user else \
            client.get(reverse("employee_attendance_detail", args=[self.employee.pk]))

    def test_employee_does_not_see_the_search_box(self):
        resp = self._page(self.emp_user)
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, BOX)

    def test_admin_still_sees_it(self):
        admin = User.objects.create_user(username="asb_admin", password="pass12345")
        admin.groups.add(Group.objects.get(name="Admin"))
        resp = self._page(admin)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, BOX)


class LeaveBalanceSearchBoxTest(AttendanceDetailSearchBoxTest):
    """Same rule on Leave Balance: an employee only ever sees their own row there."""
    BOX = 'id="search-input"'

    def _page(self, user):
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return client.get(reverse("leave_balance_report"))

    def test_employee_does_not_see_the_search_box(self):
        resp = self._page(self.emp_user)
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, self.BOX)

    def test_admin_still_sees_it(self):
        admin = User.objects.create_user(username="lbs_admin", password="pass12345")
        admin.groups.add(Group.objects.get(name="Admin"))
        resp = self._page(admin)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.BOX)
