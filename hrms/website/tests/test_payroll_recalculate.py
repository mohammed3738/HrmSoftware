"""
Regression tests for recalculating a draft payroll run before finalizing.

Feature: HR sometimes needs to adjust attendance, approve/correct leave, or
change an advance AFTER a payroll run has already been generated in draft
status. Previously there was no way to pull those changes into the run
short of deleting and regenerating it. `recalculate_payroll_run()` (and the
"Recalculate" button on the run detail page that calls it) refreshes every
record from current attendance/leave/advance/salary data and recomputes
deductions and net pay, while leaving any field a user already manually
edited on a record untouched.

Run with: python manage.py test website.tests.test_payroll_recalculate
"""
from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from website.models import (
    Company, Employee, Attendance, SalaryMaster, LeaveBalance,
    AdvanceMaster, AdvanceSchedule, PayrollRun, PayrollRecord,
)
from website.services import create_payroll_run, recalculate_payroll_run


class PayrollRecalculateTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="RC", name="Recalc Test Co", phone="1", email="rc@test.com", address="Addr",
        )
        self._code_seq = 0
        self.user = User.objects.create_superuser("admin", "admin@test.com", "pass12345")
        self.client = Client()
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def make_employee(self, first_name, status="Active", date_of_joining=date(2020, 1, 1)):
        self._code_seq += 1
        code = f"RC{self._code_seq:03d}"
        return Employee.objects.create(
            company=self.company, salutation="Mr", first_name=first_name, last_name="Doe",
            father_name="Father", gender="Male", blood_group="O+",
            date_of_birth=date(1990, 1, 1), place_of_birth="City",
            personal_email=f"{code}@test.com", present_address="Addr", permanent_address="Addr",
            personal_mobile="1234567890", employee_code=code, designation="Dev", department="IT",
            date_of_joining=date_of_joining, location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank=first_name,
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status=status,
        )

    def make_salary(self, employee, basic_pm=20000, opted_for_pf=False):
        return SalaryMaster.objects.create(
            employee=employee, is_active=True, gross_ctc_pm=basic_pm * 2, basic_pm=basic_pm,
            hra_pm=0, sp_allowance_pm=0, stat_bonus_pm=0, allowance1_pm=0, allowance2_pm=0,
            pf_deducted=opted_for_pf,
        )

    def mark_present(self, employee, d):
        return Attendance.objects.create(employee=employee, date=d, in_time=time(9, 0), out_time=time(18, 0))

    def test_recalculate_picks_up_attendance_added_after_run_was_generated(self):
        emp = self.make_employee("One")
        self.make_salary(emp)
        for d in range(1, 20):
            self.mark_present(emp, date(2026, 8, d))

        run = create_payroll_run(self.company, date(2026, 8, 1), date(2026, 8, 31))
        rec = PayrollRecord.objects.get(payroll=run, employee=emp)
        initial_present_days = rec.present_days

        # HR later marks the rest of the month present too (e.g. a late upload).
        for d in range(20, 32):
            self.mark_present(emp, date(2026, 8, d))

        result = recalculate_payroll_run(run)
        self.assertEqual(result["refreshed"], 1)
        self.assertEqual(result["added"], 0)

        rec.refresh_from_db()
        self.assertGreater(rec.present_days, initial_present_days)

    def test_recalculate_picks_up_leave_without_pay_correction(self):
        """Pay itself is driven by LeaveBalance.leave_without_pay, not
        present_days directly — this proves a later LWP correction (e.g. a
        leave got approved after the run was generated) flows into net pay."""
        emp = self.make_employee("Six")
        self.make_salary(emp, basic_pm=31000)
        lb = LeaveBalance.objects.create(
            employee=emp, period_from_date=date(2026, 8, 1), period_to_date=date(2026, 8, 31),
            leave_without_pay=5,
        )

        run = create_payroll_run(self.company, date(2026, 8, 1), date(2026, 8, 31))
        rec = PayrollRecord.objects.get(payroll=run, employee=emp)
        self.assertEqual(rec.leave_without_pay, 5)
        net_with_lwp = rec.net_salary

        # HR approves the leave after the fact -> LWP corrected down to 0.
        lb.leave_without_pay = 0
        lb.save()

        recalculate_payroll_run(run)
        rec.refresh_from_db()
        self.assertEqual(rec.leave_without_pay, 0)
        self.assertGreater(rec.net_salary, net_with_lwp)

    def test_recalculate_preserves_manually_overridden_advance(self):
        emp = self.make_employee("Two")
        self.make_salary(emp)
        adv = AdvanceMaster.objects.create(
            employee=emp, advance_amount=6000, default_months=6, outstanding_amount=6000,
        )
        AdvanceSchedule.objects.create(advance=adv, due_month=date(2026, 8, 1), scheduled_amount=1000)

        run = create_payroll_run(self.company, date(2026, 8, 1), date(2026, 8, 31))
        rec = PayrollRecord.objects.get(payroll=run, employee=emp)
        self.assertEqual(rec.advance, 1000)

        # HR manually overrides the advance deduction for this month (e.g. employee requested a skip).
        rec.advance = 0
        rec.manual_override = {"advance": "0.00"}
        rec.save()

        result = recalculate_payroll_run(run)
        self.assertEqual(result["refreshed"], 1)

        rec.refresh_from_db()
        # The manual override must win, even though the schedule still says 1000.
        self.assertEqual(rec.advance, 0)

    def test_recalculate_adds_newly_eligible_employee(self):
        emp1 = self.make_employee("Existing")
        self.make_salary(emp1)
        run = create_payroll_run(self.company, date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(run.records.count(), 1)

        # A new employee joins and gets a salary structure after the run was generated.
        emp2 = self.make_employee("NewJoiner", date_of_joining=date(2026, 8, 5))
        self.make_salary(emp2)

        result = recalculate_payroll_run(run)
        self.assertEqual(result["added"], 1)
        self.assertEqual(run.records.count(), 2)
        self.assertTrue(PayrollRecord.objects.filter(payroll=run, employee=emp2).exists())

    def test_recalculate_leaves_now_inactive_employees_untouched(self):
        emp = self.make_employee("Leaving")
        self.make_salary(emp)
        run = create_payroll_run(self.company, date(2026, 8, 1), date(2026, 8, 31))
        rec = PayrollRecord.objects.get(payroll=run, employee=emp)
        original_net = rec.net_salary

        emp.status = "Inactive"
        emp.save()

        result = recalculate_payroll_run(run)
        self.assertEqual(result["refreshed"], 0)
        self.assertEqual(result["skipped"], 1)

        rec.refresh_from_db()
        self.assertEqual(rec.net_salary, original_net)  # untouched, not deleted or blanked

    def test_recalculate_picks_up_pf_wage_ceiling_setting_change(self):
        emp = self.make_employee("Three")
        self.make_salary(emp, basic_pm=20000, opted_for_pf=True)
        run = create_payroll_run(self.company, date(2026, 8, 1), date(2026, 8, 31))
        rec = PayrollRecord.objects.get(payroll=run, employee=emp)
        self.assertEqual(rec.pf_employee, 1800.00)  # min(20000, 15000) * 12%

        from website.models import PayrollSettings
        ps, _ = PayrollSettings.objects.get_or_create(company=self.company)
        ps.pf_wage_ceiling = 20000.0
        ps.save()

        recalculate_payroll_run(run)
        rec.refresh_from_db()
        self.assertEqual(rec.pf_employee, 2400.00)  # min(20000, 20000) * 12%

    def test_recalculate_endpoint_via_view(self):
        emp = self.make_employee("Four")
        self.make_salary(emp)
        run = create_payroll_run(self.company, date(2026, 8, 1), date(2026, 8, 31))

        resp = self.client.post(reverse("payroll-run-recalculate", args=[run.id]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["refreshed"], 1)

    def test_recalculate_endpoint_rejects_finalized_run(self):
        emp = self.make_employee("Five")
        self.make_salary(emp)
        run = create_payroll_run(self.company, date(2026, 8, 1), date(2026, 8, 31))
        run.status = PayrollRun.STATUS_FINALIZED
        run.save()

        resp = self.client.post(reverse("payroll-run-recalculate", args=[run.id]))
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])
