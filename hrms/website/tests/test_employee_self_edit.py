"""
An employee edits their own personal details from My Details. Nothing
changes until an approver (Super Admin / Admin / Payroll Officer) accepts
it on the Employee Changes page; a rejection leaves the record as it was.

Run with: python manage.py test website.tests.test_employee_self_edit
"""
from datetime import date

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import Company, Employee, EmployeeChangeRequest


class EmployeeSelfEditTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(short_name="SE", name="Self Co", phone="1", email="s@t.com", address="A")
        self.user = User.objects.create_user(username="self_emp", password="pass12345")
        self.user.groups.add(Group.objects.get(name="Employee"))
        self.emp = Employee.objects.create(
            company=self.company, user=self.user, first_name="Nazim", last_name="M", employee_code="SE1",
            date_of_joining=date(2020, 1, 1), status="Active", force_password_change=False,
            personal_mobile="1111111111", present_address="Old address", pan_no="ABCDE1234F",
        )
        self.client = self.login(self.user)

    def login(self, user):
        c = Client()
        c.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return c

    def approver(self, role="Admin"):
        user = User.objects.create_user(username=f"appr_{role}", password="pass12345")
        user.groups.add(Group.objects.get(name=role))
        return self.login(user)

    def send(self, **changes):
        data = {
            "personal_mobile": self.emp.personal_mobile or "",
            "present_address": self.emp.present_address or "",
            **changes,
        }
        return self.client.post(reverse("my_details_edit"), data)

    def test_profile_offers_edit_button_only_on_own_record(self):
        resp = self.client.get(reverse("employee_detail", args=[self.emp.pk]))
        self.assertContains(resp, reverse("my_details_edit"))
        other = Employee.objects.create(company=self.company, first_name="Other", last_name="X", employee_code="SE2",
                                        date_of_joining=date(2020, 1, 1), status="Active")
        admin = self.approver()
        self.assertNotContains(admin.get(reverse("employee_detail", args=[other.pk])), reverse("my_details_edit"))

    def test_changes_wait_for_review(self):
        resp = self.send(personal_mobile="2222222222", present_address="New address")
        self.assertRedirects(resp, reverse("my_details_edit"))
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.personal_mobile, "1111111111")   # unchanged until approved
        cr = EmployeeChangeRequest.objects.get(employee=self.emp)
        self.assertEqual(cr.status, EmployeeChangeRequest.STATUS_PENDING)
        self.assertEqual(set(cr.field_changes), {"personal_mobile", "present_address"})
        self.assertEqual(cr.requested_by, self.user)

        page = self.client.get(reverse("my_details_edit"))
        self.assertContains(page, "Waiting for review")
        self.assertContains(page, "Pending")

    def test_approver_accepts_and_changes_apply(self):
        self.send(personal_mobile="2222222222")
        cr = EmployeeChangeRequest.objects.get(employee=self.emp)
        admin = self.approver("Payroll Officer")
        admin.post(reverse("employee_change_request_detail", args=[cr.pk]), {"decision": "approve", "note": "ok"})
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.personal_mobile, "2222222222")
        self.assertContains(self.client.get(reverse("my_details_edit")), "Approved")

    def test_approver_rejects_and_nothing_changes(self):
        self.send(personal_mobile="2222222222")
        cr = EmployeeChangeRequest.objects.get(employee=self.emp)
        self.approver().post(reverse("employee_change_request_detail", args=[cr.pk]),
                             {"decision": "reject", "note": "Wrong number"})
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.personal_mobile, "1111111111")
        page = self.client.get(reverse("my_details_edit"))
        self.assertContains(page, "Rejected")
        self.assertContains(page, "Wrong number")

    def test_employee_cannot_approve_their_own_request(self):
        self.send(personal_mobile="2222222222")
        cr = EmployeeChangeRequest.objects.get(employee=self.emp)
        resp = self.client.post(reverse("employee_change_request_detail", args=[cr.pk]), {"decision": "approve"})
        self.assertEqual(resp.status_code, 403)
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.personal_mobile, "1111111111")

    def test_protected_fields_cannot_be_changed(self):
        self.send(personal_mobile="2222222222", pan_no="ZZZZZ9999Z", first_name="Hacker", designation="CEO")
        cr = EmployeeChangeRequest.objects.get(employee=self.emp)
        self.assertEqual(set(cr.field_changes), {"personal_mobile"})

    def test_one_pending_request_at_a_time(self):
        self.send(personal_mobile="2222222222")
        self.send(personal_mobile="3333333333")
        self.assertEqual(EmployeeChangeRequest.objects.filter(employee=self.emp).count(), 1)

    def test_nothing_changed_sends_nothing(self):
        self.send()
        self.assertFalse(EmployeeChangeRequest.objects.exists())

    # ── bank details ────────────────────────────────────────────────────
    def test_bank_change_waits_for_review_then_applies(self):
        self.send(name_as_per_bank="NAZIM M", salary_account_number="1234 5678 9012", ifsc_code="sbin0001234")
        self.emp.refresh_from_db()
        self.assertIsNone(self.emp.salary_account_number)          # not until approved
        cr = EmployeeChangeRequest.objects.get(employee=self.emp)
        self.assertEqual(cr.field_changes["salary_account_number"]["new"], "123456789012")
        self.assertEqual(cr.field_changes["ifsc_code"]["new"], "SBIN0001234")

        self.approver().post(reverse("employee_change_request_detail", args=[cr.pk]), {"decision": "approve"})
        self.emp.refresh_from_db()
        self.assertEqual((self.emp.name_as_per_bank, self.emp.salary_account_number, self.emp.ifsc_code),
                         ("NAZIM M", "123456789012", "SBIN0001234"))

    def test_bad_bank_details_are_refused(self):
        resp = self.send(salary_account_number="12AB", ifsc_code="SBIN1234")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "9 to 18 digits")
        self.assertContains(resp, "valid IFSC code")
        self.assertFalse(EmployeeChangeRequest.objects.exists())


