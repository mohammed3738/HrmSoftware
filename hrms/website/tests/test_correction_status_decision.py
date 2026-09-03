"""
Regression tests for the approver's status decision on an attendance
correction request.

Two distinct kinds of request go through the same approval flow:

  1. A plain time fix ("my punch-out was recorded wrong"). The approver
     picks nothing; the day is recalculated from the corrected times, which
     is the behaviour that already existed.
  2. A judgement call ("I came in late for a medical reason") -- the
     employee submits the same times they already had and is really asking
     the approver to decide the day. Here the approver explicitly grants
     Present / Late Present / Half Day / Absent, which is stored as a manual
     override so a later bulk recalculation can't silently revert it.

Run with: python manage.py test website.tests.test_correction_status_decision
"""
from datetime import date, time
from decimal import Decimal

from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse

from website.models import (
    Attendance, AttendanceCorrectionRequest, Company, Employee, PayrollRun, PayrollSettings,
)

# 2026-06-01 is a Monday, so calculate_status() never short-circuits to
# "Weekend" and the punch times actually drive the status.
WORK_DAY = date(2026, 6, 1)


class CorrectionStatusDecisionTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="CSD", name="Correction Status Co", phone="1", email="csd@test.com", address="Addr",
        )
        PayrollSettings.objects.create(company=self.company)

        self.employee_user = User.objects.create_user(username="csd_emp", password="pass12345")
        self.employee_user.groups.add(Group.objects.get(name="Employee"))
        self.employee = Employee.objects.create(
            company=self.company, user=self.employee_user, salutation="Mr", first_name="Late", last_name="Comer",
            father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email="csd@test.com", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890", employee_code="CSD001",
            designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Late",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active", force_password_change=False,
        )

        # 10:00-17:00 = 7h worked against a 9h duty -> "Late Present".
        self.attendance = Attendance.objects.create(
            employee=self.employee, date=WORK_DAY, in_time=time(10, 0), out_time=time(17, 0),
        )
        self.assertEqual(self.attendance.status, "Late Present")

        self.manager = User.objects.create_user(username="csd_mgr", password="pass12345")
        self.manager.groups.add(Group.objects.get(name="Manager"))

    def _client_as(self, user):
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return client

    def _request(self, new_in=time(10, 0), new_out=time(17, 0)):
        """A correction request; defaults to the 'no time change, explain the
        day' kind the status dropdown exists for."""
        return AttendanceCorrectionRequest.objects.create(
            attendance=self.attendance,
            old_in_time=self.attendance.in_time, old_out_time=self.attendance.out_time,
            new_in_time=new_in, new_out_time=new_out,
            reason="Was late due to a medical issue",
        )

    # ── the request itself ────────────────────────────────────────────────

    def test_times_unchanged_flags_a_judgement_call_request(self):
        self.assertTrue(self._request().times_unchanged)

    def test_times_unchanged_is_false_for_a_real_time_fix(self):
        self.assertFalse(self._request(new_in=time(9, 0), new_out=time(18, 0)).times_unchanged)

    # ── auto (no decision) keeps the old behaviour ────────────────────────

    def test_auto_approval_recalculates_from_the_corrected_times(self):
        req = self._request(new_in=time(9, 0), new_out=time(18, 0))
        resp = self._client_as(self.manager).post(reverse("approve_correction", args=[req.id]))
        self.assertEqual(resp.status_code, 200)

        self.attendance.refresh_from_db()
        self.assertEqual(self.attendance.in_time, time(9, 0))
        self.assertEqual(self.attendance.status, "Present")  # 9h worked
        self.assertFalse(self.attendance.status_overridden)

        req.refresh_from_db()
        self.assertEqual(req.status, "Approved")
        self.assertIsNone(req.approved_status)

    def test_auto_approval_clears_an_earlier_manual_override(self):
        """A previous manual override would otherwise make calculate_status()
        return early, writing the corrected times but leaving the very status
        the correction was meant to fix untouched."""
        self.attendance.status_overridden = True
        self.attendance.status = "Absent"
        self.attendance.count = Decimal("0.00")
        self.attendance.save()

        req = self._request(new_in=time(9, 0), new_out=time(18, 0))
        self._client_as(self.manager).post(reverse("approve_correction", args=[req.id]))

        self.attendance.refresh_from_db()
        self.assertEqual(self.attendance.status, "Present")
        self.assertFalse(self.attendance.status_overridden)

    # ── explicit grants ───────────────────────────────────────────────────

    def test_approver_can_grant_a_full_day_without_any_time_change(self):
        req = self._request()
        resp = self._client_as(self.manager).post(reverse("approve_correction", args=[req.id]), {
            "status_decision": "Present",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "Present")

        self.attendance.refresh_from_db()
        self.assertEqual(self.attendance.status, "Present")
        self.assertEqual(self.attendance.count, Decimal("1.00"))
        self.assertTrue(self.attendance.status_overridden)
        # The punch times themselves are untouched -- the day was a judgement
        # call, not a mis-punch.
        self.assertEqual(self.attendance.in_time, time(10, 0))
        self.assertEqual(self.attendance.out_time, time(17, 0))

        req.refresh_from_db()
        self.assertEqual(req.approved_status, "Present")

    def test_approver_can_grant_half_day(self):
        req = self._request()
        self._client_as(self.manager).post(reverse("approve_correction", args=[req.id]), {
            "status_decision": "Half Day",
        })
        self.attendance.refresh_from_db()
        self.assertEqual(self.attendance.status, "Half Day")
        self.assertEqual(self.attendance.count, Decimal("0.50"))
        self.assertTrue(self.attendance.is_half_day)

    def test_approver_can_grant_absent(self):
        req = self._request()
        self._client_as(self.manager).post(reverse("approve_correction", args=[req.id]), {
            "status_decision": "Absent",
        })
        self.attendance.refresh_from_db()
        self.assertEqual(self.attendance.status, "Absent")
        self.assertEqual(self.attendance.count, Decimal("0.00"))

    def test_approver_can_grant_late_present(self):
        # Start from a full-day row so the grant is a real change.
        self.attendance.in_time = time(9, 0)
        self.attendance.out_time = time(18, 0)
        self.attendance.save()
        self.assertEqual(self.attendance.status, "Present")

        req = self._request(new_in=time(9, 0), new_out=time(18, 0))
        self._client_as(self.manager).post(reverse("approve_correction", args=[req.id]), {
            "status_decision": "Late Present",
        })
        self.attendance.refresh_from_db()
        self.assertEqual(self.attendance.status, "Late Present")
        self.assertEqual(self.attendance.count, Decimal("1.00"))

    def test_granted_status_survives_a_later_recalculation(self):
        req = self._request()
        self._client_as(self.manager).post(reverse("approve_correction", args=[req.id]), {
            "status_decision": "Present",
        })

        # What the "Recalculate Attendance" action does to every row.
        self.attendance.refresh_from_db()
        self.attendance.save()

        self.attendance.refresh_from_db()
        self.assertEqual(self.attendance.status, "Present")
        self.assertEqual(self.attendance.count, Decimal("1.00"))

    # ── guards ────────────────────────────────────────────────────────────

    def test_invalid_status_choice_is_rejected(self):
        req = self._request()
        resp = self._client_as(self.manager).post(reverse("approve_correction", args=[req.id]), {
            "status_decision": "Vacation",
        })
        self.assertEqual(resp.status_code, 400)

        self.attendance.refresh_from_db()
        self.assertEqual(self.attendance.status, "Late Present")
        req.refresh_from_db()
        self.assertEqual(req.status, "Pending")

    def test_employee_cannot_approve_their_own_correction(self):
        req = self._request()
        resp = self._client_as(self.employee_user).post(reverse("approve_correction", args=[req.id]), {
            "status_decision": "Present",
        })
        self.assertEqual(resp.status_code, 403)
        req.refresh_from_db()
        self.assertEqual(req.status, "Pending")

    def test_locked_payroll_blocks_a_granted_status_too(self):
        PayrollRun.objects.create(
            company=self.company, month=date(2026, 6, 1),
            start_date=date(2026, 6, 1), end_date=date(2026, 6, 30),
            status=PayrollRun.STATUS_FINALIZED,
        )
        req = self._request()
        resp = self._client_as(self.manager).post(reverse("approve_correction", args=[req.id]), {
            "status_decision": "Present",
        })
        self.assertEqual(resp.status_code, 400)

        self.attendance.refresh_from_db()
        self.assertEqual(self.attendance.status, "Late Present")
        self.assertFalse(self.attendance.status_overridden)
