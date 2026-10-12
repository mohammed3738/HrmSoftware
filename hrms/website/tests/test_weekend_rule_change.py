"""
Changing the weekend rule after attendance has been recorded.

Days inside a finalized payroll run keep the rule they were paid under;
every other day -- including those in a draft run -- follows the new rule,
both when the setting is saved and when attendance is recalculated.

Run with: python manage.py test website.tests.test_weekend_rule_change
"""
from datetime import date, time

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import Attendance, Company, Employee, PayrollRun, PayrollSettings

LOCKED_SAT = date(2026, 1, 17)   # inside the finalized January run
DRAFT_SAT = date(2026, 2, 14)    # inside the draft February run
OPEN_SAT = date(2026, 3, 14)     # no run at all
SUNDAY = date(2026, 3, 15)


class WeekendRuleChangeTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(short_name="WKD", name="Weekend Co", address="A")
        self.settings = PayrollSettings.objects.create(company=self.company, weekend_days="sat_sun")
        self.employee = Employee.objects.create(
            company=self.company, first_name="Week", last_name="End", employee_code="WKD1", status="Active",
        )
        self.days = {
            d: Attendance.objects.create(employee=self.employee, date=d, in_time=time(9, 0), out_time=time(18, 0))
            for d in (LOCKED_SAT, DRAFT_SAT, OPEN_SAT, SUNDAY)
        }
        PayrollRun.objects.create(company=self.company, month=date(2026, 1, 1), start_date=date(2026, 1, 1),
                                  end_date=date(2026, 1, 31), status=PayrollRun.STATUS_FINALIZED)
        self.draft = PayrollRun.objects.create(company=self.company, month=date(2026, 2, 1), start_date=date(2026, 2, 1),
                                               end_date=date(2026, 2, 28), status=PayrollRun.STATUS_DRAFT)

        admin = User.objects.create_user(username="wkd_admin", password="pass12345")
        admin.groups.add(Group.objects.get(name="Super Admin"))
        self.client = Client()
        self.client.force_login(admin, backend="django.contrib.auth.backends.ModelBackend")

    def _status(self, day):
        return Attendance.objects.get(employee=self.employee, date=day).status

    def test_recorded_saturdays_start_as_weekends(self):
        for day in (LOCKED_SAT, DRAFT_SAT, OPEN_SAT, SUNDAY):
            self.assertEqual(self._status(day), "Weekend")

    def test_saving_sunday_only_updates_every_unlocked_saturday(self):
        resp = self.client.post(reverse("save-payroll-settings"), {"company_id": self.company.pk, "weekend_days": "sun"})
        self.assertTrue(resp.json()["success"], resp.json())
        self.assertEqual(self._status(OPEN_SAT), "Present")
        self.assertEqual(self._status(DRAFT_SAT), "Present")
        self.assertEqual(self._status(LOCKED_SAT), "Weekend")   # finalized payroll: unchanged
        self.assertEqual(self._status(SUNDAY), "Weekend")
        message = resp.json()["message"]
        self.assertIn("Weekend change applied to 2 attendance day(s)", message)
        self.assertIn("1 draft payroll run(s)", message)
        self.assertIn("1 day(s) in finalized payroll were left unchanged", message)

    def test_switching_back_restores_saturday_weekends_outside_finalized_payroll(self):
        self.client.post(reverse("save-payroll-settings"), {"company_id": self.company.pk, "weekend_days": "sun"})
        self.client.post(reverse("save-payroll-settings"), {"company_id": self.company.pk, "weekend_days": "sat_sun"})
        self.assertEqual(self._status(OPEN_SAT), "Weekend")
        self.assertEqual(self._status(DRAFT_SAT), "Weekend")

    def test_recalculate_tool_follows_the_rule_and_reports_locked_days(self):
        PayrollSettings.objects.filter(pk=self.settings.pk).update(weekend_days="sun")  # no auto-apply
        init = self.client.post(reverse("recalculate_attendance_init")).json()
        self.assertEqual(init["total"], 3)
        self.assertEqual(init["locked"], 1)
        self.client.post(reverse("recalculate_attendance_chunk"), {"offset": 0})
        self.assertEqual(self._status(OPEN_SAT), "Present")
        self.assertEqual(self._status(DRAFT_SAT), "Present")
        self.assertEqual(self._status(LOCKED_SAT), "Weekend")

    def test_employee_without_company_follows_the_shared_rule(self):
        PayrollSettings.objects.filter(pk=self.settings.pk).update(weekend_days="sun")
        PayrollSettings.objects.exclude(pk=self.settings.pk).update(weekend_days="sun")
        loner = Employee.objects.create(first_name="No", last_name="Company", employee_code="WKD2", status="Active")
        att = Attendance.objects.create(employee=loner, date=OPEN_SAT, in_time=time(9, 0), out_time=time(18, 0))
        self.assertEqual(att.status, "Present")

    def test_holiday_calendar_shades_only_the_configured_weekend(self):
        page = self.client.get(reverse("holiday-calendar") + f"?company_id={self.company.pk}")
        self.assertContains(page, "const WEEKEND_DAYS = [0, 6];")
        PayrollSettings.objects.filter(pk=self.settings.pk).update(weekend_days="sun")
        page = self.client.get(reverse("holiday-calendar") + f"?company_id={self.company.pk}")
        self.assertContains(page, "const WEEKEND_DAYS = [0];")