class HrDecidesSelfEditsTest(EmployeeSelfEditTest):
    """HR approves or rejects what employees send from My Details, but not
    edits made by someone else to an employee (those stay with Admin)."""

    def pending(self):
        self.send(personal_mobile="2222222222")
        return EmployeeChangeRequest.objects.get(employee=self.emp)

    def test_hr_sees_and_approves(self):
        cr = self.pending()
        hr = self.approver("HR")
        page = hr.get(reverse("employee_change_requests"))
        self.assertContains(page, "Review")
        self.assertContains(page, 'class="form-check-input request-box"')
        self.assertContains(hr.get(reverse("employee_change_request_detail", args=[cr.pk])), "Approve &amp; apply")
        hr.post(reverse("employee_change_request_detail", args=[cr.pk]), {"decision": "approve"})
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.personal_mobile, "2222222222")

    def test_hr_rejects(self):
        cr = self.pending()
        self.approver("HR").post(reverse("employee_change_request_detail", args=[cr.pk]), {"decision": "reject"})
        cr.refresh_from_db()
        self.assertEqual(cr.status, EmployeeChangeRequest.STATUS_REJECTED)

    def test_hr_bulk_approves(self):
        cr = self.pending()
        self.approver("HR").post(reverse("employee_change_requests_bulk"), {"decision": "approve", "ids": [cr.pk]})
        cr.refresh_from_db()
        self.assertEqual(cr.status, EmployeeChangeRequest.STATUS_APPROVED)

    def test_hr_cannot_decide_someone_elses_edit(self):
        admin_user = User.objects.create_user(username="editor", password="pass12345")
        cr = EmployeeChangeRequest.objects.create(employee=self.emp, requested_by=admin_user,
                                                  field_changes={})
        hr = self.approver("HR")
        self.assertEqual(hr.post(reverse("employee_change_request_detail", args=[cr.pk]),
                                 {"decision": "approve"}).status_code, 403)
        hr.post(reverse("employee_change_requests_bulk"), {"decision": "approve", "ids": [cr.pk]})
        cr.refresh_from_db()
        self.assertEqual(cr.status, EmployeeChangeRequest.STATUS_PENDING)

    def test_hr_edits_to_employees_still_need_approval(self):
        from website.services.employee_changes import can_approve_changes
        hr_user = User.objects.create_user(username="hr_only", password="pass12345")
        hr_user.groups.add(Group.objects.get(name="HR"))
        self.assertFalse(can_approve_changes(hr_user))


class SelfEditPhotoTest(EmployeeSelfEditTest):
    """Employees change or remove their profile photo from My Details; it
    waits for review like every other change."""

    def setUp(self):
        import shutil, tempfile
        from django.test import override_settings
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        super().setUp()

    def png(self, name="me.png"):
        from io import BytesIO
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        buf = BytesIO()
        Image.new("RGB", (40, 40), "red").save(buf, "PNG")
        return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")

    def test_page_has_photo_section(self):
        page = self.client.get(reverse("my_details_edit"))
        self.assertContains(page, "Profile photo")
        self.assertContains(page, 'id="photoPreview"')

    def test_new_photo_waits_then_applies_on_approval(self):
        self.send(photo=self.png())
        self.emp.refresh_from_db()
        self.assertFalse(self.emp.photo)                        # not yet
        cr = EmployeeChangeRequest.objects.get(employee=self.emp)
        self.assertTrue(cr.photo)
        self.approver("HR").post(reverse("employee_change_request_detail", args=[cr.pk]), {"decision": "approve"})
        self.emp.refresh_from_db()
        self.assertTrue(self.emp.photo)

    def test_remove_photo_request(self):
        from website.services.employee_changes import apply_change_request
        self.send(photo=self.png())
        cr = EmployeeChangeRequest.objects.get(employee=self.emp)
        apply_change_request(cr, User.objects.create_superuser("ph_su", "p@t.com", "x"), "")
        self.assertContains(self.client.get(reverse("my_details_edit")), "Remove my current photo")
        self.send(**{"photo-clear": "on"})
        cr2 = EmployeeChangeRequest.objects.filter(employee=self.emp, status="pending").get()
        self.assertTrue(cr2.clear_photo)
