"""
Regression tests for the Attendance Register (muster roll): a day-by-day
attendance matrix combining the Leave Balance summary columns with one
column per calendar day in the selected payroll period. Per-day cells are
edited via the existing override_attendance_status endpoint -- this test
file focuses on the new view's data assembly (day columns, bulk Attendance
fetch, LeaveBalance summary reuse) and confirms it composes correctly with
that pre-existing override endpoint.

Run with: python manage.py test website.tests.test_attendance_register
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse

from website.models import (
    Attendance, Branch, Company, Employee, LeaveBalance, PayrollSettings,
)


class AttendanceRegisterTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="AREG", name="Attendance Register Co", phone="1", email="areg@test.com", address="Addr",
        )
        # No from_date/to_date configured -> falls back to calendar month,
        # so the March 2026 period is exactly 1 Mar - 31 Mar.
        self.payroll_settings = PayrollSettings.objects.create(company=self.company)
        self.branch = Branch.objects.create(branch_name="HQ")

        self.admin = User.objects.create_user(username="areg_admin", password="pass12345")
        self.admin.groups.add(Group.objects.get(name="Admin"))
        self.client = Client()
        self.client.login(username="areg_admin", password="pass12345")

        self.employee = Employee.objects.create(
            company=self.company, branch=self.branch, salutation="Mr", first_name="Reg", last_name="Ister",
            father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email="reg@test.com", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890", employee_code="AREG1",
            designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Reg",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
        )

        # A handful of Attendance rows within March 2026 -- deliberately NOT
        # every day, so the "no Attendance row" blank-cell path is exercised.
        # status_overridden=True is required here: Attendance.save() always
        # recomputes status/count from in_time/out_time via
        # calculate_status() unless this flag is set, which would otherwise
        # silently discard the status/count set below (in_time/out_time are
        # left unset in this fixture, so calculate_status() would compute
        # every row as Absent).
        Attendance.objects.create(employee=self.employee, date=date(2026, 3, 2), status="Present", count=Decimal("1.00"), status_overridden=True)
        Attendance.objects.create(employee=self.employee, date=date(2026, 3, 3), status="Half Day", count=Decimal("0.50"), status_overridden=True)
        Attendance.objects.create(employee=self.employee, date=date(2026, 3, 4), status="Absent", count=Decimal("0.00"), status_overridden=True)
        Attendance.objects.create(employee=self.employee, date=date(2026, 3, 5), status="Late Present", count=Decimal("1.00"), status_overridden=True)
        # 6 Mar 2026 is a Friday -- left with no Attendance row at all.

        self.lb = LeaveBalance.objects.create(
            employee=self.employee, period_from_date=date(2026, 3, 1), period_to_date=date(2026, 3, 31),
            opening_balance=Decimal("2.00"), leave_taken=Decimal("1.50"), late=6,
            compoff=Decimal("0.00"), leave_without_pay=Decimal("0.00"),
            number_of_days_present=Decimal("20.00"), total_number_of_days=31,
            closing_balance=Decimal("3.00"), final_leave_balance=Decimal("3.00"),
        )

    def get_register(self):
        # The logged-in Admin is a global-access user with no linked
        # Employee record, so (matching the view's designed single-company
        # scoping) it must be told explicitly which company to view.
        return self.client.get(reverse("attendance-register"), {
            "period": "2026-03-31", "company_id": self.company.id,
        })

    def test_day_columns_span_the_full_selected_period(self):
        resp = self.get_register()
        self.assertEqual(resp.status_code, 200)
        day_columns = resp.context["day_columns"]
        self.assertEqual(day_columns[0]["date"], date(2026, 3, 1))
        self.assertEqual(day_columns[-1]["date"], date(2026, 3, 31))
        self.assertEqual(len(day_columns), 31)

    def test_weekend_days_are_flagged_and_working_days_are_not(self):
        resp = self.get_register()
        day_columns = {c["date"]: c for c in resp.context["day_columns"]}
        # 1 Mar 2026 is a Sunday, 2 Mar 2026 is a Monday.
        self.assertTrue(day_columns[date(2026, 3, 1)]["is_weekend"])
        self.assertFalse(day_columns[date(2026, 3, 2)]["is_weekend"])

    def test_per_day_values_reflect_actual_attendance_records(self):
        resp = self.get_register()
        row = resp.context["rows"][0]
        days_by_date = {d["date"]: d for d in row["days"]}

        present_day = days_by_date[date(2026, 3, 2)]
        self.assertEqual(present_day["display"], "1")
        self.assertIsNotNone(present_day["attendance_id"])

        half_day = days_by_date[date(2026, 3, 3)]
        self.assertEqual(half_day["display"], "0.5")

        absent_day = days_by_date[date(2026, 3, 4)]
        self.assertEqual(absent_day["display"], "")
        self.assertIsNotNone(absent_day["attendance_id"])  # still overridable

    def test_day_with_no_attendance_row_is_blank_and_not_overridable(self):
        resp = self.get_register()
        row = resp.context["rows"][0]
        days_by_date = {d["date"]: d for d in row["days"]}
        blank_day = days_by_date[date(2026, 3, 6)]
        self.assertEqual(blank_day["display"], "")
        self.assertIsNone(blank_day["attendance_id"])

    def test_weekend_cell_always_shows_credited_and_is_not_overridable(self):
        resp = self.get_register()
        row = resp.context["rows"][0]
        days_by_date = {d["date"]: d for d in row["days"]}
        sunday = days_by_date[date(2026, 3, 1)]
        self.assertEqual(sunday["display"], "1")
        self.assertIsNone(sunday["attendance_id"])

    def test_summary_columns_match_the_leavebalance_row(self):
        resp = self.get_register()
        row = resp.context["rows"][0]
        self.assertEqual(row["lb"], self.lb)
        self.assertEqual(row["lb"].opening_balance, Decimal("2.00"))
        self.assertEqual(row["lb"].final_leave_balance, Decimal("3.00"))

    def test_late_deduction_is_derived_from_late_count(self):
        # late=6, grace of 5 free lates -> (6-5)//3 = 0
        resp = self.get_register()
        self.assertEqual(resp.context["rows"][0]["late_deduction"], 0)

        self.lb.late = 11  # (11-5)//3 = 2
        self.lb.save(update_fields=["late"])
        resp2 = self.get_register()
        self.assertEqual(resp2.context["rows"][0]["late_deduction"], 2)

    def test_bulk_attendance_fetch_is_not_n_plus_one(self):
        for code in ("AREG2", "AREG3"):
            Employee.objects.create(
                company=self.company, branch=self.branch, salutation="Mr", first_name="Reg", last_name=code,
                father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
                place_of_birth="City", personal_email=f"{code}@test.com", present_address="Addr",
                permanent_address="Addr", personal_mobile="1234567890", employee_code=code,
                designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), location="City",
                pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Reg",
                salary_account_number="1234567890", ifsc_code="TEST0001234",
                emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
                emergency_contact_mobile1="0987654321", status="Active",
            )
        with CaptureQueriesContext(connection) as ctx:
            resp = self.get_register()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["rows"]), 3)
        # A handful of fixed queries (auth/session, permission checks,
        # payroll settings, employees, leave balances, attendance,
        # pagination count) regardless of employee/day count -- NOT one
        # query per employee-day, which for 3 employees x 31 days (93
        # employee-days) would blow far past this bound if it regressed to
        # N+1 (a per-cell lookup would need ~93 extra queries on top).
        self.assertLess(len(ctx.captured_queries), 30)

    def test_manager_can_view_register(self):
        manager = User.objects.create_user(username="areg_mgr", password="pass12345")
        manager.groups.add(Group.objects.get(name="Manager"))
        client = Client()
        client.login(username="areg_mgr", password="pass12345")
        resp = client.get(reverse("attendance-register"))
        self.assertEqual(resp.status_code, 200)

    def test_employee_cannot_view_register(self):
        emp_user = User.objects.create_user(username="areg_emp", password="pass12345")
        emp_user.groups.add(Group.objects.get(name="Employee"))
        client = Client()
        client.login(username="areg_emp", password="pass12345")
        resp = client.get(reverse("attendance-register"))
        self.assertEqual(resp.status_code, 403)

    def test_hr_sees_compoff_override_control(self):
        hr_user = User.objects.create_user(username="areg_hr", password="pass12345")
        hr_user.groups.add(Group.objects.get(name="HR"))
        client = Client()
        client.login(username="areg_hr", password="pass12345")
        resp = client.get(reverse("attendance-register"), {
            "period": "2026-03-31", "company_id": self.company.id,
        })
        self.assertTrue(resp.context["can_edit_compoff"])
        self.assertContains(resp, 'onclick="startCompoffEdit(this)"')

    def test_manager_does_not_see_compoff_override_control(self):
        # leave_management:edit is Admin/HR only -- Manager gets view-only.
        manager = User.objects.create_user(username="areg_mgr2", password="pass12345")
        manager.groups.add(Group.objects.get(name="Manager"))
        client = Client()
        client.login(username="areg_mgr2", password="pass12345")
        resp = client.get(reverse("attendance-register"), {
            "period": "2026-03-31", "company_id": self.company.id,
        })
        self.assertFalse(resp.context["can_edit_compoff"])
        self.assertNotContains(resp, 'onclick="startCompoffEdit(this)"')

    def test_compoff_override_updates_the_row_on_the_spot(self):
        resp = self.client.post(reverse("override-compoff"), {
            "lb_id": self.lb.id, "compoff_value": "1.00",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])

        self.lb.refresh_from_db()
        self.assertEqual(self.lb.compoff, Decimal("1.00"))
        self.assertTrue(self.lb.compoff_overridden)

        resp2 = self.get_register()
        row = resp2.context["rows"][0]
        self.assertEqual(row["lb"].compoff, Decimal("1.00"))

    def test_composes_correctly_with_the_existing_override_endpoint(self):
        """The register must reflect a correction made through the
        pre-existing override_attendance_status endpoint -- proving it
        reads live data, not a stale snapshot, and that no separate
        override mechanism was accidentally introduced."""
        absent_att = Attendance.objects.get(employee=self.employee, date=date(2026, 3, 4))
        resp = self.client.post(reverse("override_attendance_status"), {
            "attendance_id": absent_att.id, "new_status": "Present",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])

        resp2 = self.get_register()
        row = resp2.context["rows"][0]
        days_by_date = {d["date"]: d for d in row["days"]}
        corrected_day = days_by_date[date(2026, 3, 4)]
        self.assertEqual(corrected_day["display"], "1")
        self.assertEqual(corrected_day["status"], "Present")

        absent_att.refresh_from_db()
        self.assertTrue(absent_att.status_overridden)
