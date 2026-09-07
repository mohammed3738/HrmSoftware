"""
Regression tests for raising an attendance correction as a Minutes of
Meeting: an optional mode where the employee records when a call ran and
attaches the minutes, instead of (or alongside) correcting punch times.
Leaving the MoM box unticked must keep the ordinary request behaviour
untouched.

Run with: python manage.py test website.tests.test_correction_mom
"""
from datetime import date, time

from django.contrib.auth.models import User, Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse

from website.models import (
    Attendance, AttendanceCorrectionRequest, Company, Employee, PayrollSettings,
)

WORK_DAY = date(2026, 6, 1)  # a Monday


def make_employee(company, code, user=None):
    return Employee.objects.create(
        company=company, user=user, salutation="Mr", first_name="Mom", last_name="Tester",
        father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
        place_of_birth="City", personal_email=f"{code}@test.com", present_address="Addr",
        permanent_address="Addr", personal_mobile="1234567890", employee_code=code,
        designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), location="City",
        pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Mom",
        salary_account_number="1234567890", ifsc_code="TEST0001234",
        emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
        emergency_contact_mobile1="0987654321", status="Active", force_password_change=False,
    )


class CorrectionMomTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="MOM", name="MoM Co", phone="1", email="mom@test.com", address="Addr",
        )
        PayrollSettings.objects.create(company=self.company)

        self.user = User.objects.create_user(username="mom_emp", password="pass12345")
        self.user.groups.add(Group.objects.get(name="Employee"))
        self.employee = make_employee(self.company, "MOM001", user=self.user)

        self.attendance = Attendance.objects.create(
            employee=self.employee, date=WORK_DAY, in_time=time(10, 0), out_time=time(17, 0),
        )

        self.client = Client()
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def _submit(self, **extra):
        payload = {
            "attendance_id": self.attendance.id,
            "new_in_time": "10:00",
            "new_out_time": "17:00",
            "reason": "Was on a client call",
        }
        payload.update(extra)
        return self.client.post(reverse("submit_correction_request"), payload)

    # ── unticked: nothing about the ordinary request changes ──────────

    def test_plain_request_is_not_a_mom(self):
        resp = self._submit()
        self.assertEqual(resp.status_code, 200)
        req = AttendanceCorrectionRequest.objects.latest("id")
        self.assertFalse(req.is_mom)
        self.assertIsNone(req.meeting_in_time)
        self.assertIsNone(req.meeting_out_time)
        self.assertFalse(bool(req.mom_attachment))

    def test_meeting_fields_are_ignored_when_the_box_is_unticked(self):
        """The fields are only disabled client-side, so values can still
        arrive; without the box ticked they must not be stored."""
        resp = self._submit(meeting_in_time="11:00", meeting_out_time="12:00")
        self.assertEqual(resp.status_code, 200)
        req = AttendanceCorrectionRequest.objects.latest("id")
        self.assertFalse(req.is_mom)
        self.assertIsNone(req.meeting_in_time)
        self.assertIsNone(req.meeting_out_time)

    # ── ticked: MoM details are captured ──────────────────────────────

    def test_mom_request_stores_call_timings(self):
        resp = self._submit(is_mom="on", meeting_in_time="11:00", meeting_out_time="12:30")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["is_mom"])

        req = AttendanceCorrectionRequest.objects.latest("id")
        self.assertTrue(req.is_mom)
        self.assertEqual(req.meeting_in_time, time(11, 0))
        self.assertEqual(req.meeting_out_time, time(12, 30))
        self.assertEqual(req.meeting_duration_display, "1h 30m")

    def test_mom_request_stores_the_attachment(self):
        minutes = SimpleUploadedFile("minutes.txt", b"Discussed Q3 targets.", content_type="text/plain")
        resp = self._submit(
            is_mom="on", meeting_in_time="11:00", meeting_out_time="12:00", mom_attachment=minutes,
        )
        self.assertEqual(resp.status_code, 200)

        req = AttendanceCorrectionRequest.objects.latest("id")
        self.assertTrue(bool(req.mom_attachment))
        self.assertIn("minutes", req.mom_attachment.name)
        req.mom_attachment.delete(save=False)  # don't leave the file behind

    def test_attachment_is_optional_for_a_mom(self):
        resp = self._submit(is_mom="on", meeting_in_time="09:30", meeting_out_time="10:00")
        self.assertEqual(resp.status_code, 200)
        req = AttendanceCorrectionRequest.objects.latest("id")
        self.assertTrue(req.is_mom)
        self.assertFalse(bool(req.mom_attachment))

    def test_meeting_timings_are_required_once_mom_is_ticked(self):
        resp = self._submit(is_mom="on", meeting_in_time="11:00")  # no out-call time
        self.assertEqual(resp.status_code, 400)
        self.assertIn("required", resp.json()["error"].lower())
        self.assertFalse(AttendanceCorrectionRequest.objects.exists())

    def test_a_call_running_past_midnight_still_reports_a_sane_duration(self):
        resp = self._submit(is_mom="on", meeting_in_time="23:30", meeting_out_time="00:30")
        self.assertEqual(resp.status_code, 200)
        req = AttendanceCorrectionRequest.objects.latest("id")
        self.assertEqual(req.meeting_duration_display, "1h 0m")

    def test_duration_is_blank_for_a_non_mom_request(self):
        self._submit()
        req = AttendanceCorrectionRequest.objects.latest("id")
        self.assertEqual(req.meeting_duration_display, "")

    # ── a MoM still approves like any other correction ────────────────

    def test_a_mom_request_can_be_approved_with_a_status_decision(self):
        self._submit(is_mom="on", meeting_in_time="11:00", meeting_out_time="12:00")
        req = AttendanceCorrectionRequest.objects.latest("id")

        hr_user = User.objects.create_user(username="mom_hr", password="pass12345")
        hr_user.groups.add(Group.objects.get(name="Admin"))
        hr_client = Client()
        hr_client.force_login(hr_user, backend="django.contrib.auth.backends.ModelBackend")

        resp = hr_client.post(reverse("approve_correction", args=[req.id]), {"status_decision": "Present"})
        self.assertEqual(resp.status_code, 200)

        req.refresh_from_db()
        self.assertEqual(req.status, "Approved")
        self.assertEqual(req.approved_status, "Present")
        self.assertTrue(req.is_mom)  # the MoM details survive approval

    def test_detail_api_exposes_the_mom_details_to_the_approver(self):
        self._submit(is_mom="on", meeting_in_time="11:00", meeting_out_time="12:00")
        req = AttendanceCorrectionRequest.objects.latest("id")

        hr_user = User.objects.create_user(username="mom_hr2", password="pass12345")
        hr_user.groups.add(Group.objects.get(name="Admin"))
        hr_client = Client()
        hr_client.force_login(hr_user, backend="django.contrib.auth.backends.ModelBackend")

        resp = hr_client.get(reverse("attendance_correction_detail", args=[req.id]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["is_mom"])
        self.assertEqual(data["meeting_in_time"], "11:00:00")
        self.assertEqual(data["meeting_duration"], "1h 0m")

    # ── ownership ─────────────────────────────────────────────────────

    def test_cannot_raise_a_request_against_someone_elses_attendance(self):
        other = make_employee(self.company, "MOM002")
        other_attendance = Attendance.objects.create(
            employee=other, date=WORK_DAY, in_time=time(10, 0), out_time=time(17, 0),
        )
        resp = self.client.post(reverse("submit_correction_request"), {
            "attendance_id": other_attendance.id,
            "new_in_time": "09:00", "new_out_time": "18:00", "reason": "not mine",
        })
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(AttendanceCorrectionRequest.objects.exists())
