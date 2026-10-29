"""
Regression tests for serving uploaded files behind a permission check.

Everything under MEDIA_ROOT is an employee document -- KYC scans,
offboarding letters, asset receipts, bulk-upload spreadsheets. nginx was
configured to serve that whole directory itself:

    location /media/ { alias .../hrms/media/; }        DEPLOYMENT.md

so `_serve_employee_file`'s can_access_employee_record() check was
decorative: the same bytes came back to an anonymous request one URL over.
Two things made the paths easy to come by rather than merely guessable:

  * offboarding_detail / offboarding_edit_data returned `FieldFile.url`
    -- raw /media/ paths -- in their JSON, and both were themselves
    ungated until the previous commit;
  * only `employee_photo_path` randomises its filename. The other upload
    fields keep whatever the uploader called the file, so an Aadhaar scan
    sits at a predictable /media/employee_attachments/aadhaar.pdf.

These tests cover the application half: every document now has a view that
checks permission before streaming, and nothing hands out a /media/ path
any more. The deployment half -- removing the public location block -- is
asserted on only indirectly, by proving no /media/ URL is emitted.

Run with:
    python manage.py test website.tests.test_protected_media
"""
import shutil
import tempfile
from datetime import date

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from website.models import (
    AssetHandover,
    Company,
    Employee,
    Offboarding,
)


def make_employee(company, code, first_name, user=None):
    return Employee.objects.create(
        company=company, user=user, salutation="Mr", first_name=first_name,
        last_name="Doe", father_name="Father", gender="Male", blood_group="O+",
        date_of_birth=date(1990, 1, 1), place_of_birth="City",
        personal_email=f"{code}@test.com", present_address="Addr",
        permanent_address="Addr", personal_mobile="1234567890",
        employee_code=code, designation="Dev", department="IT",
        date_of_joining=date(2020, 1, 1), location="City", pan_no="ABCDE1234F",
        aadhar_no="123456789012", name_as_per_bank=first_name,
        salary_account_number="1234567890", ifsc_code="TEST0001234",
        emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
        emergency_contact_mobile1="0987654321", status="Active",
        force_password_change=False,
    )


