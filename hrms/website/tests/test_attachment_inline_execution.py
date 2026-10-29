"""
Regression tests for serving employee documents inline.

No upload field on EmployeeAttachment / PreviousEmploymentAttachment
validates extension, MIME type or size (only Employee.photo and
Company.logo do, in forms.py). _serve_employee_file used

    as_attachment=bool(request.GET.get("download"))

so without ?download=1 the file rendered **inline**, from this
application's own origin, with Content-Type guessed from its name. An
attachment uploaded as .html or .svg therefore executed script with the
viewing user's session -- and the templates link to these files with
target="_blank" and no ?download, so inline is the normal path.

The fix forces a download for the extensions a browser will execute, and
sets X-Content-Type-Options: nosniff so a mislabelled file is not sniffed
into one. PDFs and images must still preview inline, because that is what
the "view file" links are for.

Run with:
    python manage.py test website.tests.test_attachment_inline_execution
"""
from datetime import date

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from website.models import Company, Employee, EmployeeAttachment


class AttachmentInlineExecutionTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="AIE", name="Attachment Co", phone="1",
            email="aie@test.com", address="Addr",
        )
        self.employee = Employee.objects.create(
            company=self.company, salutation="Mr", first_name="Att", last_name="Doe",
            father_name="Father", gender="Male", blood_group="O+",
            date_of_birth=date(1990, 1, 1), place_of_birth="City",
            personal_email="aie001@test.com", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890",
            employee_code="AIE001", designation="Dev", department="IT",
            date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Att",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
            force_password_change=False,
        )
        self.hr_user = User.objects.create_user(username="aie_hr", password="pass12345")
        self.hr_user.groups.add(Group.objects.get(name="HR"))
        self.client_hr = Client()
        self.client_hr.force_login(
            self.hr_user, backend="django.contrib.auth.backends.ModelBackend",
        )

    def _attachment(self, name, content, content_type):
        return EmployeeAttachment.objects.create(
            employee=self.employee, file_name="other", other_file_name=name,
            file=SimpleUploadedFile(name, content, content_type=content_type),
        )

    def _fetch(self, attachment):
        return self.client_hr.get(
            reverse("download_attachment", args=[attachment.pk]),
        )

    def test_html_attachment_is_forced_to_download(self):
        attachment = self._attachment(
            "notes.html", b"<script>document.title='x'</script>", "text/html",
        )
        resp = self._fetch(attachment)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("attachment", resp["Content-Disposition"])

    def test_svg_attachment_is_forced_to_download(self):
        attachment = self._attachment(
            "logo.svg",
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>1</script></svg>',
            "image/svg+xml",
        )
        resp = self._fetch(attachment)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("attachment", resp["Content-Disposition"])

    def test_pdf_attachment_still_previews_inline(self):
        attachment = self._attachment("payslip.pdf", b"%PDF-1.4 fake", "application/pdf")
        resp = self._fetch(attachment)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("inline", resp["Content-Disposition"])

    def test_image_attachment_still_previews_inline(self):
        attachment = self._attachment("scan.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")
        resp = self._fetch(attachment)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("inline", resp["Content-Disposition"])

    def test_download_query_parameter_still_forces_an_attachment(self):
        attachment = self._attachment("scan.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")
        resp = self.client_hr.get(
            reverse("download_attachment", args=[attachment.pk]) + "?download=1",
        )
        self.assertIn("attachment", resp["Content-Disposition"])

    def test_nosniff_header_is_set(self):
        attachment = self._attachment("scan.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")
        resp = self._fetch(attachment)
        self.assertEqual(resp["X-Content-Type-Options"], "nosniff")

    def test_access_control_is_unchanged(self):
        """The ownership check must still run -- a plain employee who is not
        this employee cannot fetch the file at all."""
        other_user = User.objects.create_user(username="aie_other", password="pass12345")
        other_user.groups.add(Group.objects.get(name="Employee"))
        Employee.objects.create(
            company=self.company, user=other_user, salutation="Mr",
            first_name="Other", last_name="Doe", father_name="Father",
            gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email="aie002@test.com",
            present_address="Addr", permanent_address="Addr",
            personal_mobile="1234567890", employee_code="AIE002",
            designation="Dev", department="IT", date_of_joining=date(2020, 1, 1),
            location="City", pan_no="ABCDE1234F", aadhar_no="123456789012",
            name_as_per_bank="Other", salary_account_number="1234567890",
            ifsc_code="TEST0001234", emergency_contact_name1="Jane",
            emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
            force_password_change=False,
        )
        attachment = self._attachment("scan.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")
        client = Client()
        client.force_login(other_user, backend="django.contrib.auth.backends.ModelBackend")
        resp = client.get(reverse("download_attachment", args=[attachment.pk]))
        self.assertEqual(resp.status_code, 403)
