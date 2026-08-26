"""
Regression tests for employee PF deduction calculation in payroll runs.

The rule (per business confirmation): PF = 12% of the basic actually earned
this period (i.e. basic_processed, already pro-rated for LWP), capped at the
flat statutory contribution (pf_wage_ceiling x pf_percentage, e.g.
15000 x 12% = 1800). So a small LWP for a high earner still leaves PF at the
flat 1800 cap — PF only starts coming down once LWP is heavy enough that
even the full earned basic's 12% drops below 1800.

Two bugs fixed to get here:

1. Wrong cap field: the payroll run engine originally capped PF wage using
   PayrollSettings.basic_cap (default 21000), which is actually meant to cap
   the Basic component when deriving it from Gross CTC during salary
   structuring — not PF. The Salary Structure editor (create_salary4.html)
   separately hardcoded the statutory PF wage ceiling of 15000 (giving
   15000 x 12% = 1800), so the two screens disagreed (payroll run showed
   2520, salary structure showed 1800, for the same employee). Fixed by
   adding a dedicated, configurable PayrollSettings.pf_wage_ceiling field
   (default 15000) and using it consistently in both places.

2. A short-lived attempt to also cap the wage BEFORE pro-rating for LWP
   (instead of after) was reverted: business confirmed PF should be 12% of
   the *earned* basic capped at the flat 1800, not the capped wage pro-rated
   for LWP — e.g. 1 day of LWP for a high earner should NOT quietly reduce
   PF below the flat 1800 cap.

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

    def test_pf_stays_flat_capped_for_a_small_lwp(self):
        # This is the exact case reported live: basic 21000, 1 day LWP out
        # of 31. A small LWP for a high earner must NOT quietly reduce PF
        # below the flat cap -- 12% of the earned basic (still ~20322) is
        # well above 1800, so the flat cap wins either way.
        rec = self.make_record(21000, 31, 1)
        recalc_and_save_record(rec, manual_overrides={})
        self.assertEqual(rec.pf_employee, Decimal("1800.00"))

    def test_pf_drops_below_flat_cap_once_lwp_is_heavy_enough(self):
        # basic 30000, 20 days LWP out of 30 -> earned basic = 10000,
        # 12% of that (1200) is below the flat 1800 cap, so PF must follow
        # the earned amount instead of staying pinned at the cap.
        rec = self.make_record(30000, 30, 20)
        recalc_and_save_record(rec, manual_overrides={})
        self.assertEqual(rec.pf_employee, Decimal("1200.00"))
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