# Uploading through SimpleUploadedFile writes into MEDIA_ROOT, and the
# test runner does not clean it up -- without this every run left a new
# batch of randomly-suffixed files in the developer's hrms/media/.
_MEDIA_ROOT = tempfile.mkdtemp(prefix="hrms-test-media-")


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class ProtectedMediaTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="PM", name="Protected Media Co", phone="1",
            email="pm@test.com", address="Addr",
        )
        self.leaver = make_employee(self.company, "PM001", "Leaver")

        self.offboarding = Offboarding.objects.create(
            employee=self.leaver,
            date_of_resignation=date(2026, 1, 1),
            date_of_relieving=date(2026, 1, 31),
            experience_certificate=SimpleUploadedFile(
                "experience.pdf", b"%PDF-1.4 experience", content_type="application/pdf"),
            relieving_letter=SimpleUploadedFile(
                "relieving.pdf", b"%PDF-1.4 relieving", content_type="application/pdf"),
            fnf_documents=SimpleUploadedFile(
                "fnf.pdf", b"%PDF-1.4 fnf", content_type="application/pdf"),
        )
        self.asset = AssetHandover.objects.create(
            offboarding=self.offboarding, asset_type="Laptop", quantity=1,
            receipt=SimpleUploadedFile("receipt.pdf", b"%PDF-1.4 receipt",
                                       content_type="application/pdf"),
        )

        self.hr_user = User.objects.create_user(username="pm_hr", password="pass12345")
        self.hr_user.groups.add(Group.objects.get(name="HR"))

        self.emp_user = User.objects.create_user(username="pm_emp", password="pass12345")
        self.emp_user.groups.add(Group.objects.get(name="Employee"))
        make_employee(self.company, "PM002", "Nosy", user=self.emp_user)

    def _as(self, user):
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return client

    # ── the JSON endpoints must not hand out /media/ paths ───────────────

    def test_offboarding_detail_emits_no_media_paths(self):
        payload = self._as(self.hr_user).get(
            reverse("offboarding-detail", args=[self.offboarding.pk]),
        ).json()
        self.assertNotIn("/media/", str(payload))
        self.assertIn("/document/", payload["experience_certificate"])

    def test_offboarding_edit_data_emits_no_media_paths(self):
        payload = self._as(self.hr_user).get(
            reverse("offboarding-edit-data", args=[self.offboarding.pk]),
        ).json()
        self.assertNotIn("/media/", str(payload))
        self.assertIn(
            "/document/", payload["offboarding"]["relieving_letter"]["url"],
        )

    def test_a_missing_document_reports_no_url_rather_than_a_broken_one(self):
        payload = self._as(self.hr_user).get(
            reverse("offboarding-detail", args=[self.offboarding.pk]),
        ).json()
        self.assertIsNone(payload["other_documents"])

    # ── the download views themselves ────────────────────────────────────

    def test_hr_can_download_an_offboarding_document(self):
        resp = self._as(self.hr_user).get(
            reverse("download-offboarding-document",
                    args=[self.offboarding.pk, "experience_certificate"]),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(b"".join(resp.streaming_content), b"%PDF-1.4 experience")

    def test_an_employee_cannot_download_an_offboarding_document(self):
        resp = self._as(self.emp_user).get(
            reverse("download-offboarding-document",
                    args=[self.offboarding.pk, "relieving_letter"]),
        )
        self.assertEqual(resp.status_code, 403)

    def test_an_anonymous_visitor_is_redirected_to_login(self):
        resp = Client().get(
            reverse("download-offboarding-document",
                    args=[self.offboarding.pk, "fnf_documents"]),
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp["Location"])

    def test_hr_can_download_an_asset_document(self):
        resp = self._as(self.hr_user).get(
            reverse("download-asset-document", args=[self.asset.pk, "receipt"]),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(b"".join(resp.streaming_content), b"%PDF-1.4 receipt")

    def test_an_employee_cannot_download_an_asset_document(self):
        resp = self._as(self.emp_user).get(
            reverse("download-asset-document", args=[self.asset.pk, "receipt"]),
        )
        self.assertEqual(resp.status_code, 403)

    def test_an_unknown_field_name_is_not_a_way_to_read_other_attributes(self):
        """`field` comes from the URL, so it must be checked against a
        whitelist rather than passed to getattr()."""
        for field in ("employee", "date_of_resignation", "pk", "__class__"):
            with self.subTest(field=field):
                resp = self._as(self.hr_user).get(
                    f"/offboarding/{self.offboarding.pk}/document/{field}/",
                )
                self.assertEqual(resp.status_code, 404)

    def test_a_document_that_was_never_uploaded_is_a_404(self):
        resp = self._as(self.hr_user).get(
            reverse("download-offboarding-document",
                    args=[self.offboarding.pk, "other_documents"]),
        )
        self.assertEqual(resp.status_code, 404)

    # ── X-Accel-Redirect mode ────────────────────────────────────────────

    @override_settings(MEDIA_ACCEL_REDIRECT="/protected-media/")
    def test_accel_redirect_hands_the_body_to_nginx(self):
        resp = self._as(self.hr_user).get(
            reverse("download-offboarding-document",
                    args=[self.offboarding.pk, "experience_certificate"]),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp["X-Accel-Redirect"].startswith("/protected-media/"))
        self.assertIn("offboarding/certificates/", resp["X-Accel-Redirect"])
        self.assertEqual(resp.content, b"")
        self.assertEqual(resp["X-Content-Type-Options"], "nosniff")

    @override_settings(MEDIA_ACCEL_REDIRECT="/protected-media/")
    def test_accel_redirect_still_enforces_permission(self):
        resp = self._as(self.emp_user).get(
            reverse("download-offboarding-document",
                    args=[self.offboarding.pk, "experience_certificate"]),
        )
        self.assertEqual(resp.status_code, 403)

    # ── the page that renders those links ────────────────────────────────

    def test_the_offboarding_page_renders_and_leaks_no_media_path(self):
        """The asset rows build their link with {% url %} and a pk, while
        the formset renders blank extra rows whose instance has no pk --
        and {% url %} with None raises NoReverseMatch. The surrounding
        `{% if f.instance.pk %}` guard is what keeps that from being a 500,
        so it is load-bearing and worth a test: this page had none.

        The saved asset's own link is not asserted here because the list
        page renders an empty formset for a *new* offboarding record; the
        links for an existing one are built by JavaScript from
        offboarding-edit-data, which is covered above."""
        resp = self._as(self.hr_user).get(reverse("offboarding-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("/media/offboarding/", resp.content.decode())

    @override_settings(MEDIA_ACCEL_REDIRECT="/protected-media/")
    def test_accel_redirect_forces_download_for_executable_types(self):
        self.offboarding.other_documents = SimpleUploadedFile(
            "notes.html", b"<script>1</script>", content_type="text/html")
        self.offboarding.save()
        resp = self._as(self.hr_user).get(
            reverse("download-offboarding-document",
                    args=[self.offboarding.pk, "other_documents"]),
        )
        self.assertIn("attachment", resp["Content-Disposition"])

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA_ROOT, ignore_errors=True)
