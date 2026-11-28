"""
Dashboard "Absent Today": everyone without a punch-in today, including
people with no attendance row at all yet -- but not someone whose day is a
weekend or a holiday, who hasn't joined, or who is out on field duty.
Approved leave is listed and marked "On leave".

Birthdays: every user sees every active employee's birthday, across all
companies.

Run with: python manage.py test website.tests.test_absent_today_and_birthdays
"""
from datetime import date, time, timedelta
from unittest import mock

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import Attendance, BiometricPunch, Company, Employee, LeaveApplication, PayrollSettings
from website.views import _absent_today

WEDNESDAY = date(2026, 11, 18)
SUNDAY = date(2026, 11, 22)


class AbsentTodayTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(short_name="ABT", name="Absent Co", phone="1", email="a@t.com", address="A")
        PayrollSettings.objects.create(company=self.company, weekend_days="sun")
        n = 0

        def emp(code, **kw):
            nonlocal n
            n += 1
            kw.setdefault("date_of_joining", date(2020, 1, 1))
            return Employee.objects.create(company=self.company, first_name=code, last_name="X",
                                           employee_code=code, status="Active", **kw)
        self.punched = emp("PUNCHED")
        self.no_row = emp("NOROW")
        self.marked_absent = emp("MARKED")
        self.on_leave = emp("LEAVE")
        self.not_joined = emp("FUTURE", date_of_joining=WEDNESDAY + timedelta(days=10))
        self.left = emp("LEFT")
        self.left.status = "Left"
        self.left.save()

        Attendance.objects.create(employee=self.punched, date=WEDNESDAY, in_time=time(9, 5))
        Attendance.objects.create(employee=self.marked_absent, date=WEDNESDAY)
        LeaveApplication.objects.create(employee=self.on_leave, start_date=WEDNESDAY, end_date=WEDNESDAY,
                                        status="Approved", reason="x")

    def _codes(self, day):
        return {a.employee.employee_code: a.remark for a in _absent_today(Employee.objects.all(), day)}

    def test_working_day(self):
        self.assertEqual(self._codes(WEDNESDAY), {"NOROW": "No punch", "MARKED": "No punch", "LEAVE": "On leave"})

    def test_midnight_placeholder_and_real_midnight_shift(self):
        Attendance.objects.filter(employee=self.marked_absent).update(in_time=time.min, out_time=time.min, status="Present")
        Attendance.objects.filter(employee=self.punched).update(in_time=time.min, out_time=time(8))
        codes = self._codes(WEDNESDAY)
        self.assertEqual(codes["MARKED"], "No punch")
        self.assertNotIn("PUNCHED", codes)

    def test_device_check_in_precedes_attendance_rollup(self):
        BiometricPunch.objects.create(employee=self.no_row, device_user_id="42", punch_date=WEDNESDAY,
                                      punch_time=time(9), direction="IN")
        self.assertNotIn("NOROW", self._codes(WEDNESDAY))

    def test_team_roster_list_and_count_use_same_workday(self):
        from website.views import _team_panel_for
        Employee.objects.exclude(pk=self.punched.pk).update(manager=self.punched)
        panel = _team_panel_for(self.punched, WEDNESDAY)
        self.assertEqual(panel["team_absent_today"], 2)
        self.assertEqual({r["employee"].employee_code: r["status"] for r in panel["team_today"]},
                         {"MARKED": "No punch", "NOROW": "No punch", "LEAVE": "On leave"})
        self.assertEqual(len(panel["absent_employees_today"]), 3)

    def test_weekend_lists_nobody(self):
        self.assertEqual(self._codes(SUNDAY), {})

    def test_field_duty_is_not_absent(self):
        from website.models import FieldDuty
        field = {f.name for f in FieldDuty._meta.get_fields()}
        if "duty_date" not in field:
            self.skipTest("FieldDuty has no duty_date")
        with mock.patch("website.views.FieldDuty.objects.filter") as fd:
            fd.return_value.values_list.return_value = [self.no_row.pk]
            self.assertNotIn("NOROW", self._codes(WEDNESDAY))

    def test_dashboard_shows_people_without_any_row(self):
        admin = User.objects.create_user(username="abt_admin", password="pass12345")
        admin.groups.add(Group.objects.get(name="Admin"))
        client = Client()
        client.force_login(admin, backend="django.contrib.auth.backends.ModelBackend")
        with mock.patch("website.views.timezone.localdate", return_value=WEDNESDAY), mock.patch("website.views.now") as n:
            n.return_value.date.return_value = WEDNESDAY
            resp = client.get(reverse("admin-dashboard"))
        self.assertEqual(resp.status_code, 200)
        codes = {a.employee.employee_code for a in resp.context["absent_employees_today"]}
        self.assertEqual(codes, {"NOROW", "MARKED", "LEAVE"})
        self.assertContains(resp, "No punch")


class BirthdaysForEveryoneTest(TestCase):
    def test_employee_sees_birthdays_from_other_companies(self):
        today = date.today()
        c1 = Company.objects.create(short_name="BD1", name="BD One", phone="1", email="b1@t.com", address="A")
        c2 = Company.objects.create(short_name="BD2", name="BD Two", phone="1", email="b2@t.com", address="A")
        user = User.objects.create_user(username="bd_emp", password="pass12345")
        user.groups.add(Group.objects.get(name="Employee"))
        Employee.objects.create(company=c1, user=user, first_name="Me", last_name="Self", employee_code="BD1",
                                date_of_joining=date(2020, 1, 1), status="Active", force_password_change=False)
        Employee.objects.create(company=c2, first_name="Far", last_name="Away", employee_code="BD2",
                                date_of_joining=date(2020, 1, 1), status="Active",
                                date_of_birth=today.replace(year=1990) if not (today.month == 2 and today.day == 29)
                                else date(1990, 2, 28))
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        resp = client.get(reverse("employee-dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("BD2", {b["employee"].employee_code for b in resp.context["birthdays"]})
        self.assertContains(resp, "Far Away")
