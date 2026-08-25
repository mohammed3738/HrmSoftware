"""
Regression tests for the "All Companies" bulk-create option on the Process
Payroll page: instead of creating a payroll run for one company at a time,
selecting "All Companies" creates a draft run for every active company for
the chosen month in one action, skipping any company that already has one.
Run with: python manage.py test website.tests.test_payroll_run_create_all_companies
"""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from website.models import Company, PayrollRun, PayrollSettings


class PayrollRunCreateAllCompaniesTest(TestCase):
    def setUp(self):
        self.company1 = Company.objects.create(short_name="C1", name="Company One", phone="1", email="c1@test.com", address="Addr")
        self.company2 = Company.objects.create(short_name="C2", name="Company Two", phone="2", email="c2@test.com", address="Addr")
        self.inactive_company = Company.objects.create(
            short_name="C3", name="Inactive Co", phone="3", email="c3@test.com", address="Addr", status="inactive",
        )
        self.user = User.objects.create_superuser("admin", "admin@test.com", "pass12345")
        self.client = Client()
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def test_all_companies_creates_a_run_per_active_company(self):
        resp = self.client.post(reverse("payroll-run-create"), {"company": "all", "month": "2026-08"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("payroll-run-list"))

        self.assertTrue(PayrollRun.objects.filter(company=self.company1).exists())
        self.assertTrue(PayrollRun.objects.filter(company=self.company2).exists())
        self.assertFalse(PayrollRun.objects.filter(company=self.inactive_company).exists())
        self.assertEqual(PayrollRun.objects.count(), 2)
        for run in PayrollRun.objects.all():
            self.assertEqual(run.status, PayrollRun.STATUS_DRAFT)

    def test_all_companies_skips_companies_that_already_have_a_run(self):
        PayrollSettings.objects.create(company=self.company1)
        # Pre-create a run for company1 covering the calendar-month fallback period.
        PayrollRun.objects.create(
            company=self.company1, month=date(2026, 8, 1),
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 31),
        )

        resp = self.client.post(reverse("payroll-run-create"), {"company": "all", "month": "2026-08"})
        self.assertEqual(resp.status_code, 302)

        # company1 still has exactly its pre-existing run (not duplicated);
        # company2 got a new one created.
        self.assertEqual(PayrollRun.objects.filter(company=self.company1).count(), 1)
        self.assertTrue(PayrollRun.objects.filter(company=self.company2).exists())

    def test_single_company_creation_still_works(self):
        resp = self.client.post(reverse("payroll-run-create"), {"company": str(self.company1.id), "month": "2026-08"})
        self.assertEqual(resp.status_code, 302)
        run = PayrollRun.objects.get(company=self.company1)
        self.assertEqual(resp.url, reverse("payroll-run-detail", args=[run.id]))
