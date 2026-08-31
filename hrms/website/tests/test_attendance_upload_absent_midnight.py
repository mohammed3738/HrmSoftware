"""
Regression test: an attendance Excel upload row with In Time = Out Time =
00:00 (this app's source files' convention for "no punch recorded", i.e.
the employee was absent) was being parsed as a literal midnight time
instead of "blank" -- datetime.time(0, 0) is truthy in Python, so
calculate_status()'s "no in/out time -> Absent" check never fired, and the
overnight-shift adjustment (out_time <= in_time -> add a day) turned it
into a ~24-hour shift, marking the employee Present instead of Absent.

Two-layer fix, both covered here: (1) _parse_excel_time now returns None
for midnight so NEW uploads never store 00:00/00:00 in the first place, and
(2) Attendance.calculate_status() itself now also treats an
already-stored in_time == out_time == midnight row as Absent -- this is
what actually fixes rows that were bulk-uploaded *before* the parser fix
shipped, since "Recalculate Attendance" just re-runs calculate_status() on
the DB's existing (already-bad) in_time/out_time, it doesn't re-parse Excel.

Run with: python manage.py test website.tests.test_attendance_upload_absent_midnight
"""
import io
from datetime import date, time
from decimal import Decimal

import openpyxl
from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from website.models import Attendance, Company, Employee
from website.views import _parse_excel_time


class ParseExcelTimeMidnightTest(TestCase):
    """Unit tests directly on the parsing helper -- covers every input
    shape the upload pipeline can hand it (string, Excel time-fraction
    float, datetime.time object)."""

    def test_string_00_00_is_treated_as_blank(self):
        self.assertIsNone(_parse_excel_time("00:00"))

    def test_string_00_00_00_is_treated_as_blank(self):
        self.assertIsNone(_parse_excel_time("00:00:00"))

    def test_excel_time_fraction_zero_is_treated_as_blank(self):
        self.assertIsNone(_parse_excel_time(0.0))

    def test_time_object_midnight_is_treated_as_blank(self):
        self.assertIsNone(_parse_excel_time(time(0, 0)))

    def test_genuinely_blank_cell_is_still_none(self):
        self.assertIsNone(_parse_excel_time(""))
        self.assertIsNone(_parse_excel_time(None))

    def test_real_time_is_unaffected(self):
        self.assertEqual(_parse_excel_time("09:15"), time(9, 15))
        self.assertEqual(_parse_excel_time("18:00:00"), time(18, 0, 0))


class AttendanceUploadAbsentMidnightTest(TestCase):
    """End-to-end: uploading a row with 00:00/00:00 must produce an Absent
    Attendance row, not a ~24-hour Present one."""

    def setUp(self):
        self.company = Company.objects.create(name="Test Co")
        self.employee = Employee.objects.create(
            company=self.company,
            salutation="Mr", first_name="Ann", last_name="Doe",
            father_name="Robert Doe", gender="Male", blood_group="O+",
            date_of_birth=date(1990, 1, 1), place_of_birth="Test City",
            personal_email="ann@test.com", present_address="123 Test St",
            permanent_address="123 Test St", personal_mobile="1234567890",
            employee_code="ABSENT1", designation="Developer", department="IT",
            date_of_joining=date(2020, 1, 1), location="Test Location",
            pan_no="ABCDE1234F", aadhar_no="123456789012",
            name_as_per_bank="Ann Doe", salary_account_number="1234567890",
            ifsc_code="TEST0001234", emergency_contact_name1="Jane Doe",
            emergency_contact_relation1="Spouse", emergency_contact_mobile1="0987654321",
            status="Active",
        )
        self.user = User.objects.create_superuser("admin2", "admin2@test.com", "pass12345")
        self.client = Client()
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def _build_excel(self, att_date, in_time, out_time):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Emp Code", "Att.Date", "In Time", "Out Time"])
        ws.append(["ABSENT1", att_date.strftime("%Y-%m-%d"), in_time, out_time])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf

    def test_00_00_in_and_out_time_is_marked_absent_not_present(self):
        # A Wednesday, so it won't get short-circuited by the weekend check.
        att_date = date(2026, 3, 4)
        excel_file = self._build_excel(att_date, "00:00", "00:00")
        excel_file.name = "attendance.xlsx"

        resp = self.client.post(reverse("upload_attendance_init"), {"attendance_file": excel_file})
        data = resp.json()
        self.assertTrue(data["success"], data)
        upload_id = data["upload_id"]

        chunk_resp = self.client.post(reverse("upload_attendance_chunk", args=[upload_id]))
        chunk_data = chunk_resp.json()
        self.assertTrue(chunk_data["success"], chunk_data)

        attendance = Attendance.objects.get(employee=self.employee, date=att_date)
        self.assertIsNone(attendance.in_time)
        self.assertIsNone(attendance.out_time)
        self.assertEqual(attendance.status, "Absent")
        self.assertNotEqual(attendance.status, "Present")

    def test_real_midnight_shift_start_with_a_real_checkout_still_works(self):
        """Only exact 00:00-for-both is the absence convention -- a real
        overnight shift (e.g. in at 23:50, out at 08:00 the next reporting
        slot) must still compute normally, not be swallowed by this fix."""
        att_date = date(2026, 3, 5)
        excel_file = self._build_excel(att_date, "23:50", "09:00")
        excel_file.name = "attendance.xlsx"

        resp = self.client.post(reverse("upload_attendance_init"), {"attendance_file": excel_file})
        upload_id = resp.json()["upload_id"]
        self.client.post(reverse("upload_attendance_chunk", args=[upload_id]))

        attendance = Attendance.objects.get(employee=self.employee, date=att_date)
        self.assertEqual(attendance.in_time, time(23, 50))
        self.assertEqual(attendance.out_time, time(9, 0))
        self.assertNotEqual(attendance.status, "Absent")


