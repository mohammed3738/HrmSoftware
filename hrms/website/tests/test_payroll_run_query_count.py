"""
Query-count guard for payroll run generation.

create_payroll_run() -> generate_records_for_month() walks every active
employee with a salary and builds a PayrollRecord for each. Everything it
needs per employee was fetched per employee, including things that are the
same for the whole run:

  * _build_record_snapshot -> get_attendance_summary() ran
        PayrollSettings.objects.filter(company=employee.company).first()
    once per employee, for a company-level row that cannot change mid-run.
  * recalc_and_save_record() then ran the same PayrollSettings query again
    for every record.

So each employee cost two identical PayrollSettings lookups on top of their
own attendance/salary/leave/advance reads. The count grew strictly linearly
with headcount, which is what this test pins: adding employees must not add
more than a fixed per-employee budget, and the company-level settings row
must be read a bounded number of times no matter the headcount.

The assertion is written as a per-employee *slope* measured between two
run sizes rather than an absolute number, so it keeps its meaning if an
unrelated change adds one constant query somewhere.

Run with:
    python manage.py test website.tests.test_payroll_run_query_count
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from website.models import (
    Attendance,
    Branch,
    Company,
    Employee,
    PayrollSettings,
    SalaryMaster,
)
from website.services import create_payroll_run

PERIOD_START = date(2026, 5, 1)
PERIOD_END = date(2026, 5, 31)


class PayrollRunQueryCountTest(TestCase):
    def _company(self, short_name):
        company = Company.objects.create(
            short_name=short_name, name=f"{short_name} Co", phone="1",
            email=f"{short_name.lower()}@test.com", address="Addr",
        )
        PayrollSettings.objects.create(company=company, weekend_days="sun")
        return company

    def _populate(self, company, count):
        branch = Branch.objects.create(branch_name=f"{company.short_name} Branch")
        for n in range(1, count + 1):
            employee = Employee.objects.create(
                company=company, branch=branch, salutation="Mr",
                first_name=f"Emp{n}", last_name="Doe", father_name="Father",
                gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
                place_of_birth="City",
                personal_email=f"{company.short_name.lower()}{n}@test.com",
                present_address="Addr", permanent_address="Addr",
                personal_mobile="1234567890",
                employee_code=f"{company.short_name}{n:03d}", designation="Dev",
                department="IT", date_of_joining=date(2020, 1, 1), location="City",
                pan_no="ABCDE1234F", aadhar_no="123456789012",
                name_as_per_bank=f"Emp{n}", salary_account_number="1234567890",
                ifsc_code="TEST0001234", emergency_contact_name1="Jane",
                emergency_contact_relation1="Spouse",
                emergency_contact_mobile1="0987654321", status="Active",
                force_password_change=False,
            )
            SalaryMaster.objects.create(
                employee=employee, is_active=True, gross_ctc_pm=Decimal("30000"),
                basic_pm=Decimal("15000"), hra_pm=Decimal("9000"), pf_deducted=True,
            )
            # A few attendance rows each, so get_attendance_summary has work.
            day = PERIOD_START
            while day <= PERIOD_START + timedelta(days=9):
                if day.weekday() != 6:
                    Attendance.objects.create(
                        employee=employee, date=day, status="Present",
                        count=Decimal("1.00"),
                    )
                day += timedelta(days=1)

    def _queries_for(self, short_name, employee_count):
        company = self._company(short_name)
        self._populate(company, employee_count)
        with CaptureQueriesContext(connection) as captured:
            create_payroll_run(company, PERIOD_START, PERIOD_END)
        return captured.captured_queries

    def test_per_employee_query_cost_stays_within_budget(self):
        small = self._queries_for("QA", 2)
        large = self._queries_for("QB", 8)

        slope = (len(large) - len(small)) / 6.0
        # Measured: 15.5 queries/employee before the fix (124 for 8
        # employees), 10.8 after (86 for 8). The budget leaves headroom for
        # an unrelated change without letting the repeats come back.
        self.assertLessEqual(
            slope, 12.0,
            f"payroll run generation costs {slope:.1f} queries per employee "
            f"({len(small)} for 2 employees, {len(large)} for 8) -- the "
            f"per-employee work has grown",
        )

    def test_company_payroll_settings_is_not_re_read_per_employee(self):
        queries = self._queries_for("QC", 8)
        settings_reads = [
            q for q in queries
            if "payrollsettings" in q["sql"].lower() and q["sql"].lstrip().upper().startswith("SELECT")
        ]
        self.assertLessEqual(
            len(settings_reads), 4,
            f"PayrollSettings was read {len(settings_reads)} times while generating "
            f"a run for 8 employees; it is one company-level row for the whole run",
        )

    def test_generated_records_are_still_correct(self):
        """A query-count change must not quietly change the figures."""
        company = self._company("QD")
        self._populate(company, 3)
        run = create_payroll_run(company, PERIOD_START, PERIOD_END)

        self.assertEqual(run.records.count(), 3)
        for record in run.records.all():
            # 31-day period, no LWP -> full monthly components, nothing pro-rated.
            self.assertEqual(record.total_days, 31)
            self.assertEqual(record.leave_without_pay, Decimal("0.00"))
            self.assertEqual(record.basic_processed, Decimal("15000"))
            self.assertEqual(record.hra_processed, Decimal("9000"))
            # PF: 12% of 15000 earned basic = 1800, equal to the flat cap.
            self.assertEqual(record.pf_employee, Decimal("1800"))
