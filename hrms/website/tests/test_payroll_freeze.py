"""
What a finalized payroll run actually freezes.

Finalizing is meant to make a period historical: once payslips are out, the
numbers behind them must not move. This file probes every write path that
touches a finalized period and records which are blocked and which are not,
so the freeze's real boundary is written down rather than assumed.

The lock itself lives in website/utils/payroll_lock.py and is consulted by
each write path individually -- there is no middleware catching them all,
which is exactly why this file enumerates them.

Run with: python manage.py test website.tests.test_payroll_freeze
"""
from datetime import date, time
from decimal import Decimal

from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse

from website.models import (
    Attendance, AttendanceCorrectionRequest, Company, CompOffRequest, Employee,
    LeaveApplication, LeaveBalance, PayrollRecord, PayrollRun, PayrollSettings,
)

# The finalized period, and a day inside it.
PERIOD_START = date(2026, 1, 1)
PERIOD_END = date(2026, 1, 31)
LOCKED_DAY = date(2026, 1, 15)   # a Thursday
OPEN_DAY = date(2026, 2, 12)     # a Thursday in the following, open period


class PayrollFreezeTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="FRZ", name="Freeze Co", phone="1", email="frz@test.com", address="Addr",
        )
        PayrollSettings.objects.create(company=self.company)

        self.employee_user = User.objects.create_user(username="frz_emp", password="pass12345")
        self.employee_user.groups.add(Group.objects.get(name="Employee"))
        self.employee = Employee.objects.create(
            company=self.company, user=self.employee_user, salutation="Mr",
            first_name="Frozen", last_name="Employee", father_name="Father", gender="Male",
            date_of_birth=date(1990, 1, 1), personal_email="frz@test.com",
            personal_mobile="1234567890", employee_code="FRZ001", designation="Dev",
            department="IT", date_of_joining=date(2020, 1, 1), status="Active",
            force_password_change=False,
        )

        self.admin_user = User.objects.create_user(username="frz_admin", password="pass12345")
        self.admin_user.groups.add(Group.objects.get(name="Super Admin"))
        self.admin = Client()
        self.admin.force_login(self.admin_user, backend="django.contrib.auth.backends.ModelBackend")

        self.locked_attendance = Attendance.objects.create(
            employee=self.employee, date=LOCKED_DAY, in_time=time(10, 0), out_time=time(17, 0),
        )
        self.open_attendance = Attendance.objects.create(
            employee=self.employee, date=OPEN_DAY, in_time=time(10, 0), out_time=time(17, 0),
        )

        self.run = PayrollRun.objects.create(
            company=self.company, month=PERIOD_START,
            start_date=PERIOD_START, end_date=PERIOD_END,
            status=PayrollRun.STATUS_FINALIZED,
        )
        self.record = PayrollRecord.objects.create(
            payroll=self.run, employee=self.employee, employee_code="FRZ001",
        )

    def _employee_client(self):
        client = Client()
        client.force_login(self.employee_user, backend="django.contrib.auth.backends.ModelBackend")
        return client

    # ── the payroll run itself ────────────────────────────────────────

    def test_a_finalized_run_cannot_be_finalized_again(self):
        resp = self.admin.post(reverse("payroll-run-finalize", args=[self.run.id]))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("already finalized", resp.json()["error"])

    def test_a_finalized_run_cannot_be_recalculated(self):
        resp = self.admin.post(reverse("payroll-run-recalculate", args=[self.run.id]))
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])

    def test_a_finalized_runs_records_cannot_be_edited(self):
        resp = self.admin.post(
            reverse("payroll-record-update", args=[self.record.id]),
            data='{"present_days": "20"}', content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("finalized", resp.json()["error"].lower())

    # ── attendance inside the locked period ───────────────────────────

    def test_attendance_status_cannot_be_overridden_in_a_locked_period(self):
        resp = self.admin.post(reverse("override_attendance_status"), {
            "attendance_id": self.locked_attendance.id, "new_status": "Present",
        })
        self.assertEqual(resp.status_code, 400)
        self.locked_attendance.refresh_from_db()
        self.assertNotEqual(self.locked_attendance.status, "Present")

    def test_the_same_override_still_works_in_an_open_period(self):
        resp = self.admin.post(reverse("override_attendance_status"), {
            "attendance_id": self.open_attendance.id, "new_status": "Present",
        })
        self.assertEqual(resp.status_code, 200)
        self.open_attendance.refresh_from_db()
        self.assertEqual(self.open_attendance.status, "Present")

    def test_bulk_override_is_blocked_for_locked_days(self):
        resp = self.admin.post(
            reverse("bulk_override_attendance_status"),
            data='{"ids": [%d], "new_status": "Present"}' % self.locked_attendance.id,
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["approved"] if "approved" in resp.json() else resp.json()["updated"], [])
        self.locked_attendance.refresh_from_db()
        self.assertNotEqual(self.locked_attendance.status, "Present")

    # ── requests against the locked period ────────────────────────────

    def test_a_correction_request_cannot_be_raised_for_a_locked_day(self):
        resp = self._employee_client().post(reverse("submit_correction_request"), {
            "attendance_id": self.locked_attendance.id,
            "new_in_time": "09:00", "new_out_time": "18:00", "reason": "fix",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(AttendanceCorrectionRequest.objects.exists())

    def test_a_correction_raised_before_finalizing_cannot_be_approved_after(self):
        """The realistic case: the request was pending when payroll closed."""
        req = AttendanceCorrectionRequest.objects.create(
            attendance=self.locked_attendance,
            old_in_time=time(10, 0), old_out_time=time(17, 0),
            new_in_time=time(9, 0), new_out_time=time(18, 0), reason="fix",
        )
        resp = self.admin.post(reverse("approve_correction", args=[req.id]))
        self.assertEqual(resp.status_code, 400)
        req.refresh_from_db()
        self.assertEqual(req.status, "Pending")

    def test_leave_overlapping_a_locked_period_cannot_be_approved(self):
        leave = LeaveApplication.objects.create(
            employee=self.employee, leave_type="CL",
            start_date=LOCKED_DAY, end_date=LOCKED_DAY, reason="x", status="Pending",
        )
        resp = self.admin.post(reverse("approve_leave", args=[leave.id]))
        self.assertEqual(resp.status_code, 400)
        leave.refresh_from_db()
        self.assertEqual(leave.status, "Pending")

    def test_compoff_overlapping_a_locked_period_cannot_be_approved(self):
        compoff = CompOffRequest.objects.create(
            employee=self.employee, from_date=LOCKED_DAY, to_date=LOCKED_DAY,
            count=1, reason="x", status="Pending",
        )
        resp = self.admin.post(reverse("approve_compoff", args=[compoff.id]))
        self.assertEqual(resp.status_code, 400)
        compoff.refresh_from_db()
        self.assertEqual(compoff.status, "Pending")

    # ── leave balance overrides ───────────────────────────────────────

    def test_lwp_cannot_be_overridden_for_a_locked_period(self):
        lb = LeaveBalance.objects.create(
            employee=self.employee, period_from_date=PERIOD_START, period_to_date=PERIOD_END,
            opening_balance=2, leave_taken=0, leave_without_pay=0,
            leave_balance=2, closing_balance=3, final_leave_balance=3,
        )
        resp = self.admin.post(reverse("override-lwp"), {"lb_id": lb.id, "lwp_value": "5"})
        self.assertEqual(resp.status_code, 400)
        lb.refresh_from_db()
        self.assertEqual(lb.leave_without_pay, 0)

    def test_compoff_cannot_be_overridden_for_a_locked_period(self):
        lb = LeaveBalance.objects.create(
            employee=self.employee, period_from_date=PERIOD_START, period_to_date=PERIOD_END,
            opening_balance=2, leave_taken=0, compoff=0,
            leave_balance=2, closing_balance=3, final_leave_balance=3,
        )
        resp = self.admin.post(reverse("override-compoff"), {"lb_id": lb.id, "compoff_value": "5"})
        self.assertEqual(resp.status_code, 400)
        lb.refresh_from_db()
        self.assertEqual(lb.compoff, 0)


class PayrollFreezeBulkRecalculationTest(TestCase):
    """The bulk "recalculate everything" actions.

    These are the most dangerous paths, because they rewrite history in one
    click rather than a record at a time -- and both were unguarded until
    this file went looking.
    """

    def setUp(self):
        self.company = Company.objects.create(
            short_name="GAP", name="Gap Co", phone="1", email="gap@test.com", address="Addr",
        )
        PayrollSettings.objects.create(company=self.company)
        self.employee = Employee.objects.create(
            company=self.company, salutation="Mr", first_name="Gap", last_name="Employee",
            father_name="Father", gender="Male", date_of_birth=date(1990, 1, 1),
            personal_email="gap@test.com", personal_mobile="1234567890",
            employee_code="GAP001", designation="Dev", department="IT",
            date_of_joining=date(2020, 1, 1), status="Active",
        )
        self.attendance = Attendance.objects.create(
            employee=self.employee, date=LOCKED_DAY, in_time=time(10, 0), out_time=time(17, 0),
        )
        PayrollRun.objects.create(
            company=self.company, month=PERIOD_START,
            start_date=PERIOD_START, end_date=PERIOD_END,
            status=PayrollRun.STATUS_FINALIZED,
        )

        self.admin_user = User.objects.create_user(username="gap_admin", password="pass12345")
        self.admin_user.groups.add(Group.objects.get(name="Super Admin"))
        self.admin = Client()
        self.admin.force_login(self.admin_user, backend="django.contrib.auth.backends.ModelBackend")

    def test_recalculating_attendance_skips_a_locked_day(self):
        """"Recalculate Attendance" re-saves every matching row and
        Attendance.save() recomputes status/count, so a locked day has to be
        excluded from the queryset entirely -- otherwise a rules change
        would move the numbers behind an issued payslip."""
        init = self.admin.post(reverse("recalculate_attendance_init"))
        self.assertEqual(init.status_code, 200)
        self.assertEqual(init.json()["total"], 0)

        resp = self.admin.post(reverse("recalculate_attendance_chunk"), {"offset": 0})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["processed_in_chunk"], 0)

    def test_recalculating_attendance_still_covers_open_days(self):
        open_row = Attendance.objects.create(
            employee=self.employee, date=OPEN_DAY, in_time=time(10, 0), out_time=time(17, 0),
        )
        init = self.admin.post(reverse("recalculate_attendance_init"))
        self.assertEqual(init.json()["total"], 1)
        resp = self.admin.post(reverse("recalculate_attendance_chunk"), {"offset": 0})
        self.assertEqual(resp.json()["processed_in_chunk"], 1)
        self.assertTrue(Attendance.objects.filter(pk=open_row.pk).exists())

    def test_uploading_attendance_skips_a_locked_day(self):
        """Re-uploading a month that has already been paid must not rewrite
        the rows the payslips were calculated from. The upload reports the
        row as skipped with a reason rather than failing the whole file."""
        import io as _io
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Emp Code", "Att.Date", "In Time", "Out Time"])
        ws.append(["GAP001", LOCKED_DAY.strftime("%Y-%m-%d"), "09:00", "18:00"])
        buf = _io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "attendance.xlsx"

        resp = self.admin.post(reverse("upload_attendance_init"), {"attendance_file": buf})
        self.assertEqual(resp.status_code, 200)
        upload_id = resp.json()["upload_id"]
        chunk = self.admin.post(reverse("upload_attendance_chunk", args=[upload_id]))

        data = chunk.json()
        self.assertEqual(data["updated"], 0)
        self.assertEqual(data["skipped"], 1)
        self.assertIn("finalized payroll run", " ".join(data["errors"]))

        self.attendance.refresh_from_db()
        self.assertEqual(self.attendance.in_time, time(10, 0))  # untouched

    def test_recalculating_leave_balances_skips_a_locked_period(self):
        """The leave balance a finalized payslip was computed from must
        survive a recalculation run."""
        lb = LeaveBalance.objects.create(
            employee=self.employee, period_from_date=PERIOD_START, period_to_date=PERIOD_END,
            opening_balance=Decimal("99.00"), leave_taken=Decimal("99.00"),
            leave_balance=Decimal("99.00"), closing_balance=Decimal("99.00"),
            final_leave_balance=Decimal("99.00"),
        )
        resp = self.admin.post(reverse("recalculate_leave_balances"), {"company_id": self.company.id})
        self.assertEqual(resp.status_code, 200)

        lb.refresh_from_db()
        # The deliberately-bogus 99s survive: the period is finalized, so
        # recalculation left it alone.
        self.assertEqual(lb.leave_taken, Decimal("99.00"))

    def test_a_finalized_run_cannot_be_reopened_through_the_app(self):
        """There is no un-finalize endpoint: the freeze is permanent unless
        someone edits the database directly."""
        from django.urls import get_resolver

        names = set()
        for pattern in get_resolver().url_patterns:
            names.add(getattr(pattern, "name", None))
        for suspect in ("payroll-run-reopen", "payroll-run-unfinalize", "payroll-run-delete"):
            self.assertNotIn(suspect, names)
