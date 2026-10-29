"""
Regression tests for three small defects that each had a way of producing
a wrong number or an unhandled crash rather than an error message.

1. get_advance_for_employee_month() called .first() on an unordered
   queryset. An employee repaying two advances at once had whichever EMI
   the database happened to return deducted from their pay, and not
   necessarily the same one when the run was recalculated. Now ordered by
   due month, then id.

2. services.revert_skip() computed `outstanding // remaining_count` with
   no guard. Reverting the skip of the last outstanding month, when every
   other month is already paid, leaves nothing pending -- so the division
   raised ZeroDivisionError and the revert was lost.

3. PayrollSettings.esic_threshold did not exist. calculate_and_populate_
   record() read it with getattr(..., "esic_threshold", 21000), so the
   fallback was the only value it could ever take, while the code (and
   test_payroll_esic_opt_out's docstring) read as though a company could
   configure its own ESIC ceiling. It is a real field now, defaulting to
   the same 21000, so behaviour is unchanged for every existing company
   and the setting does what it says.

Run with:
    python manage.py test website.tests.test_advance_and_payroll_edge_cases
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from website.models import (
    AdvanceMaster,
    AdvanceSchedule,
    Company,
    Employee,
    PayrollRecord,
    PayrollRun,
    PayrollSettings,
)
from website.services import (
    calculate_and_populate_record,
    create_advance,
    get_advance_for_employee_month,
    revert_skip,
    skip_month,
)


def make_employee(company, code, first_name):
    return Employee.objects.create(
        company=company, salutation="Mr", first_name=first_name, last_name="Doe",
        father_name="Father", gender="Male", blood_group="O+",
        date_of_birth=date(1990, 1, 1), place_of_birth="City",
        personal_email=f"{code}@test.com", present_address="Addr",
        permanent_address="Addr", personal_mobile="1234567890",
        employee_code=code, designation="Dev", department="IT",
        date_of_joining=date(2020, 1, 1), location="City", pan_no="ABCDE1234F",
        aadhar_no="123456789012", name_as_per_bank=first_name,
        salary_account_number="1234567890", ifsc_code="TEST0001234",
        emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
        emergency_contact_mobile1="0987654321", status="Active",
        force_password_change=False,
    )


class AdvanceEmiSelectionTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="AE", name="Advance Edge Co", phone="1",
            email="ae@test.com", address="Addr",
        )
        self.employee = make_employee(self.company, "AE001", "Borrower")

    def test_the_earliest_due_emi_in_the_period_is_the_one_deducted(self):
        """Two advances, both with an EMI due in May. The one due earliest
        wins, deterministically, however the rows happen to be stored."""
        later = AdvanceMaster.objects.create(
            employee=self.employee, advance_amount=6000, default_months=3,
            outstanding_amount=6000, start_date=date(2026, 5, 15),
        )
        AdvanceSchedule.objects.create(
            advance=later, due_month=date(2026, 5, 15), scheduled_amount=2000)

        earlier = AdvanceMaster.objects.create(
            employee=self.employee, advance_amount=3000, default_months=3,
            outstanding_amount=3000, start_date=date(2026, 5, 1),
        )
        AdvanceSchedule.objects.create(
            advance=earlier, due_month=date(2026, 5, 1), scheduled_amount=1000)

        amount = get_advance_for_employee_month(
            self.employee, date(2026, 5, 1), date(2026, 5, 31))
        self.assertEqual(amount, Decimal("1000"))

    def test_the_same_answer_comes_back_every_time(self):
        create_advance(self.employee, 9000, 3, start_date=date(2026, 5, 1))
        create_advance(self.employee, 6000, 3, start_date=date(2026, 5, 1))
        answers = {
            get_advance_for_employee_month(
                self.employee, date(2026, 5, 1), date(2026, 5, 31))
            for _ in range(5)
        }
        self.assertEqual(len(answers), 1, f"EMI selection is not stable: {answers}")

    def test_no_emi_in_the_period_means_no_deduction(self):
        create_advance(self.employee, 3000, 3, start_date=date(2026, 5, 1))
        amount = get_advance_for_employee_month(
            self.employee, date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual(amount, Decimal("0"))


class RevertSkipTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="RS", name="Revert Skip Co", phone="1",
            email="rs@test.com", address="Addr",
        )
        self.employee = make_employee(self.company, "RS001", "Skipper")

    def test_reverting_a_skip_with_nothing_left_pending_does_not_crash(self):
        advance = create_advance(self.employee, 3000, 3, start_date=date(2026, 5, 1))
        schedules = list(advance.schedules.order_by("due_month"))

        # Pay off everything except the middle month, then skip that one.
        for schedule in (schedules[0], schedules[2]):
            schedule.paid_amount = schedule.scheduled_amount
            schedule.status = AdvanceSchedule.STATUS_PAID
            schedule.save()
        skip_month(advance, schedules[1].due_month)

        advance.refresh_from_db()
        for schedule in advance.schedules.filter(status=AdvanceSchedule.STATUS_PENDING):
            schedule.paid_amount = schedule.scheduled_amount
            schedule.status = AdvanceSchedule.STATUS_PAID
            schedule.save()
        advance.outstanding_amount = 0
        advance.save()

        # Nothing pending left to spread a balance over. This used to raise
        # ZeroDivisionError and lose the revert entirely.
        reverted = revert_skip(advance, schedules[1].due_month)
        self.assertEqual(
            reverted.schedules.get(due_month=schedules[1].due_month).status, "pending")

    def test_an_ordinary_revert_still_redistributes_the_balance(self):
        advance = create_advance(self.employee, 3000, 3, start_date=date(2026, 5, 1))
        schedules = list(advance.schedules.order_by("due_month"))
        skip_month(advance, schedules[1].due_month)

        advance.refresh_from_db()
        revert_skip(advance, schedules[1].due_month)

        advance.refresh_from_db()
        pending_total = sum(
            s.scheduled_amount
            for s in advance.schedules.filter(status=AdvanceSchedule.STATUS_PENDING)
        )
        self.assertEqual(pending_total, advance.outstanding_amount)


class EsicThresholdSettingTest(TestCase):
    """The ESIC ceiling is a real, configurable field now. The default must
    reproduce exactly what the hardcoded 21000 produced before."""

    def setUp(self):
        self.company = Company.objects.create(
            short_name="ET", name="Esic Threshold Co", phone="1",
            email="et@test.com", address="Addr",
        )
        self.settings = PayrollSettings.objects.create(
            company=self.company, esic_percentage=Decimal("0.75"),
        )
        self.employee = make_employee(self.company, "ET001", "Insured")
        self.run = PayrollRun.objects.create(
            company=self.company, month=date(2026, 5, 1),
            start_date=date(2026, 5, 1), end_date=date(2026, 5, 31),
        )

    def _record(self, gross):
        return PayrollRecord.objects.create(
            payroll=self.run, employee=self.employee,
            employee_code="ET001", employee_name="Insured Doe",
            total_days=31, leave_without_pay=Decimal("0.00"),
            opted_for_esic=True, opted_for_pf=False,
            gross_ctc=gross, basic_pm=gross, total_gross_salary=gross,
        )

    def test_the_field_defaults_to_the_figure_that_was_hardcoded(self):
        self.assertEqual(self.settings.esic_threshold, Decimal("21000.00"))

    def test_gross_under_the_default_ceiling_is_deducted(self):
        result = calculate_and_populate_record(
            self._record(Decimal("20000")), self.run, self.settings)
        # 0.75% of 20000 = 150
        self.assertEqual(result["esic_employee"], Decimal("150"))

    def test_gross_over_the_default_ceiling_is_not(self):
        result = calculate_and_populate_record(
            self._record(Decimal("25000")), self.run, self.settings)
        self.assertEqual(result["esic_employee"], Decimal("0"))

    def test_raising_the_ceiling_now_actually_changes_the_outcome(self):
        """The point of the fix: before, this setting could not be changed,
        because there was no field to change."""
        self.settings.esic_threshold = Decimal("30000.00")
        self.settings.save()
        result = calculate_and_populate_record(
            self._record(Decimal("25000")), self.run, self.settings)
        # 0.75% of 25000 = 187.50, rounded to whole rupees = 188
        self.assertEqual(result["esic_employee"], Decimal("188"))
