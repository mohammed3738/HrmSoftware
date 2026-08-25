"""
Regression tests for employee PF deduction calculation in payroll runs.

Two bugs, fixed together:

1. Order-of-operations bug: PF was calculated by pro-rating the basic salary
   for LWP (leave without pay) FIRST, then capping the result against the PF
   wage ceiling. Once an employee's LWP-adjusted basic still exceeded the
   ceiling (true for most earners above it unless they took a lot of LWP),
   PF was pinned at the flat capped amount and never went down for the LWP
   days they actually took. Fixed by capping the full monthly wage first,
   then pro-rating the *capped* wage for LWP, exactly like every other
   salary component.

2. Wrong cap field: the payroll run engine capped PF wage using
   PayrollSettings.basic_cap (default 21000), which is actually meant to cap
   the Basic component when deriving it from Gross CTC during salary
   structuring — not PF. The Salary Structure editor (create_salary4.html)
   separately hardcoded the statutory PF wage ceiling of 15000 (giving
   15000 x 12% = 1800), so the two screens disagreed (payroll run showed
   2520, salary structure showed 1800, for the same employee). Fixed by
   adding a dedicated, configurable PayrollSettings.pf_wage_ceiling field
   (default 15000) and using it consistently in both places.

Run with: python manage.py test website.tests.test_payroll_pf_calculation
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from website.models import Company, Employee, PayrollRun, PayrollRecord, PayrollSettings
from website.services import recalc_and_save_record


class PayrollPFCalculationTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="PFC", name="PF Test Co", phone="1", email="pf@test.com", address="Addr",
        )
        self.settings = PayrollSettings.objects.create(
            company=self.company, pf_percentage=Decimal("12.00"),
            basic_cap=21000.0, pf_wage_ceiling=15000.0,
        )
        self.employee = Employee.objects.create(
            company=self.company, salutation="Mr", first_name="Test", last_name="Employee",
            father_name="Father", gender="Male", blood_group="O+",
            date_of_birth=date(1990, 1, 1), place_of_birth="City",
            personal_email="pfemp@test.com", present_address="Addr", permanent_address="Addr",
            personal_mobile="1234567890", employee_code="PFEMP1", designation="Dev", department="IT",
            date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Test",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
        )
        self.run = PayrollRun.objects.create(
            company=self.company, month=date(2026, 8, 1),
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 31),
        )

    def make_record(self, basic_pm, total_days, lwp, opted_for_pf=True):
        return PayrollRecord.objects.create(
            payroll=self.run, employee=self.employee, employee_code="PFEMP1",
            opted_for_pf=opted_for_pf, basic_pm=Decimal(basic_pm),
            total_days=total_days, leave_without_pay=Decimal(lwp),
        )

    def test_pf_uses_pf_wage_ceiling_not_basic_cap(self):
        # basic (21000) sits between pf_wage_ceiling (15000) and basic_cap
        # (21000) -- PF must be capped at the smaller, statutory figure.
        rec = self.make_record(21000, 30, 0)
        recalc_and_save_record(rec, manual_overrides={})
        self.assertEqual(rec.pf_employee, Decimal("1800.00"))  # 15000 * 12%, matches Salary Structure editor

    def test_pf_scales_down_with_lwp_when_basic_above_ceiling(self):
        # basic (33600) is above the 15000 ceiling; 3 LWP days out of 31.
        rec = self.make_record(33600, 31, 3)
        recalc_and_save_record(rec, manual_overrides={})

        # Old (buggy) behaviour pinned this at 15000 * 12% = 1800.00
        # regardless of LWP. Correct: cap first (15000), then pro-rate for
        # LWP the same as every other component: 15000 * 28/31 * 12%.
        expected = (Decimal("15000") * Decimal(28) / Decimal(31) * Decimal("0.12")).quantize(Decimal("0.01"))
        self.assertEqual(rec.pf_employee, expected)
        self.assertLess(rec.pf_employee, Decimal("1800.00"))

    def test_pf_is_flat_capped_amount_when_no_lwp(self):
        rec = self.make_record(33600, 31, 0)
        recalc_and_save_record(rec, manual_overrides={})
        self.assertEqual(rec.pf_employee, Decimal("1800.00"))  # 15000 * 12%

    def test_pf_uncapped_when_basic_below_ceiling(self):
        # basic (12000) is below the 15000 ceiling -> PF just tracks pro-rated basic.
        rec = self.make_record(12000, 30, 5)
        recalc_and_save_record(rec, manual_overrides={})
        expected = (Decimal("12000") * Decimal(25) / Decimal(30) * Decimal("0.12")).quantize(Decimal("0.01"))
        self.assertEqual(rec.pf_employee, expected)
        self.assertEqual(rec.pf_employee, rec.basic_processed * Decimal("0.12"))

    def test_pf_zero_when_not_opted_in(self):
        rec = self.make_record(33600, 31, 3, opted_for_pf=False)
        recalc_and_save_record(rec, manual_overrides={})
        self.assertEqual(rec.pf_employee, Decimal("0.00"))

    def test_manual_override_still_wins_over_calculated_pf(self):
        rec = self.make_record(33600, 31, 3)
        recalc_and_save_record(rec, manual_overrides={"pf_employee": "1000.00"})
        self.assertEqual(rec.pf_employee, Decimal("1000.00"))

    def test_pf_wage_ceiling_falls_back_to_statutory_default_when_unset(self):
        # A company with no PayrollSettings row at all (edge case) should
        # still get the statutory 15000 ceiling, not an uncapped PF.
        other_company = Company.objects.create(
            short_name="NOSET", name="No Settings Co", phone="1", email="noset@test.com", address="Addr",
        )
        other_run = PayrollRun.objects.create(
            company=other_company, month=date(2026, 8, 1),
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 31),
        )
        rec = PayrollRecord.objects.create(
            payroll=other_run, employee=self.employee, employee_code="PFEMP1",
            opted_for_pf=True, basic_pm=Decimal("33600"), total_days=31, leave_without_pay=Decimal("0"),
        )
        recalc_and_save_record(rec, manual_overrides={})
        self.assertEqual(rec.pf_employee, Decimal("1800.00"))  # 15000 * 12%
