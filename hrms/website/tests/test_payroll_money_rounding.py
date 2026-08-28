"""
Regression test: payroll figures (processed components, PF, ESIC, gross,
deductions, net pay) must round to the nearest whole rupee, not paise --
per explicit business request after decimals like 608.44 / 2,608.44 /
48,785.56 started showing up in the payroll run table.

money_int() in website/services/__init__.py implements this and is used
throughout calculate_and_populate_record / calculate_pro_rata /
_build_record_snapshot / get_advance_for_employee_month. Kept separate from
money_d() (2-decimal), which stays in use for day-count fields
(present_days, leave_taken) where a half-day value is correct.

Run with: python manage.py test website.tests.test_payroll_money_rounding
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from website.models import Company, Employee, PayrollRun, PayrollRecord, PayrollSettings, SalaryMaster
from website.services import money_int, recalc_and_save_record, recalculate_payroll_run


class MoneyIntHelperTest(TestCase):
    def test_rounds_half_up_to_nearest_rupee(self):
        self.assertEqual(money_int(Decimal("608.44")), Decimal("608"))
        self.assertEqual(money_int(Decimal("608.50")), Decimal("609"))
        self.assertEqual(money_int(Decimal("608.49")), Decimal("608"))
        self.assertEqual(money_int(0), Decimal("0"))
        self.assertEqual(money_int(None), Decimal("0"))


class PayrollRoundingTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="RND", name="Rounding Co", phone="1", email="rnd@test.com", address="Addr",
        )
        self.settings = PayrollSettings.objects.create(
            company=self.company, pf_percentage=Decimal("12.00"), pf_wage_ceiling=15000.0,
            esic_percentage=Decimal("0.75"), professional_tax=Decimal("200.00"),
        )
        self.employee = Employee.objects.create(
            company=self.company, salutation="Mr", first_name="Round", last_name="Off",
            father_name="Father", gender="Male", blood_group="O+",
            date_of_birth=date(1990, 1, 1), place_of_birth="City",
            personal_email="rnd1@test.com", present_address="Addr", permanent_address="Addr",
            personal_mobile="1234567890", employee_code="RNDEMP1", designation="Dev", department="IT",
            date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Round",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
        )
        self.run = PayrollRun.objects.create(
            company=self.company, month=date(2026, 8, 1),
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 31),
        )

    def test_processed_components_and_deductions_have_no_paise(self):
        # basic 15000 pro-rated over 30 days with 7 LWP days lands on a
        # non-round fraction (15000 * 23/30 = 11500 exactly, so also add HRA
        # to force a genuinely fractional pro-rated amount).
        rec = PayrollRecord.objects.create(
            payroll=self.run, employee=self.employee, employee_code="RNDEMP1",
            opted_for_pf=True, opted_for_esic=True,
            basic_pm=Decimal("15333"), hra_pm=Decimal("4777"),
            total_days=30, leave_without_pay=Decimal("7"),
        )
        recalc_and_save_record(rec, manual_overrides={})

        for field in [
            "basic_processed", "hra_processed", "gross_processed",
            "pf_employee", "esic_employee", "professional_tax",
            "total_deductions", "net_salary",
        ]:
            value = getattr(rec, field)
            self.assertEqual(
                value, value.to_integral_value(),
                f"{field} = {value} has a fractional (paise) component",
            )

    def test_recalculate_payroll_run_produces_whole_rupee_salary_snapshot(self):
        SalaryMaster.objects.create(
            employee=self.employee, is_active=True, esic_applicable=False, pf_deducted=True,
            gross_ctc_pm=Decimal("34810.37"), basic_pm=Decimal("15333.33"),
            hra_pm=Decimal("4777.77"), sp_allowance_pm=Decimal("4000.90"),
        )
        result = recalculate_payroll_run(self.run)
        self.assertEqual(result["added"], 1)

        rec = PayrollRecord.objects.get(payroll=self.run, employee=self.employee)
        for field in ["gross_ctc", "basic_pm", "hra_pm", "sp_allowance_pm"]:
            value = getattr(rec, field)
            self.assertEqual(
                value, value.to_integral_value(),
                f"{field} = {value} has a fractional (paise) component even though it came from a "
                f"decimal-valued Salary Master",
            )
