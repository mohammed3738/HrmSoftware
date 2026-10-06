"""
Automatic leave-balance recalculation: the 25th-of-month full refresh, the
per-change recalculation for employees without a company, and the monthly
reset task.

Run with: python manage.py test website.tests.test_leave_balance_auto_recalc
"""
from datetime import date, time
from decimal import Decimal

from django.test import TestCase

from website.models import Attendance, Company, Employee, LeaveBalance, PayrollRun, PayrollSettings
from website.signals import recalculate_all_leave_balances
from website.tasks import auto_process_all_companies_leave_balance, reset_monthly_leave_balances_task

MARCH = (date(2026, 2, 27), date(2026, 3, 26))
APRIL = (date(2026, 3, 27), date(2026, 4, 26))


class LeaveBalanceAutoRecalcTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Recalc Co", short_name="RCO")
        PayrollSettings.objects.create(company=self.company, from_date=27, to_date=26)
        self.employee = self._employee("RC001", self.company)

    def _employee(self, code, company):
        return Employee.objects.create(
            company=company, salutation="Mr", first_name="Emp", last_name=code,
            father_name="F", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email=f"{code}@test.com", present_address="A",
            permanent_address="A", personal_mobile="1234567890", employee_code=code,
            designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Emp",
            salary_account_number="1", ifsc_code="TEST0001234", emergency_contact_name1="J",
            emergency_contact_relation1="Spouse", emergency_contact_mobile1="0987654321", status="Active",
        )

    def _present(self, employee, d):
        Attendance.objects.create(employee=employee, date=d, in_time=time(9, 0), out_time=time(18, 0))

    def _balance(self, employee, period):
        return LeaveBalance.objects.filter(
            employee=employee, period_from_date=period[0], period_to_date=period[1],
        ).first()

    def test_monthly_job_leaves_finalized_period_untouched(self):
        self._present(self.employee, date(2026, 3, 2))
        self._present(self.employee, date(2026, 4, 1))
        PayrollRun.objects.create(
            company=self.company, month=date(2026, 3, 1), start_date=MARCH[0], end_date=MARCH[1],
            status=PayrollRun.STATUS_FINALIZED,
        )
        # Stand-in for the figures the March payslips were built from.
        LeaveBalance.objects.filter(employee=self.employee, period_to_date=MARCH[1]).delete()
        LeaveBalance.objects.create(
            employee=self.employee, period_from_date=MARCH[0], period_to_date=MARCH[1],
            leave_taken=Decimal("9.00"),
        )
        LeaveBalance.objects.filter(employee=self.employee, period_to_date=APRIL[1]).delete()

        result = auto_process_all_companies_leave_balance.apply().get()

        self.assertEqual(self._balance(self.employee, MARCH).leave_taken, Decimal("9.00"))
        self.assertIsNotNone(self._balance(self.employee, APRIL))
        self.assertIn("Recalculated", result)

    def test_employee_without_company_is_recalculated_on_attendance_change(self):
        loner = self._employee("RC002", None)
        self._present(loner, date(2026, 4, 1))
        balance = self._balance(loner, APRIL)
        self.assertIsNotNone(balance)
        self.assertEqual(balance.total_number_of_days, 31)

    def test_employee_without_company_is_included_in_monthly_job(self):
        loner = self._employee("RC003", None)
        self._present(loner, date(2026, 4, 1))
        LeaveBalance.objects.filter(employee=loner).delete()
        recalculate_all_leave_balances()
        self.assertIsNotNone(self._balance(loner, APRIL))

    def test_deleting_employee_leaves_no_orphan_leave_balances(self):
        for employee in (self.employee, self._employee("RC004", None)):
            self._present(employee, date(2026, 4, 1))
            emp_id = employee.id
            employee.delete()
            self.assertFalse(LeaveBalance.objects.filter(employee_id=emp_id).exists())
        Employee.objects.filter(employee_code="RC005").delete()  # queryset delete path too
        queryset_emp = self._employee("RC005", self.company)
        self._present(queryset_emp, date(2026, 4, 2))
        Employee.objects.filter(id=queryset_emp.id).delete()
        self.assertFalse(LeaveBalance.objects.filter(employee_id=queryset_emp.id).exists())

    def test_deleting_single_attendance_still_recalculates(self):
        self._present(self.employee, date(2026, 4, 1))
        self._present(self.employee, date(2026, 4, 2))
        before = self._balance(self.employee, APRIL).number_of_days_present
        Attendance.objects.get(employee=self.employee, date=date(2026, 4, 2)).delete()
        self.assertEqual(self._balance(self.employee, APRIL).number_of_days_present, before - 1)

    def test_reset_task_deletes_nothing(self):
        self._present(self.employee, date(2026, 3, 2))
        self._present(self.employee, date(2026, 4, 1))
        before = LeaveBalance.objects.filter(employee=self.employee).count()
        self.assertGreater(before, 0)
        PayrollSettings.objects.filter(company=self.company).update(
            reset_month=date.today().month, carry_forward=False,
        )

        reset_monthly_leave_balances_task.apply().get()

        self.assertGreaterEqual(LeaveBalance.objects.filter(employee=self.employee).count(), before)
