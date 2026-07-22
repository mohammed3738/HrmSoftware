"""
Regression tests for the "Recalculate Attendance" feature: re-running
Attendance.calculate_status() on already-saved rows (via the normal
.save() path) without deleting and re-uploading the source Excel file.
Run with: python manage.py test website.tests.test_recalculate_attendance
"""
from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from website.models import Company, Employee, Attendance, PayrollSettings


class RecalculateAttendanceTest(TestCase):
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
        self.user = User.objects.create_superuser("admin", "admin@test.com", "pass12345")
        self.client = Client()
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def test_recalculate_updates_status_after_settings_change(self):
        # Create attendance rows while grace period is 0 (strict) — a 10-min
        # shortfall of the 9h duty will be "Late Present".
        PayrollSettings.objects.create(company=self.company, grace_period_minutes=0)
        rows = [
            Attendance.objects.create(
                employee=self.employee, date=date(2026, 8, 3).replace(day=d),  # Mon-Wed
                in_time=time(9, 0), out_time=time(17, 50),  # 8h50m, 10 min short of 9h
            )
            for d in (3, 4, 5)
        ]
        for r in rows:
            r.refresh_from_db()
            self.assertEqual(r.status, "Late Present")

        # Now loosen the grace period to 15 minutes — existing rows are stale
        # until recalculated.
        ps = PayrollSettings.objects.get(company=self.company)
        ps.grace_period_minutes = 15
        ps.save()
        for r in rows:
            r.refresh_from_db()
            self.assertEqual(r.status, "Late Present")  # still stale

        resp = self.client.post(reverse("recalculate_attendance_init"))
        data = resp.json()
        self.assertTrue(data["success"], data)
        self.assertEqual(data["total"], 3)

        offset = 0
        loops = 0
        while True:
            loops += 1
            self.assertLess(loops, 20)
            resp = self.client.post(reverse("recalculate_attendance_chunk"), {"offset": offset})
            chunk_data = resp.json()
            self.assertTrue(chunk_data["success"], chunk_data)
            if chunk_data["processed_in_chunk"] == 0:
                break
            offset += chunk_data["processed_in_chunk"]

        self.assertEqual(offset, 3)
        for r in rows:
            r.refresh_from_db()
            self.assertEqual(r.status, "Present")  # now correctly recalculated
            self.assertEqual(r.late, 0)

    def test_recalculate_respects_date_range_filter(self):
        PayrollSettings.objects.create(company=self.company, grace_period_minutes=15)
        in_range = Attendance.objects.create(
            employee=self.employee, date=date(2026, 8, 5), in_time=time(9, 0), out_time=time(17, 50),
        )
        out_of_range = Attendance.objects.create(
            employee=self.employee, date=date(2026, 9, 5), in_time=time(9, 0), out_time=time(17, 50),
        )

        resp = self.client.post(reverse("recalculate_attendance_init"), {
            "date_from": "2026-08-01", "date_to": "2026-08-31",
        })
        self.assertEqual(resp.json()["total"], 1)

        resp = self.client.post(reverse("recalculate_attendance_chunk"), {
            "offset": 0, "date_from": "2026-08-01", "date_to": "2026-08-31",
        })
        self.assertEqual(resp.json()["processed_in_chunk"], 1)

        in_range.refresh_from_db()
        out_of_range.refresh_from_db()
        self.assertIsNotNone(in_range.status)
        self.assertNotEqual(out_of_range.status, "")  # unaffected but still has its own prior status

    def test_recalculate_requires_admin_or_hr_group(self):
        plain_user = User.objects.create_user("plain", "plain@test.com", "pass12345")
        client = Client()
        client.force_login(plain_user, backend="django.contrib.auth.backends.ModelBackend")
        resp = client.post(reverse("recalculate_attendance_init"))
        self.assertEqual(resp.status_code, 403)
