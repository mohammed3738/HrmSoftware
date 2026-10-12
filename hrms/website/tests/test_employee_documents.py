"""
Employee documents on the profile page: each link opens its own file, the
KYC table names the document type, and only people who may see the
employee's record can open them.

Run with: python manage.py test website.tests.test_employee_documents
"""
import shutil
import tempfile
from datetime import date

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from website.models import (
    Company, Employee, EmployeeAttachment, PreviousEmployment, PreviousEmploymentAttachment,
)

MEDIA = tempfile.mkdtemp(prefix="hrms_test_media_")


def pdf(name, marker):
    return SimpleUploadedFile(name, f"%PDF-1.4 {marker}".encode(), content_type="application/pdf")


def body(resp):
    return b"".join(resp.streaming_content).decode()


@override_settings(MEDIA_ROOT=MEDIA)
class EmployeeDocumentsTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        company = Company.objects.create(name="Doc Co", short_name="DOC", address="A")
        self.emp = Employee.objects.create(company=company, first_name="Doc", last_name="One",
                                           employee_code="DOC1", status="Active")
        self.other = Employee.objects.create(company=company, first_name="Doc", last_name="Two",
                                             employee_code="DOC2", status="Active")
        # The other employee's KYC rows take the low ids, so a previous-
        # employment document's id collides with one of them.
        EmployeeAttachment.objects.create(employee=self.other, file_name="aadhaar", file=pdf("x.pdf", "OTHER-AADHAAR"))
        self.pan = EmployeeAttachment.objects.create(employee=self.emp, file_name="pan", file=pdf("pan.pdf", "MY-PAN"))
        self.custom = EmployeeAttachment.objects.create(
            employee=self.emp, file_name="other", other_file_name="Cancelled cheque", file=pdf("chq.pdf", "MY-CHEQUE"),
        )
        job = PreviousEmployment.objects.create(employee=self.emp, employer_name="Old Co", from_date=date(2018, 1, 1),
                                                to_date=date(2019, 1, 1), last_ctc=1)
        self.prev_doc = PreviousEmploymentAttachment.objects.create(
            previous_employment=job, file=pdf("relieving.pdf", "MY-RELIEVING"), document_name="Relieving letter",
        )

        self.admin = Client()
        self.admin.force_login(User.objects.create_superuser("doc_admin", "d@test.com", "pass12345"),
                               backend="django.contrib.auth.backends.ModelBackend")

    def _login(self, username, role, employee=None):
        user = User.objects.create_user(username=username, password="pass12345")
        user.groups.add(Group.objects.get(name=role))
        if employee:
            Employee.objects.filter(pk=employee.pk).update(user=user, force_password_change=False)
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return client

    def test_previous_employment_document_opens_its_own_file(self):
        resp = self.admin.get(reverse("download_previous_attachment", args=[self.prev_doc.pk]))
        self.assertIn("MY-RELIEVING", body(resp))

    def test_profile_links_each_document_to_its_own_file(self):
        page = self.admin.get(reverse("employee_detail", args=[self.emp.pk]))
        self.assertContains(page, reverse("download_previous_attachment", args=[self.prev_doc.pk]))
        self.assertContains(page, reverse("download_attachment", args=[self.pan.pk]))
        # Document-type column
        self.assertContains(page, "<td class=\"fw-semibold\">PAN</td>", html=False)
        self.assertContains(page, "Cancelled cheque")
        self.assertContains(page, "Relieving letter")

    def test_kyc_file_opens_inline_or_downloads(self):
        url = reverse("download_attachment", args=[self.pan.pk])
        resp = self.admin.get(url)
        self.assertIn("MY-PAN", body(resp))
        self.assertTrue(resp["Content-Disposition"].startswith("inline"))
        self.assertTrue(self.admin.get(url + "?download=1")["Content-Disposition"].startswith("attachment"))

    def test_employee_opens_own_documents_but_not_a_colleagues(self):
        client = self._login("doc_emp", "Employee", employee=self.emp)
        self.assertEqual(client.get(reverse("download_attachment", args=[self.pan.pk])).status_code, 200)
        self.assertEqual(client.get(reverse("download_previous_attachment", args=[self.prev_doc.pk])).status_code, 200)
        theirs = EmployeeAttachment.objects.get(employee=self.other)
        self.assertEqual(client.get(reverse("download_attachment", args=[theirs.pk])).status_code, 403)

    def test_hr_opens_anyones_documents(self):
        client = self._login("doc_hr", "HR")
        self.assertEqual(client.get(reverse("download_attachment", args=[self.pan.pk])).status_code, 200)
