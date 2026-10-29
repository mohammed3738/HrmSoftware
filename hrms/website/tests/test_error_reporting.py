"""
Regression tests for what a user is told when a request goes wrong.

The house pattern in the holiday-calendar handlers was to wrap the whole
view in `except Exception as e` and show the exception:

    messages.error(request, f'Error: {str(e)}')

Two problems. The text is the database's, not the user's -- "duplicate key
value violates unique constraint website_holiday_holiday_date_key" names a
table and a column to whoever provoked it and means nothing to the HR
officer who did. And because the handler swallowed everything, that
message was also the only record that anything had failed: nothing reached
the log, so an error nobody screenshotted never happened.

Now: problems the user can act on (a malformed date, a non-numeric credit)
are caught specifically and described in their own words, and anything
unexpected goes through report_unexpected(), which logs the traceback and
shows a neutral sentence.

Run with:
    python manage.py test website.tests.test_error_reporting
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import (
    Branch,
    Company,
    HalfDayScenario,
    MonthlyEarnedLeaves,
    PayrollSettings,
)


class ErrorReportingTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="ER", name="Error Reporting Co", phone="1",
            email="er@test.com", address="Addr",
        )
        self.branch = Branch.objects.create(branch_name="Main")
        self.settings = PayrollSettings.objects.create(company=self.company)
        self.admin = User.objects.create_user(username="er_admin", password="pass12345")
        self.admin.groups.add(Group.objects.get(name="Super Admin"))
        self.client_admin = Client()
        self.client_admin.force_login(
            self.admin, backend="django.contrib.auth.backends.ModelBackend",
        )
        self.earned_leave, _ = MonthlyEarnedLeaves.objects.get_or_create(
            payroll_settings=self.settings, month=4, year=2026,
            defaults={"earned_leaves": Decimal("2.00")},
        )

    def _messages(self, resp):
        return [str(m) for m in resp.wsgi_request._messages]

    def _post(self, name, data, args=None):
        return self.client_admin.post(
            reverse(name, args=args or []), data, follow=True,
        )

    # ── actionable problems get actionable words ─────────────────────────

    def test_a_non_numeric_earned_leave_is_explained_not_dumped(self):
        resp = self._post(
            "edit-earned-leave", {"earned_leaves": "two and a half"},
            args=[self.earned_leave.pk],
        )
        text = " ".join(str(m) for m in resp.context["messages"])
        self.assertIn("decimal numbers", text.lower() + text)
        self.assertNotIn("InvalidOperation", text)
        self.assertNotIn("Traceback", text)

    def test_a_malformed_half_day_date_is_explained(self):
        resp = self._post("add-half-day-scenario", {
            "scenario_date": "31-06-2026", "description": "Flood",
            "scenario_type": "other", "credit_count": "0.50", "branch": "all",
        })
        text = " ".join(str(m) for m in resp.context["messages"])
        self.assertIn("YYYY-MM-DD", text)
        self.assertNotIn("ValueError", text)
        self.assertFalse(HalfDayScenario.objects.filter(description="Flood").exists())

    def test_a_non_numeric_credit_is_explained(self):
        resp = self._post("add-half-day-scenario", {
            "scenario_date": "2026-06-01", "description": "Rain",
            "scenario_type": "other", "credit_count": "half", "branch": "all",
        })
        text = " ".join(str(m) for m in resp.context["messages"])
        self.assertIn("credit", text.lower())
        self.assertNotIn("InvalidOperation", text)

    # ── unexpected problems are logged, and described neutrally ──────────

    def test_an_unexpected_failure_is_logged_and_not_shown_verbatim(self):
        import website.views as views_module

        def boom(*args, **kwargs):
            raise RuntimeError("relation \"website_payrollsettings\" does not exist")

        original = views_module.MonthlyEarnedLeaves.generate_for_payroll_settings
        views_module.MonthlyEarnedLeaves.generate_for_payroll_settings = boom
        try:
            with self.assertLogs("website.views", level="ERROR") as logged:
                resp = self._post("save-holiday-settings", {
                    "financial_year_start_month": "1",
                    "branch_specific_holidays": "false",
                    "company_id": str(self.company.pk),
                })
        finally:
            views_module.MonthlyEarnedLeaves.generate_for_payroll_settings = original

        text = " ".join(str(m) for m in resp.context["messages"])
        self.assertIn("Something went wrong", text)
        self.assertNotIn("does not exist", text)
        self.assertNotIn("RuntimeError", text)

        # ...but the real cause did reach the log, with its traceback.
        logged_text = "\n".join(logged.output)
        self.assertIn("does not exist", logged_text)
        self.assertIn("Traceback", logged_text)

    # ── the happy paths still work ───────────────────────────────────────

    def test_a_valid_earned_leave_edit_still_succeeds(self):
        self._post("edit-earned-leave", {"earned_leaves": "3.5"},
                   args=[self.earned_leave.pk])
        self.earned_leave.refresh_from_db()
        self.assertEqual(self.earned_leave.earned_leaves, Decimal("3.50"))

    def test_a_valid_half_day_scenario_is_still_created(self):
        self._post("add-half-day-scenario", {
            "scenario_date": "2026-06-01", "description": "Legitimate",
            "scenario_type": "other", "credit_count": "0.50", "branch": "all",
        })
        self.assertTrue(HalfDayScenario.objects.filter(description="Legitimate").exists())
