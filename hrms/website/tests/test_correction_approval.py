"""
Regression tests for the attendance-correction approve flow.
Run with: python manage.py test website.tests.test_correction_approval
"""
from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from website.models import Company, Employee, Attendance, AttendanceCorrectionRequest, PayrollRun


class CorrectionApprovalTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Test Co")
        self.employee = Employee.objects.create(
            company=self.company,
            salutation="Mr", first_name="John", last_name="Doe",
            father_name="Robert Doe", gender="Male", blood_group="O+",
            date_of_birth=date(1990, 1, 1), place_of_birth="Test City",
            personal_email="john@test.com", present_address="123 Test St",
            permanent_address="123 Test St", personal_mobile="1234567890",
            employee_code="EMP001", designation="Developer", department="IT",
            date_of_joining=date(2020, 1, 1), location="Test Location",
            pan_no="ABCDE1234F", aadhar_no="123456789012",
            name_as_per_bank="John Doe", salary_account_number="1234567890",
            ifsc_code="TEST0001234", emergency_contact_name1="Jane Doe",
            emergency_contact_relation1="Spouse", emergency_contact_mobile1="0987654321",
            status="Active",
        )
        self.attendance = Attendance.objects.create(
            employee=self.employee, date=date(2026, 6, 1),
            in_time=time(10, 0), out_time=time(18, 0),
        )
        self.user = User.objects.create_superuser("admin", "admin@test.com", "pass12345")
        self.client = Client()
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def test_approve_updates_attendance_times(self):
        resp = self.client.post(reverse("submit_correction_request"), {
            "attendance_id": self.attendance.id,
            "new_in_time": "09:15",
            "new_out_time": "18:30",
            "reason": "Forgot to punch on time",
        })
        self.assertEqual(resp.status_code, 200)
        req = AttendanceCorrectionRequest.objects.latest("id")

        resp = self.client.post(reverse("approve_correction", args=[req.id]))
        self.assertEqual(resp.status_code, 200)

        self.attendance.refresh_from_db()
        self.assertEqual(self.attendance.in_time, time(9, 15))
        self.assertEqual(self.attendance.out_time, time(18, 30))

        req.refresh_from_db()
        self.assertEqual(req.status, "Approved")

    def test_approve_blocked_when_payroll_finalized_does_not_touch_attendance(self):
        """If the attendance date falls inside a finalized payroll run, the
        backend must reject the approval (HTTP 400, success=False) and must
        NOT change the Attendance row or the request's status. The live
        dashboard JS relies on the non-2xx status to distinguish this from a
        real approval instead of showing a false 'Approved!' message."""
        PayrollRun.objects.create(
            company=self.company, month=date(2026, 6, 1),
            start_date=date(2026, 6, 1), end_date=date(2026, 6, 30),
            status=PayrollRun.STATUS_FINALIZED,
        )
        req = AttendanceCorrectionRequest.objects.create(
            attendance=self.attendance, old_in_time=self.attendance.in_time,
            old_out_time=self.attendance.out_time, new_in_time=time(9, 15),
            new_out_time=time(18, 30), reason="test",
        )

        resp = self.client.post(reverse("approve_correction", args=[req.id]))
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data["success"])

        self.attendance.refresh_from_db()
        self.assertEqual(self.attendance.in_time, time(10, 0))
        self.assertEqual(self.attendance.out_time, time(18, 0))

        req.refresh_from_db()
        self.assertEqual(req.status, "Pending")
