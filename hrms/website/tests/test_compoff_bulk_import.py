"""
Regression tests for the bulk comp-off Excel import: creates Pending
CompOffRequest rows from a spreadsheet, and re-uploading a file that
overlaps a previous import must not raise duplicate requests for the same
employee and date range.

Run with: python manage.py test website.tests.test_compoff_bulk_import
"""
import io
from datetime import date

import openpyxl
from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse

from website.models import Company, Employee, CompOffRequest

HEADERS = ["Employee Code*", "From Date (YYYY-MM-DD)*", "To Date (YYYY-MM-DD)*", "Reason*"]


def _build_excel(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADERS)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


class CompoffBulkImportTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="cbi_admin", password="pass12345")
        self.admin.groups.add(Group.objects.get(name="Admin"))
        self.client = Client()
        self.client.login(username="cbi_admin", password="pass12345")

        self.company = Company.objects.create(
            short_name="CBI", name="Compoff Bulk Import Co", phone="1", email="cbi@test.com", address="Addr",
        )

    def make_employee(self, code):
        return Employee.objects.create(
            company=self.company, salutation="Mr", first_name="Comp", last_name=code,
            father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email=f"{code}@test.com", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890", employee_code=code,
            designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Comp",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
        )

    def post_upload(self, content):
        upload_file = io.BytesIO(content)
        upload_file.name = "compoff.xlsx"
        return self.client.post(reverse("import-compoff"), {"compoff_file": upload_file})

    def test_fresh_upload_creates_pending_requests(self):
        e1 = self.make_employee("CBI1")
        content = _build_excel([["CBI1", "2026-01-05", "2026-01-05", "Worked on Sunday"]])

        resp = self.post_upload(content)
        data = resp.json()
        self.assertTrue(data["success"], data)
        self.assertEqual(data["created"], 1)
        self.assertEqual(data["duplicates"], 0)

        req = CompOffRequest.objects.get(employee=e1)
        self.assertEqual(req.status, "Pending")
        self.assertEqual(req.count, 1)

    def test_reuploading_overlapping_rows_does_not_duplicate(self):
        """Re-uploading a file that includes a comp-off already raised for
        the same employee and date range must skip it as a duplicate, not
        raise a second request."""
        self.make_employee("CBI2")
        content = _build_excel([["CBI2", "2026-02-01", "2026-02-02", "Weekend work"]])

        self.post_upload(content)
        resp2 = self.post_upload(content)
        data2 = resp2.json()

        self.assertTrue(data2["success"], data2)
        self.assertEqual(data2["created"], 0)
        self.assertEqual(data2["duplicates"], 1)
        self.assertEqual(CompOffRequest.objects.filter(employee__employee_code="CBI2").count(), 1)

    def test_unknown_employee_code_is_reported_as_a_row_error(self):
        content = _build_excel([["NOSUCH", "2026-01-05", "2026-01-05", "Reason"]])
        resp = self.post_upload(content)
        data = resp.json()

        self.assertEqual(data["created"], 0)
        self.assertEqual(data["skipped"], 1)
        self.assertTrue(any("NOSUCH" in e["errors"][0] for e in data["errors"]))

    def test_to_date_before_from_date_is_rejected(self):
        self.make_employee("CBI3")
        content = _build_excel([["CBI3", "2026-01-10", "2026-01-05", "Reason"]])
        resp = self.post_upload(content)
        data = resp.json()

        self.assertEqual(data["created"], 0)
        self.assertEqual(data["skipped"], 1)
        self.assertFalse(CompOffRequest.objects.filter(employee__employee_code="CBI3").exists())

    def test_employee_without_create_permission_is_forbidden(self):
        employee_user = User.objects.create_user(username="cbi_emp", password="pass12345")
        employee_user.groups.add(Group.objects.get(name="Employee"))
        client = Client()
        client.login(username="cbi_emp", password="pass12345")

        content = _build_excel([["CBI4", "2026-01-05", "2026-01-05", "Reason"]])
        upload_file = io.BytesIO(content)
        upload_file.name = "compoff.xlsx"
        resp = client.post(reverse("import-compoff"), {"compoff_file": upload_file})
        self.assertEqual(resp.status_code, 403)