class RecalculateFixesAlreadyStoredMidnightRowsTest(TestCase):
    """The exact scenario reported live: rows bulk-uploaded *before* the
    parser fix already have in_time=out_time=time(0,0) sitting in the DB
    (the parser fix only prevents NEW bad rows, it can't rewrite old ones).
    "Recalculate Attendance" just calls .save() on existing rows -- it must
    now correctly flip these to Absent, without needing to re-upload."""

    def setUp(self):
        self.company = Company.objects.create(name="Recalc Test Co")
        self.employee = Employee.objects.create(
            company=self.company,
            salutation="Mr", first_name="Recalc", last_name="Doe",
            father_name="Robert Doe", gender="Male", blood_group="O+",
            date_of_birth=date(1990, 1, 1), place_of_birth="Test City",
            personal_email="recalc@test.com", present_address="123 Test St",
            permanent_address="123 Test St", personal_mobile="1234567890",
            employee_code="RECALC1", designation="Developer", department="IT",
            date_of_joining=date(2020, 1, 1), location="Test Location",
            pan_no="ABCDE1234F", aadhar_no="123456789012",
            name_as_per_bank="Recalc Doe", salary_account_number="1234567890",
            ifsc_code="TEST0001234", emergency_contact_name1="Jane Doe",
            emergency_contact_relation1="Spouse", emergency_contact_mobile1="0987654321",
            status="Active",
        )

    def test_saving_an_already_stored_midnight_midnight_row_recomputes_to_absent(self):
        att_date = date(2026, 4, 17)  # a Friday, so it's not a weekend
        attendance = Attendance.objects.create(
            employee=self.employee, date=att_date,
            in_time=time(0, 0, 0), out_time=time(0, 0, 0),
        )
        # Force it into the exact bad pre-fix state (status "Present", a
        # full day counted) via a raw queryset .update(), bypassing
        # save()/calculate_status() entirely -- this is what a row created
        # by the OLD buggy calculate_status() actually looked like in the
        # DB, which is what "Recalculate Attendance" has to fix.
        Attendance.objects.filter(pk=attendance.pk).update(status="Present", count=Decimal("1.00"))
        stored = Attendance.objects.get(pk=attendance.pk)
        self.assertEqual(stored.status, "Present")  # sanity check on the staged bad state

        # Recalculate: exactly what recalculate_attendance_chunk does.
        stored.save()

        stored.refresh_from_db()
        self.assertEqual(stored.status, "Absent")
        self.assertEqual(stored.count, Decimal("0.00"))
