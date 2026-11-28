"""
Which leave balance periods people see.

- A period that hasn't started yet is never shown, even when some
  attendance carries a future date (a wrong date in an upload or on the
  biometric device). That used to make "27 Dec - 26 Jan" the current period
  in November.
- Employees see a period's balance only once payroll has been run for it.
- Admin/HR still see the current period (they override LWP there before
  running payroll).

Run with: python manage.py test website.tests.test_leave_balance_visibility
"""
from datetime import date, time, timedelta

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import Attendance, Company, Employee, LeaveBalance, PayrollRun, PayrollSettings
from website.signals import recalculate_leave_balance_for_employee, suspend_leave_balance_auto_recalc
from website.views import get_payroll_period_for_date


class LeaveBalanceVisibilityTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(short_name="LBV", name="Vis Co", phone="1", email="v@t.com", address="A")
        self.ps = PayrollSettings.objects.create(company=self.company, from_date=27, to_date=26, weekend_days="sun")
        today = date.today()
        self.current = get_payroll_period_for_date(self.ps, today)
        self.previous = get_payroll_period_for_date(self.ps, self.current[0] - timedelta(days=1))
        # two periods ahead, like the Dec-Jan period seen in November
        nxt = get_payroll_period_for_date(self.ps, self.current[1] + timedelta(days=1))
        self.future = get_payroll_period_for_date(self.ps, nxt[1] + timedelta(days=1))

        self.user = User.objects.create_user(username="lbv_emp", password="pass12345")
        self.user.groups.add(Group.objects.get(name="Employee"))
        self.emp = Employee.objects.create(company=self.company, user=self.user, first_name="Naz", last_name="M",
                                           employee_code="LBV1", date_of_joining=date(2020, 1, 1),
                                           status="Active", force_password_change=False)
        with suspend_leave_balance_auto_recalc():
            for period in (self.previous, self.current, self.future):
                d = period[0]
                for _ in range(5):
                    if d > date.today() and period is self.current:
                        break
                    Attendance.objects.create(employee=self.emp, date=d, in_time=time(9), out_time=time(18))
                    d += timedelta(days=1)
        recalculate_leave_balance_for_employee(self.emp, self.previous[0])
        self.emp_client = Client()
        self.emp_client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def run_payroll(self, period, status=PayrollRun.STATUS_DRAFT):
        PayrollRun.objects.create(company=self.company, month=period[1].replace(day=1),
                                  start_date=period[0], end_date=period[1], status=status)

    def period_values(self, resp):
        return [p["to_date"] for p in resp.context["available_periods"]]

    def test_precondition_a_future_balance_row_exists(self):
        self.assertTrue(LeaveBalance.objects.filter(employee=self.emp, period_from_date=self.future[0]).exists())

    def test_admin_sees_current_period_but_never_a_future_one(self):
        admin = User.objects.create_user(username="lbv_admin", password="pass12345")
        admin.groups.add(Group.objects.get(name="Admin"))
        client = Client()
        client.force_login(admin, backend="django.contrib.auth.backends.ModelBackend")
        resp = client.get(reverse("leave_balance"), {"company_id": self.company.id})
        self.assertEqual(self.period_values(resp)[0], self.current[1])
        self.assertNotIn(self.future[1], self.period_values(resp))
        self.assertEqual(resp.context["selected_period"], str(self.current[1]))

        resp = client.get(reverse("leave_balance"))  # all-companies mode
        values = [m["to_date"] for m in resp.context["available_months"]]
        self.assertIn(self.current[1], values)
        self.assertNotIn(self.future[1], values)

    def test_employee_sees_nothing_until_payroll_is_run(self):
        resp = self.emp_client.get(reverse("leave_balance"))
        self.assertEqual(self.period_values(resp), [])
        self.assertContains(resp, "once payroll has been run")

        self.run_payroll(self.previous)
        resp = self.emp_client.get(reverse("leave_balance"))
        self.assertEqual(self.period_values(resp), [self.previous[1]])
        self.assertEqual(resp.context["selected_period"], str(self.previous[1]))

    def test_a_run_for_a_future_period_still_does_not_show_it(self):
        self.run_payroll(self.future)
        resp = self.emp_client.get(reverse("leave_balance"))
        self.assertNotIn(self.future[1], self.period_values(resp))

    def test_employee_dashboard_follows_the_same_rule(self):
        resp = self.emp_client.get(reverse("employee-dashboard"))
        self.assertIsNone(resp.context["leave_balance"])

        self.run_payroll(self.previous, PayrollRun.STATUS_FINALIZED)
        resp = self.emp_client.get(reverse("employee-dashboard"))
        self.assertEqual(resp.context["leave_balance"].period_to_date, self.previous[1])

        self.run_payroll(self.current)
        resp = self.emp_client.get(reverse("employee-dashboard"))
        self.assertEqual(resp.context["leave_balance"].period_to_date, self.current[1])
