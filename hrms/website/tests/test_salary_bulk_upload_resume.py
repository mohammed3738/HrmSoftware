"""
Regression tests for the resumable salary-structure bulk upload:
re-uploading the exact same file after a dropped connection ("the pipe
broke") must resume from where it left off, not duplicate SalaryMaster
history rows for employees already processed by an earlier attempt.

Run with: python manage.py test website.tests.test_salary_bulk_upload_resume
"""
import hashlib
import io
from datetime import date

import openpyxl
from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse

from website.models import Company, Employee, SalaryMaster, SalaryUpload

HEADERS = [
    "Employee Code*", "Gross CTC Monthly*", "Basic Monthly*", "HRA Monthly*",
    "Stat Bonus Monthly", "Allowance 1 Monthly", "Allowance 2 Monthly",
    "Special Allowance Monthly", "Guaranteed Cash Monthly",
    "PF Employer Monthly", "PF Employee Monthly",
    "ESIC Employer Monthly", "ESIC Employee Monthly",
    "Gratuity Monthly", "Profession Tax Monthly",
    "CTC Monthly", "Net Salary Monthly*",
    "Include PF (yes/no)", "Include ESIC (yes/no)", "Include Gratuity (yes/no)",
    "Effective Date (YYYY-MM-DD)",
]


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


def _row(emp_code, gross_ctc="50000"):
    return [
        emp_code, gross_ctc, "25000", "12500", "", "", "", "", "",
        "", "", "", "", "", "", "", "45000",
        "yes", "no", "no", "2026-01-01",
    ]


class SalaryBulkUploadResumeTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="sbu_admin", password="pass12345")
        self.admin.groups.add(Group.objects.get(name="Admin"))
        self.client = Client()
        self.client.login(username="sbu_admin", password="pass12345")

        self.company = Company.objects.create(
            short_name="SBU", name="Salary Bulk Upload Co", phone="1", email="sbu@test.com", address="Addr",
        )

    def make_employee(self, code):
        return Employee.objects.create(
            company=self.company, salutation="Mr", first_name="Sal", last_name=code,
            father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email=f"{code}@test.com", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890", employee_code=code,
            designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Sal",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
        )

    def post_upload(self, content):
        upload_file = io.BytesIO(content)
        upload_file.name = "salary.xlsx"
        return self.client.post(reverse("import-salary"), {"salary_file": upload_file})

    def test_fresh_upload_creates_records(self):
        e1, e2 = self.make_employee("SBU1"), self.make_employee("SBU2")
        content = _build_excel([_row("SBU1"), _row("SBU2")])

        resp = self.post_upload(content)
        data = resp.json()
        self.assertTrue(data["success"], data)
        self.assertEqual(data["created"], 2)
        self.assertFalse(data["resumed"])
        self.assertTrue(SalaryMaster.objects.filter(employee=e1, is_active=True).exists())
        self.assertTrue(SalaryMaster.objects.filter(employee=e2, is_active=True).exists())

        upload = SalaryUpload.objects.get(file_hash=hashlib.sha256(content).hexdigest())
        self.assertEqual(set(upload.processed_employee_codes), {"SBU1", "SBU2"})
        self.assertEqual(upload.status, "completed")

    def test_resuming_after_a_dropped_connection_does_not_duplicate(self):
        """The core scenario: simulate a prior attempt that successfully
        applied SBU1 but died before reaching SBU2 (as if the connection
        dropped mid-loop). Re-uploading the identical bytes must apply only
        SBU2, and SBU1 must not gain a second SalaryMaster row."""
        e1, e2 = self.make_employee("SBU3"), self.make_employee("SBU4")
        content = _build_excel([_row("SBU3"), _row("SBU4")])
        file_hash = hashlib.sha256(content).hexdigest()

        # Simulate the partial prior attempt: SBU3 already has an active
        # SalaryMaster and is recorded as processed; SBU4 never ran.
        SalaryMaster.objects.create(employee=e1, is_active=True, gross_ctc_pm="50000")
        SalaryUpload.objects.create(
            file_hash=file_hash, file_name="salary.xlsx",
            processed_employee_codes=["SBU3"], created_count=1, status="processing",
        )

        resp = self.post_upload(content)
        data = resp.json()
        self.assertTrue(data["success"], data)
        self.assertTrue(data["resumed"])
        self.assertEqual(data["already_done"], 1)
        self.assertEqual(data["created"], 1)  # only SBU4 newly applied

        # SBU3 must still have exactly ONE SalaryMaster row -- the resume
        # must not have deactivated-and-reinserted it.
        self.assertEqual(SalaryMaster.objects.filter(employee=e1).count(), 1)
        self.assertTrue(SalaryMaster.objects.filter(employee=e1, is_active=True).exists())
        self.assertTrue(SalaryMaster.objects.filter(employee=e2, is_active=True).exists())

        upload = SalaryUpload.objects.get(file_hash=file_hash)
        self.assertEqual(set(upload.processed_employee_codes), {"SBU3", "SBU4"})

    def test_reuploading_a_fully_completed_file_creates_nothing_new(self):
        self.make_employee("SBU5")
        content = _build_excel([_row("SBU5")])

        resp1 = self.post_upload(content)
        self.assertEqual(resp1.json()["created"], 1)

        resp2 = self.post_upload(content)
        data2 = resp2.json()
        self.assertTrue(data2["resumed"])
        self.assertEqual(data2["created"], 0)
        self.assertEqual(data2["already_done"], 1)
        self.assertEqual(SalaryMaster.objects.filter(employee__employee_code="SBU5").count(), 1)

    def test_errored_row_is_retried_on_next_identical_upload_once_fixed(self):
        # SBU6 doesn't exist yet -- this row will error on the first attempt.
        content = _build_excel([_row("SBU6")])

        resp1 = self.post_upload(content)
        data1 = resp1.json()
        self.assertEqual(data1["created"], 0)
        self.assertEqual(data1["skipped"], 1)
        self.assertTrue(any("SBU6" in e["errors"][0] for e in data1["errors"]))

        # Fix the underlying problem, then re-upload the exact same bytes.
        self.make_employee("SBU6")
        resp2 = self.post_upload(content)
        data2 = resp2.json()
        self.assertTrue(data2["resumed"])
        self.assertEqual(data2["created"], 1)
        self.assertEqual(data2["skipped"], 0)
        self.assertTrue(SalaryMaster.objects.filter(employee__employee_code="SBU6", is_active=True).exists())

    def test_modified_file_is_treated_as_a_fresh_upload_not_resumed(self):
        self.make_employee("SBU7")
        content_a = _build_excel([_row("SBU7", gross_ctc="50000")])
        content_b = _build_excel([_row("SBU7", gross_ctc="60000")])  # one changed cell

        self.post_upload(content_a)
        resp = self.post_upload(content_b)
        data = resp.json()
        self.assertFalse(data["resumed"])
        self.assertEqual(data["created"], 1)
        self.assertEqual(SalaryUpload.objects.count(), 2)
