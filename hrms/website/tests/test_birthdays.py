"""
Birthday announcements on the dashboards.

Run with: python manage.py test website.tests.test_birthdays
"""
from datetime import date, timedelta

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import Company, Employee
from website.views import _upcoming_birthdays


def born_on(day, years_ago=30):
    try:
        return day.replace(year=day.year - years_ago)
    except ValueError:
        return date(day.year - years_ago, 2, 28)


class UpcomingBirthdaysTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Cake Co", short_name="CKC")
        self.other_company = Company.objects.create(name="Other Co", short_name="OTC")

    def _emp(self, code, dob, company=None, status="Active", user=None):
        return Employee.objects.create(
            company=company or self.company, user=user, first_name=code, last_name="X", employee_code=code,
            date_of_birth=dob, status=status, date_of_joining=date(2020, 1, 1), force_password_change=False,
        )

    def test_window_order_and_exclusions(self):
        today = date(2026, 10, 6)
        self._emp("TODAY", date(1990, 10, 6))
        self._emp("TMRW", date(1985, 10, 7))
        self._emp("WEEK", date(1999, 10, 13))
        self._emp("LATER", date(1999, 10, 14))      # 8 days away -> out
        self._emp("PAST", date(1999, 10, 5))        # yesterday -> next year, out
        self._emp("NODOB", None)
        found = _upcoming_birthdays(Employee.objects.all(), today)
        self.assertEqual([b["employee"].employee_code for b in found], ["TODAY", "TMRW", "WEEK"])
        self.assertTrue(found[0]["is_today"])
        self.assertEqual(found[2]["days_away"], 7)

    def test_year_end_wraps(self):
        self._emp("NEWYEAR", date(1990, 1, 2))
        found = _upcoming_birthdays(Employee.objects.all(), date(2026, 12, 30))
        self.assertEqual(found[0]["date"], date(2027, 1, 2))

    def test_leap_day_birthday_on_28_feb(self):
        self._emp("LEAP", date(1996, 2, 29))
        found = _upcoming_birthdays(Employee.objects.all(), date(2027, 2, 28))
        self.assertTrue(found and found[0]["is_today"])

    def test_employee_dashboard_greets_and_lists_only_own_company(self):
        today = date.today()
        user = User.objects.create_user("bd_emp", password="pass12345")
        user.groups.add(Group.objects.get(name="Employee"))
        me = self._emp("ME", born_on(today), user=user)
        self._emp("MATE", born_on(today + timedelta(days=2)))
        self._emp("STRANGER", born_on(today), company=self.other_company)
        self._emp("GONE", born_on(today), status="Left")

        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        resp = client.get(reverse("employee-dashboard"))
        self.assertContains(resp, f"Happy Birthday, {me.first_name}!")
        codes = [b["employee"].employee_code for b in resp.context["birthdays"]]
        self.assertEqual(codes, ["ME", "MATE"])
        self.assertNotContains(resp, str(me.date_of_birth.year))  # never reveal birth year / age

    def test_admin_dashboard_shows_birthdays(self):
        today = date.today()
        self._emp("ADMINSEE", born_on(today))
        admin = User.objects.create_superuser("bd_admin", "bd@test.com", "pass12345")
        client = Client()
        client.force_login(admin, backend="django.contrib.auth.backends.ModelBackend")
        resp = client.get(reverse("admin-dashboard"))
        self.assertContains(resp, "Birthdays")
        self.assertIn("ADMINSEE", [b["employee"].employee_code for b in resp.context["birthdays"]])
