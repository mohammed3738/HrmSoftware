"""
Changing "earned leaves per year" must regenerate the monthly earned leaves
shown in Holiday Management, whichever screen saves it, and Holiday
Management must show the company that was changed.

Run with: python manage.py test website.tests.test_earned_leaves_sync
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import Company, MonthlyEarnedLeaves, PayrollSettings


class EarnedLeavesSyncTest(TestCase):
    def setUp(self):
        self.first = Company.objects.create(name="A First Co", short_name="AFC")
        self.second = Company.objects.create(name="B Second Co", short_name="BSC")
        self.ps_first = PayrollSettings.objects.create(company=self.first, earned_leaves_per_year=12)
        self.ps_second = PayrollSettings.objects.create(company=self.second, earned_leaves_per_year=12)
        self.admin = User.objects.create_superuser("el_admin", "el@test.com", "pass12345")
        self.client = Client()
        self.client.force_login(self.admin, backend="django.contrib.auth.backends.ModelBackend")

    def _values(self, ps):
        return set(MonthlyEarnedLeaves.objects.filter(payroll_settings=ps).values_list("earned_leaves", flat=True))

    def test_any_save_regenerates_auto_months(self):
        self.assertEqual(self._values(self.ps_second), {Decimal("1.00")})
        self.ps_second.earned_leaves_per_year = 24   # e.g. a save from Django admin
        self.ps_second.save()
        self.assertEqual(self._values(self.ps_second), {Decimal("2.00")})
        self.assertEqual(self._values(self.ps_first), {Decimal("1.00")})  # other company untouched

    def test_manual_month_is_kept(self):
        manual = MonthlyEarnedLeaves.objects.filter(payroll_settings=self.ps_second).first()
        manual.earned_leaves = Decimal("3.50")
        manual.is_auto_generated = False
        manual.save()
        self.ps_second.earned_leaves_per_year = 24
        self.ps_second.save()
        manual.refresh_from_db()
        self.assertEqual(manual.earned_leaves, Decimal("3.50"))

    def test_holiday_management_shows_the_selected_company(self):
        self.ps_second.earned_leaves_per_year = 24
        self.ps_second.save()

        resp = self.client.get(reverse("holiday-calendar"), {"company_id": self.second.id, "tab": "earned"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["selected_company"], self.second)
        self.assertEqual({l.earned_leaves for l in resp.context["monthly_leaves"]}, {Decimal("2.00")})
        self.assertContains(resp, "B Second Co: 24 earned leaves per year")

        resp = self.client.get(reverse("holiday-calendar"))
        self.assertEqual(resp.context["selected_company"], self.first)
        self.assertEqual(len(resp.context["settings_companies"]), 2)
