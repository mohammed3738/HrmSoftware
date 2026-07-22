"""
Regression test for the chunked attendance upload flow (init + repeated
chunk calls), which replaced the old single-request upload that failed on
files with 2000+ rows.
Run with: python manage.py test website.tests.test_attendance_upload_chunked
"""
import io
from datetime import date, timedelta

import openpyxl
from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from website.models import Company, Employee, Attendance, AttendanceUpload


class ChunkedAttendanceUploadTest(TestCase):
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
        # The project's custom auth backend (EmployeeStatusBackend) requires an
        # Employee record; pin ModelBackend explicitly since this test user has none.
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def _build_excel(self, n_rows):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Emp Code", "Att.Date", "In Time", "Out Time"])
        start = date(2020, 2, 1)
        for i in range(n_rows):
            d = start + timedelta(days=i)
            ws.append(["EMP001", d.strftime("%Y-%m-%d"), "09:00", "18:00"])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf

    def test_chunked_upload_processes_all_rows(self):
        n_rows = 2500
        excel_file = self._build_excel(n_rows)
        excel_file.name = "attendance.xlsx"

        resp = self.client.post(reverse("upload_attendance_init"), {"attendance_file": excel_file})
        data = resp.json()
        self.assertTrue(data["success"], data)
        self.assertEqual(data["total_rows"], n_rows)
        upload_id = data["upload_id"]
        chunk_size = data["chunk_size"]

        loops = 0
        last_processed = 0
        while True:
            loops += 1
            self.assertLess(loops, 100, "too many chunk iterations, something is wrong")
            resp = self.client.post(reverse("upload_attendance_chunk", args=[upload_id]))
            data = resp.json()
            self.assertTrue(data["success"], data)
            self.assertGreater(data["processed_rows"], last_processed)
            last_processed = data["processed_rows"]
            if data["done"]:
                break

        expected_chunks = -(-n_rows // chunk_size)  # ceil div
        self.assertEqual(loops, expected_chunks)
        self.assertEqual(data["created"], n_rows)
        self.assertEqual(data["skipped"], 0)
        self.assertEqual(data["processed_rows"], n_rows)
        self.assertEqual(Attendance.objects.count(), n_rows)

        upload = AttendanceUpload.objects.get(id=upload_id)
        self.assertEqual(upload.status, "completed")
        self.assertEqual(upload.created_count, n_rows)

    def test_chunk_call_after_completion_is_idempotent(self):
        """Calling chunk again after done=True should just return the final state, not reprocess."""
        excel_file = self._build_excel(5)
        excel_file.name = "attendance.xlsx"
        upload_id = self.client.post(
            reverse("upload_attendance_init"), {"attendance_file": excel_file}
        ).json()["upload_id"]

        resp = self.client.post(reverse("upload_attendance_chunk", args=[upload_id]))
        self.assertTrue(resp.json()["done"])

        resp2 = self.client.post(reverse("upload_attendance_chunk", args=[upload_id]))
        data2 = resp2.json()
        self.assertTrue(data2["done"])
        self.assertEqual(data2["created"], 5)
        self.assertEqual(Attendance.objects.count(), 5)
