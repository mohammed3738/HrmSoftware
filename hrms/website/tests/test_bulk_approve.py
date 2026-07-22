"""
Regression tests for bulk-approving Leave / Comp-Off / Attendance-Correction
requests (select multiple, or all, and approve in one action).
Run with: python manage.py test website.tests.test_bulk_approve
"""
import json
from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from website.models import (
    Company, Employee, Attendance, AttendanceCorrectionRequest,
    LeaveApplication, CompOffRequest, PayrollRun,
)


class BulkApproveTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Test Co")

        def make_employee(code):
            return Employee.objects.create(
                company=self.company,
                salutation="Mr", first_name=f"Emp{code}", last_name="Doe",
                father_name="Robert Doe", gender="Male", blood_group="O+",
                date_of_birth=date(1990, 1, 1), place_of_birth="Test City",
                personal_email=f"{code}@test.com", present_address="123 Test St",
                permanent_address="123 Test St", personal_mobile="1234567890",
                employee_code=code, designation="Developer", department="IT",
                date_of_joining=date(2020, 1, 1), location="Test Location",
                pan_no="ABCDE1234F", aadhar_no="123456789012",
                name_as_per_bank="John Doe", salary_account_number="1234567890",
                ifsc_code="TEST0001234", emergency_contact_name1="Jane Doe",
                emergency_contact_relation1="Spouse", emergency_contact_mobile1="0987654321",
                status="Active",
            )

        self.emp1 = make_employee("EMP001")
        self.emp2 = make_employee("EMP002")
        self.emp3 = make_employee("EMP003")

        self.user = User.objects.create_superuser("admin", "admin@test.com", "pass12345")
        self.client = Client()
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def _post_json(self, url, payload):
        return self.client.post(url, data=json.dumps(payload), content_type="application/json")

    def test_bulk_approve_leave_all_succeed(self):
        leaves = [
            LeaveApplication.objects.create(
                employee=e, leave_type="CL", start_date=date(2026, 8, 1),
                end_date=date(2026, 8, 2), reason="test",
            )
            for e in (self.emp1, self.emp2, self.emp3)
        ]
        resp = self._post_json(reverse("bulk_approve_leave"), {"ids": [l.id for l in leaves]})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(sorted(data["approved"]), sorted(l.id for l in leaves))
        self.assertEqual(data["failed"], [])
        for l in leaves:
            l.refresh_from_db()
            self.assertEqual(l.status, "Approved")

    def test_bulk_approve_compoff_all_succeed(self):
        compoffs = [
            CompOffRequest.objects.create(
                employee=e, from_date=date(2026, 8, 5), to_date=date(2026, 8, 5), reason="test",
            )
            for e in (self.emp1, self.emp2)
        ]
        resp = self._post_json(reverse("bulk_approve_compoff"), {"ids": [c.id for c in compoffs]})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(sorted(data["approved"]), sorted(c.id for c in compoffs))
        self.assertEqual(data["failed"], [])
        for c in compoffs:
            c.refresh_from_db()
            self.assertEqual(c.status, "Approved")

    def test_bulk_approve_correction_updates_attendance_times(self):
        attendances = [
            Attendance.objects.create(employee=e, date=date(2026, 8, 10), in_time=time(10, 0), out_time=time(18, 0))
            for e in (self.emp1, self.emp2, self.emp3)
        ]
        corrections = [
            AttendanceCorrectionRequest.objects.create(
                attendance=a, old_in_time=a.in_time, old_out_time=a.out_time,
                new_in_time=time(9, 0), new_out_time=time(18, 30), reason="test",
            )
            for a in attendances
        ]
        resp = self._post_json(reverse("bulk_approve_correction"), {"ids": [c.id for c in corrections]})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["approved"]), 3)
        self.assertEqual(data["failed"], [])
        for a in attendances:
            a.refresh_from_db()
            self.assertEqual(a.in_time, time(9, 0))
            self.assertEqual(a.out_time, time(18, 30))
        for c in corrections:
            c.refresh_from_db()
            self.assertEqual(c.status, "Approved")

    def test_bulk_approve_partial_failure_does_not_block_others(self):
        """One request is inside a finalized payroll period (should fail);
        the rest should still succeed, and each outcome should be reported."""
        PayrollRun.objects.create(
            company=self.company, month=date(2026, 8, 1),
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 31),
            status=PayrollRun.STATUS_FINALIZED,
        )
        blocked = LeaveApplication.objects.create(
            employee=self.emp1, leave_type="CL", start_date=date(2026, 8, 5),
            end_date=date(2026, 8, 6), reason="in locked period",
        )
        allowed = LeaveApplication.objects.create(
            employee=self.emp2, leave_type="CL", start_date=date(2026, 9, 5),
            end_date=date(2026, 9, 6), reason="not locked",
        )

        resp = self._post_json(reverse("bulk_approve_leave"), {"ids": [blocked.id, allowed.id]})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["approved"], [allowed.id])
        self.assertEqual(len(data["failed"]), 1)
        self.assertEqual(data["failed"][0]["id"], blocked.id)

        blocked.refresh_from_db()
        allowed.refresh_from_db()
        self.assertEqual(blocked.status, "Pending")
        self.assertEqual(allowed.status, "Approved")

    def test_bulk_approve_requires_manager_group(self):
        """A plain employee (no Admin/HR/Manager group, not superuser) must not be able to bulk-approve."""
        plain_user = User.objects.create_user("plain", "plain@test.com", "pass12345")
        client = Client()
        client.force_login(plain_user, backend="django.contrib.auth.backends.ModelBackend")

        leave = LeaveApplication.objects.create(
            employee=self.emp1, leave_type="CL", start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 2), reason="test",
        )
        resp = client.post(
            reverse("bulk_approve_leave"),
            data=json.dumps({"ids": [leave.id]}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)
        leave.refresh_from_db()
        self.assertEqual(leave.status, "Pending")
