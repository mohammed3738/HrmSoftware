"""
Regression test for the transaction boundary around finalizing a payroll run.

payroll_run_finalize() recalculates every PayrollRecord in the run and then
flips PayrollRun.status to "finalized". It had no transaction around that:

    for rec in run.records.all():
        recalc_and_save_record(rec, ...)
    run.status = PayrollRun.STATUS_FINALIZED
    run.save()

If recalculating one employee raised -- bad salary data, a null where a
Decimal was expected -- the records processed before it kept their new
figures, the records after it kept their old ones, and the run stayed in
draft. Half of a payroll's pay figures had been rewritten with no record
anywhere that the operation had failed part-way. Its siblings
create_payroll_run() and recalculate_payroll_run() are both
@transaction.atomic, which is what shows this was an omission rather than a
decision.

The test drives a failure into the middle of the loop and asserts the
earlier record was rolled back. It patches recalc_and_save_record in the
views module namespace (where the view looks it up), raising on the second
record only, so the first has definitely already been written when the
error arrives.

Run with:
    python manage.py test website.tests.test_payroll_finalize_atomicity
"""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import (
    Company,
    Employee,
    PayrollRecord,
    PayrollRun,
    PayrollSettings,
    SalaryMaster,
)


class PayrollFinalizeAtomicityTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="PFA", name="Finalize Co", phone="1",
            email="pfa@test.com", address="Addr",
        )
        PayrollSettings.objects.create(company=self.company)

        self.officer = User.objects.create_user(username="pfa_officer", password="pass12345")
        self.officer.groups.add(Group.objects.get(name="Payroll Officer"))

        self.run = PayrollRun.objects.create(
            company=self.company, month=date(2026, 5, 1),
            start_date=date(2026, 5, 1), end_date=date(2026, 5, 31),
        )

        self.records = []
        for n in (1, 2):
            employee = Employee.objects.create(
                company=self.company, salutation="Mr", first_name=f"Emp{n}", last_name="Doe",
                father_name="Father", gender="Male", blood_group="O+",
                date_of_birth=date(1990, 1, 1), place_of_birth="City",
                personal_email=f"pfa00{n}@test.com", present_address="Addr",
                permanent_address="Addr", personal_mobile="1234567890",
                employee_code=f"PFA00{n}", designation="Dev", department="IT",
                date_of_joining=date(2020, 1, 1), location="City",
                pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank=f"Emp{n}",
                salary_account_number="1234567890", ifsc_code="TEST0001234",
                emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
                emergency_contact_mobile1="0987654321", status="Active",
                force_password_change=False,
            )
            SalaryMaster.objects.create(
                employee=employee, is_active=True,
                gross_ctc_pm=Decimal("30000"), basic_pm=Decimal("15000"),
                hra_pm=Decimal("9000"),
            )
            self.records.append(PayrollRecord.objects.create(
                payroll=self.run, employee=employee,
                employee_code=employee.employee_code, employee_name=f"Emp{n} Doe",
                total_days=31, present_days=Decimal("31.00"),
                leave_without_pay=Decimal("0.00"),
                gross_ctc=Decimal("30000"), basic_pm=Decimal("15000"),
                hra_pm=Decimal("9000"), total_gross_salary=Decimal("30000"),
                net_salary=Decimal("0"), gross_processed=Decimal("0"),
            ))

        self.client_officer = Client()
        self.client_officer.force_login(
            self.officer, backend="django.contrib.auth.backends.ModelBackend",
        )

    def _finalize(self):
        return self.client_officer.post(reverse("payroll-run-finalize", args=[self.run.id]))

    def test_successful_finalize_writes_figures_and_marks_the_run(self):
        resp = self._finalize()
        self.assertEqual(resp.status_code, 200)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, PayrollRun.STATUS_FINALIZED)
        for rec in self.records:
            rec.refresh_from_db()
            self.assertGreater(rec.net_salary, Decimal("0"))

    def test_a_failure_midway_rolls_back_the_records_already_written(self):
        import website.views as views_module

        real = views_module.recalc_and_save_record
        calls = {"n": 0}

        def failing(record, manual_overrides=None):
            calls["n"] += 1
            if calls["n"] == 2:
                raise ValueError("bad salary data for this employee")
            return real(record, manual_overrides=manual_overrides)

        with patch.object(views_module, "recalc_and_save_record", failing):
            with self.assertRaises(ValueError):
                self._finalize()

        self.assertEqual(calls["n"], 2, "the failure did not land mid-loop")

        # The first record was saved before the second one blew up. Without a
        # transaction its new net_salary survives; with one it is rolled back.
        self.records[0].refresh_from_db()
        self.assertEqual(
            self.records[0].net_salary, Decimal("0"),
            "a payroll record written before the mid-loop failure was not rolled back",
        )

        self.run.refresh_from_db()
        self.assertEqual(
            self.run.status, PayrollRun.STATUS_DRAFT,
            "the run must stay in draft when finalizing failed",
        )
