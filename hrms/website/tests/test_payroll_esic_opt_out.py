"""
Regression test: an employee with "Include ESIC?" set to No in their Salary
Structure was still getting ESIC deducted in the payroll run.

Root cause: calculate_and_populate_record's ESIC calculation only checked
gross_processed <= esic_threshold -- it never consulted the salary
structure's esic_applicable flag at all (unlike PF, which was correctly
gated on opted_for_pf). PayrollRecord had no field to even carry that flag.

Fixed by adding PayrollRecord.opted_for_esic (mirroring opted_for_pf),
populated from SalaryMaster.esic_applicable in _build_record_snapshot, and
gating the ESIC calculation on it, same as PF.

Run with: python manage.py test website.tests.test_payroll_esic_opt_out
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.test import TestCase

from website.models import (
    Company, Employee, PayrollRun, PayrollRecord, PayrollSettings, SalaryMaster,
)
from website.services import recalc_and_save_record, recalculate_payroll_run


class PayrollEsicOptOutTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="ESO", name="ESIC OptOut Co", phone="1", email="eso@test.com", address="Addr",
        )
        self.settings = PayrollSettings.objects.create(
            company=self.company, esic_percentage=Decimal("0.75"),
        )
        self.employee = Employee.objects.create(
            company=self.company, salutation="Mr", first_name="Ayyub", last_name="Khan",
            father_name="Father", gender="Male", blood_group="O+",
            date_of_birth=date(1990, 1, 1), place_of_birth="City",
            personal_email="eso1@test.com", present_address="Addr", permanent_address="Addr",
            personal_mobile="1234567890", employee_code="ESOEMP1", designation="Dev", department="IT",
            date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Ayyub",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
        )
        self.run = PayrollRun.objects.create(
            company=self.company, month=date(2026, 8, 1),
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 31),
        )

    def make_record(self, basic_pm, hra_pm, sp_pm, total_days, lwp, opted_for_esic):
        return PayrollRecord.objects.create(
            payroll=self.run, employee=self.employee, employee_code="ESOEMP1",
            opted_for_esic=opted_for_esic,
            basic_pm=Decimal(basic_pm), hra_pm=Decimal(hra_pm), sp_allowance_pm=Decimal(sp_pm),
            total_days=total_days, leave_without_pay=Decimal(lwp),
        )

    def test_esic_zero_when_not_opted_in_even_if_gross_under_threshold(self):
        # Gross (33600 + 0 + 17794 = well under 21000 after LWP proration in
        # this scenario) would trigger ESIC under the old threshold-only
        # check -- but esic_applicable is off, so it must stay zero.
        rec = self.make_record(15000, 0, 4000, total_days=30, lwp=5, opted_for_esic=False)
        recalc_and_save_record(rec, manual_overrides={})
        self.assertEqual(rec.esic_employee, Decimal("0.00"))

    def test_esic_calculated_when_opted_in_and_under_threshold(self):
        rec = self.make_record(15000, 0, 4000, total_days=30, lwp=5, opted_for_esic=True)
        recalc_and_save_record(rec, manual_overrides={})
        # Payroll amounts round to the nearest whole rupee at each step
        # (gross_processed first, then ESIC off of that rounded gross).
        expected_gross = ((Decimal("15000") + Decimal("4000")) * Decimal(25) / Decimal(30)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        expected_esic = (expected_gross * Decimal("0.75") / Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        self.assertEqual(rec.esic_employee, expected_esic)
        self.assertGreater(rec.esic_employee, Decimal("0.00"))

    def test_esic_zero_when_opted_in_but_gross_over_threshold(self):
        rec = self.make_record(25000, 10000, 5000, total_days=30, lwp=0, opted_for_esic=True)
        recalc_and_save_record(rec, manual_overrides={})
        self.assertEqual(rec.esic_employee, Decimal("0.00"))

    def test_manual_override_still_wins_over_opted_out_esic(self):
        rec = self.make_record(15000, 0, 4000, total_days=30, lwp=0, opted_for_esic=False)
        recalc_and_save_record(rec, manual_overrides={"esic_employee": "250.00"})
        self.assertEqual(rec.esic_employee, Decimal("250.00"))

    def test_recalculate_payroll_run_picks_up_esic_opt_out_from_salary_master(self):
        """The exact live scenario reported: a record already exists in a
        draft run showing a nonzero ESIC deduction; the employee's salary
        structure has ESIC set to No. Hitting Recalculate must zero it out."""
        salary = SalaryMaster.objects.create(
            employee=self.employee, is_active=True, esic_applicable=False,
            gross_ctc_pm=Decimal("34810"), basic_pm=Decimal("15000"),
            hra_pm=Decimal("0"), sp_allowance_pm=Decimal("4000"),
        )
        # Simulate a stale/buggy record already showing an ESIC deduction
        # from before this fix, as in the reported screenshot.
        rec = PayrollRecord.objects.create(
            payroll=self.run, employee=self.employee, employee_code="ESOEMP1",
            opted_for_esic=True, basic_pm=Decimal("15000"), sp_allowance_pm=Decimal("4000"),
            total_days=30, leave_without_pay=Decimal("0"), esic_employee=Decimal("608.44"),
        )
        recalculate_payroll_run(self.run)
        rec.refresh_from_db()
        self.assertFalse(rec.opted_for_esic)
        self.assertEqual(rec.esic_employee, Decimal("0.00"))
