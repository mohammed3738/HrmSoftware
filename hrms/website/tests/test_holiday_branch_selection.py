"""
A holiday can be given to selected branches only (e.g. Mumbai and
Bangalore); everyone else works as usual.

Run with: python manage.py test website.tests.test_holiday_branch_selection
"""
from datetime import date, time, timedelta

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import (
    Attendance, Branch, Company, Employee, Holiday, HolidayType, PayrollSettings,
)


def next_weekday(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


DAY = next_weekday(date.today() + timedelta(days=10))


class HolidayBranchSelectionTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Br Co", short_name="BRC", address="A")
        PayrollSettings.objects.create(company=self.company, branch_specific_holidays=True)
        self.mumbai = Branch.objects.create(branch_name="Mumbai")
        self.bangalore = Branch.objects.create(branch_name="Bangalore")
        self.delhi = Branch.objects.create(branch_name="Delhi")
        self.staff = {
            b.branch_name: Employee.objects.create(
                company=self.company, branch=b, first_name=b.branch_name, last_name="Emp",
                employee_code=f"BR-{b.branch_name}", status="Active", date_of_joining=date(2020, 1, 1),
            )
            for b in (self.mumbai, self.bangalore, self.delhi)
        }
        self.regional = HolidayType.objects.create(name="Regional", type_category="regional")
        admin = User.objects.create_user(username="br_admin", password="pass12345")
        admin.groups.add(Group.objects.get(name="Admin"))
        self.client = Client()
        self.client.force_login(admin, backend="django.contrib.auth.backends.ModelBackend")

    def _add(self, **extra):
        data = {"holiday_date": DAY.isoformat(), "name": "Local Festival", "holiday_type": self.regional.pk,
                "status": "declared", "description": "", "applies_to_all_employees": "on"}
        data.update(extra)
        return self.client.post(reverse("add-holiday"), data)

    def _status(self, branch_name):
        att = Attendance.objects.filter(employee=self.staff[branch_name], date=DAY).first()
        return att and att.status

    def test_holiday_for_selected_branches_only(self):
        self._add(branch_scope="selected", branches=[self.mumbai.pk, self.bangalore.pk])
        holiday = Holiday.objects.get()
        self.assertFalse(holiday.is_national)
        self.assertEqual(set(holiday.branches.all()), {self.mumbai, self.bangalore})
        self.assertEqual(self._status("Mumbai"), "Holiday")
        self.assertEqual(self._status("Bangalore"), "Holiday")
        self.assertIsNone(self._status("Delhi"))  # no holiday row for Delhi

    def test_delhi_punches_stay_a_working_day(self):
        Attendance.objects.create(employee=self.staff["Delhi"], date=DAY, in_time=time(9, 0), out_time=time(18, 0))
        Attendance.objects.create(employee=self.staff["Mumbai"], date=DAY, in_time=time(9, 0), out_time=time(18, 0))
        self._add(branch_scope="selected", branches=[self.mumbai.pk])
        self.assertEqual(self._status("Delhi"), "Present")
        self.assertEqual(self._status("Mumbai"), "Holiday")  # existing record re-applied

    def test_all_branches(self):
        self._add(branch_scope="all")
        holiday = Holiday.objects.get()
        self.assertTrue(holiday.is_national)
        for name in ("Mumbai", "Bangalore", "Delhi"):
            self.assertEqual(self._status(name), "Holiday")

    def test_selected_without_branches_is_refused(self):
        self._add(branch_scope="selected")
        self.assertFalse(Holiday.objects.exists())

    def test_editing_branches_updates_attendance(self):
        self._add(branch_scope="selected", branches=[self.mumbai.pk, self.bangalore.pk])
        holiday = Holiday.objects.get()
        self.client.post(reverse("edit-holiday", args=[holiday.pk]), {
            "holiday_date": DAY.isoformat(), "name": "Local Festival", "holiday_type": self.regional.pk,
            "status": "declared", "description": "", "applies_to_all_employees": "on",
            "branch_scope": "selected", "branches": [self.mumbai.pk],
        })
        self.assertEqual(set(holiday.branches.all()), {self.mumbai})
        self.assertEqual(self._status("Mumbai"), "Holiday")
        self.assertEqual(self._status("Bangalore"), "Absent")  # no longer a holiday there

    def test_edit_modal_data_and_list_show_branches(self):
        self._add(branch_scope="selected", branches=[self.mumbai.pk, self.bangalore.pk])
        holiday = Holiday.objects.get()
        data = self.client.get(f"/api/holiday/{holiday.pk}/").json()
        self.assertEqual(sorted(data["branch_ids"]), sorted([self.mumbai.pk, self.bangalore.pk]))
        page = self.client.get(reverse("holiday-calendar"))
        self.assertContains(page, "Mumbai, Bangalore")
        self.assertContains(page, 'name="branch_scope"')

    def test_employees_cannot_add_or_edit_holidays(self):
        user = User.objects.create_user(username="br_emp", password="pass12345")
        user.groups.add(Group.objects.get(name="Employee"))
        Employee.objects.filter(pk=self.staff["Delhi"].pk).update(user=user, force_password_change=False)
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        resp = client.post(reverse("add-holiday"), {"holiday_date": DAY.isoformat(), "name": "Sneaky",
                                                   "holiday_type": self.regional.pk, "status": "declared"})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Holiday.objects.exists())
