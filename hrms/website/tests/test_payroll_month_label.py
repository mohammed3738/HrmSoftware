"""
A 27th-26th payroll run is named after the month it ENDS in: 27 Mar - 26 Apr
is April's payroll -- the month picked on the Create form -- not March's.

Run with: python manage.py test website.tests.test_payroll_month_label
"""
from datetime import date
from importlib import import_module

from django.apps import apps
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import Company, PayrollRecord, PayrollRun, PayrollSettings


class PayrollMonthLabelTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(short_name="PML", name="Label Co", phone="1", email="p@t.com",
                                              address="A", status="active")
        PayrollSettings.objects.create(company=self.company, from_date=27, to_date=26)
        admin = User.objects.create_superuser("pml_admin", "pml@test.com", "pass12345")
        self.client = Client()
        self.client.force_login(admin, backend="django.contrib.auth.backends.ModelBackend")

    def test_picking_april_creates_april_payroll(self):
        self.client.post(reverse("payroll-run-create"), {"company": self.company.id, "month": "2026-04"})
        run = PayrollRun.objects.get(company=self.company)
        self.assertEqual((run.start_date, run.end_date), (date(2026, 3, 27), date(2026, 4, 26)))
        self.assertEqual(run.month, date(2026, 4, 1))
        resp = self.client.get(reverse("payroll-run-list"))
        self.assertContains(resp, "April 2026 payroll")
        self.assertNotContains(resp, "March 2026 payroll")

    def test_year_end_cycle(self):
        self.client.post(reverse("payroll-run-create"), {"company": self.company.id, "month": "2026-01"})
        run = PayrollRun.objects.get(company=self.company)
        self.assertEqual((run.start_date, run.month), (date(2025, 12, 27), date(2026, 1, 1)))

    def test_migration_relabels_existing_runs_and_payslips(self):
        run = PayrollRun.objects.create(company=self.company, month=date(2026, 3, 1),
                                        start_date=date(2026, 3, 27), end_date=date(2026, 4, 26),
                                        status=PayrollRun.STATUS_FINALIZED)
        fields = {f.name for f in PayrollRecord._meta.get_fields()}
        record = None
        if "employee" in fields:
            from website.models import Employee
            emp = Employee.objects.create(company=self.company, first_name="A", last_name="B", employee_code="PML1",
                                          date_of_joining=date(2020, 1, 1), status="Active")
            try:
                record = PayrollRecord.objects.create(payroll=run, employee=emp, month_display="Mar 2026")
            except Exception:
                record = None
        migration = import_module("website.migrations.0060_payroll_month_is_ending_month")
        migration.forwards(apps, None)
        run.refresh_from_db()
        self.assertEqual(run.month, date(2026, 4, 1))
        self.assertEqual(run.start_date, date(2026, 3, 27))     # dates untouched
        if record:
            record.refresh_from_db()
            self.assertEqual(record.month_display, "Apr 2026")
