"""
1. A leave counts only working days: the employee's weekly offs and the
   holidays that apply to them are not leave.
2. HR (leave view, no approve) sees every leave request with its status on
   the dashboard, read-only; approvers keep their approve panel.

Run with: python manage.py test website.tests.test_leave_working_days
"""
from datetime import date

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import Company, Employee, Holiday, HolidayType, LeaveApplication, PayrollSettings

# Week of 6-12 Dec 2027: Mon 6 ... Sun 12.
MON, TUE, WED, THU, FRI, SAT, SUN = (date(2027, 12, d) for d in range(6, 13))
NEXT_MON = date(2027, 12, 13)


class LeaveWorkingDaysTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(short_name="LWD", name="Leave Days", phone="1", email="l@t.com", address="A")
        PayrollSettings.objects.create(company=self.company, weekend_days="sun")
        self.user = User.objects.create_user(username="lwd_emp", password="pass12345")
        self.user.groups.add(Group.objects.get(name="Employee"))
        self.emp = Employee.objects.create(company=self.company, user=self.user, first_name="Lea", last_name="V",
                                           employee_code="LWD1", date_of_joining=date(2020, 1, 1),
                                           status="Active", force_password_change=False)

    def leave(self, start, end):
        return LeaveApplication(employee=self.emp, start_date=start, end_date=end, reason="x")

    def test_company_weekly_off_is_not_counted(self):
        self.assertEqual(self.leave(FRI, NEXT_MON).total_days(), 3)   # Fri, Sat, Mon (Sun off)
        self.assertEqual(self.leave(FRI, NEXT_MON).calendar_days(), 4)

    def test_employees_own_weekly_offs_are_not_counted(self):
        self.emp.week_off_days = "5,6"           # Sat + Sun
        self.emp.save()
        self.assertEqual(self.leave(FRI, NEXT_MON).total_days(), 2)   # Fri, Mon

    def test_holiday_is_not_counted(self):
        su = User.objects.create_superuser("lwd_su", "s@t.com", "pass12345")
        Holiday.objects.create(holiday_date=WED, name="Festival", created_by=su,
                               holiday_type=HolidayType.objects.create(name="National", type_category="national"))
        self.assertEqual(self.leave(MON, FRI).total_days(), 4)

    def test_applying_reports_working_days(self):
        c = Client()
        c.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")
        resp = c.post(reverse("leave_apply"), {"start_date": FRI, "end_date": NEXT_MON, "reason": "Trip"}, follow=True)
        self.assertContains(resp, "3 working day(s)")
        self.assertTrue(LeaveApplication.objects.filter(employee=self.emp).exists())

    def test_range_of_only_days_off_is_refused(self):
        c = Client()
        c.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")
        resp = c.post(reverse("leave_apply"), {"start_date": SUN, "end_date": SUN, "reason": "x"}, follow=True)
        self.assertContains(resp, "no working days")
        self.assertFalse(LeaveApplication.objects.filter(employee=self.emp).exists())


class HrLeaveOverviewTest(TestCase):
    def setUp(self):
        company = Company.objects.create(short_name="HLO", name="Overview Co", phone="1", email="o@t.com", address="A")
        PayrollSettings.objects.create(company=company, weekend_days="sun")
        emp = Employee.objects.create(company=company, first_name="Req", last_name="E", employee_code="HLO1",
                                      date_of_joining=date(2020, 1, 1), status="Active")
        for status, reason in (("Pending", "waiting"), ("Approved", "granted"), ("Rejected", "declined")):
            LeaveApplication.objects.create(employee=emp, start_date=MON, end_date=TUE, reason=reason, status=status)

    def client_for(self, role):
        user = User.objects.create_user(username=f"hlo_{role}", password="pass12345")
        user.groups.add(Group.objects.get(name=role))
        c = Client()
        c.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return c

    def test_hr_sees_every_status_read_only(self):
        resp = self.client_for("HR").get(reverse("admin-dashboard"))
        self.assertTrue(resp.context["show_leave_overview"])
        self.assertEqual({l.status for l in resp.context["leave_overview"]}, {"Pending", "Approved", "Rejected"})
        self.assertContains(resp, "view only")
        self.assertNotContains(resp, 'id="leaveBulkApproveBtn"')

    def test_approvers_keep_their_own_panel(self):
        resp = self.client_for("Admin").get(reverse("admin-dashboard"))
        self.assertFalse(resp.context["show_leave_overview"])
        self.assertContains(resp, 'id="leaveBulkApproveBtn"')
