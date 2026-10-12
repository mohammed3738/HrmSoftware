"""
Onboarding progress, the 15-day / 100% edit lock, and the change-approval
flow that replaces direct edits once the lock applies.

Run with: python manage.py test website.tests.test_employee_onboarding
"""
import json
import shutil
import tempfile
from datetime import date, timedelta

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms.models import model_to_dict
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from website.forms import AttachmentFormSet, PreviousEmploymentFormSet
from website.models import (
    Branch, Company, Employee, EmployeeAttachment, EmployeeChangeRequest, PreviousEmployment,
)
from website.services.onboarding import onboarding_progress
from website.utils.permissions import has_feature_permission

MEDIA = tempfile.mkdtemp(prefix="hrms_test_media_")

FULL_DETAILS = dict(
    salutation="Mr.", first_name="Full", last_name="Record", father_name="F", gender="Male",
    blood_group="O+", date_of_birth=date(1990, 1, 1), place_of_birth="City",
    personal_email="full@test.com", present_address="A", permanent_address="A",
    personal_mobile="1234567890", designation="Dev", department="IT",
    date_of_joining=date(2020, 1, 1), location="City", pan_no="ABCDE1234F",
    aadhar_no="123456789012", name_as_per_bank="Full Record", salary_account_number="1",
    ifsc_code="TEST0001234", emergency_contact_name1="J", emergency_contact_relation1="Spouse",
    emergency_contact_mobile1="0987654321", status="Active",
)


def a_file(name="doc.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4 test", content_type="application/pdf")


@override_settings(MEDIA_ROOT=MEDIA)
class OnboardingTestBase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.company = Company.objects.create(name="Onb Co", short_name="ONB")
        self.branch = Branch.objects.create(branch_name="Onb HQ")
        self.hr = self._user("onb_hr", "HR")
        self.admin = self._user("onb_admin", "Admin")

    def _user(self, username, role):
        user = User.objects.create_user(username=username, password="pass12345")
        user.groups.add(Group.objects.get(name=role))
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        user.client = client
        return user

    def _employee(self, code="ONB001", started=None, **extra):
        fields = {**FULL_DETAILS, **extra}
        emp = Employee.objects.create(company=self.company, branch=self.branch, employee_code=code, **fields)
        if started is not None:
            Employee.objects.filter(pk=emp.pk).update(onboarding_started_at=started)
            emp.refresh_from_db()
        return emp

    def _complete(self, emp):
        """Fill in everything the checklist still wants: no photo, resume or
        offer letter -- only Aadhaar and PAN are required."""
        emp.is_fresher = True
        emp.save()
        for code in ("aadhaar", "pan"):
            EmployeeAttachment.objects.create(employee=emp, file_name=code, file=a_file(f"{code}.pdf"))
        return emp

    def _post_edit(self, user, emp, changes=None, files=None, extra=None):
        emp = Employee.objects.get(pk=emp.pk)
        data = {k: v for k, v in model_to_dict(emp).items() if v is not None and k != "photo"}
        data.update(changes or {})
        for formset in (PreviousEmploymentFormSet(instance=emp), AttachmentFormSet(instance=emp)):
            mgmt = formset.management_form
            for name in ("TOTAL_FORMS", "INITIAL_FORMS", "MIN_NUM_FORMS", "MAX_NUM_FORMS"):
                data[f"{formset.prefix}-{name}"] = mgmt[name].value()
            for i, form in enumerate(formset.initial_forms):
                for name, field in form.fields.items():
                    value = form.initial.get(name)
                    if value not in (None, "") and name != "file":
                        data[f"{formset.prefix}-{i}-{name}"] = getattr(value, "pk", value)
                data[f"{formset.prefix}-{i}-id"] = form.instance.pk
        data.update(extra or {})
        data.update(files or {})
        resp = user.client.post(reverse("employee_edit", args=[emp.pk]), data=data)
        if resp.status_code == 200 and resp.context:
            errors = [resp.context["form"].errors] + [
                fs.errors for fs in (resp.context.get("formset"), resp.context.get("attachment_formset")) if fs
            ]
            self.fail(f"Form invalid: {errors}")
        return resp


class OnboardingProgressTest(OnboardingTestBase):
    def test_details_only_is_seventy_percent(self):
        # Personal, office, bank, emergency = 25 + 15 + 20 + 10.
        progress = onboarding_progress(self._employee())
        self.assertEqual(progress["percent"], 70)
        self.assertEqual(progress["remaining"], 30)
        self.assertFalse(progress["complete"])
        self.assertIn("Previous employment (or tick Fresher)", progress["missing"])
        self.assertIn("KYC documents (2 more of any 2)", progress["missing"])
        self.assertNotIn("Resume", progress["missing"])
        self.assertNotIn("Photo", progress["missing"])

    def test_partial_section_counts_proportionally(self):
        emp = Employee.objects.create(company=self.company, employee_code="ONB-P", first_name="Only", last_name="")
        progress = onboarding_progress(emp)
        personal = next(s for s in progress["sections"] if s["key"] == "personal")
        self.assertEqual((personal["done"], personal["count"]), (1, 9))
        self.assertLess(progress["percent"], 30)

    def test_previous_employment_or_fresher_counts(self):
        emp = self._employee()
        PreviousEmployment.objects.create(
            employee=emp, employer_name="Old Co", from_date=date(2018, 1, 1), to_date=date(2019, 1, 1), last_ctc=1,
        )
        self.assertEqual(onboarding_progress(emp)["percent"], 80)
        emp2 = self._employee(code="ONB002", is_fresher=True)
        self.assertEqual(onboarding_progress(emp2)["percent"], 80)

    def test_complete_is_one_hundred(self):
        progress = onboarding_progress(self._complete(self._employee()))
        self.assertEqual(progress["percent"], 100)
        self.assertTrue(progress["complete"])
        self.assertEqual(progress["missing"], [])

    def test_aadhaar_and_pan_alone_complete_the_documents(self):
        emp = self._employee(is_fresher=True)
        EmployeeAttachment.objects.create(employee=emp, file_name="aadhaar", file=a_file())
        self.assertEqual(onboarding_progress(emp)["percent"], 90)
        EmployeeAttachment.objects.create(employee=emp, file_name="pan", file=a_file())
        progress = onboarding_progress(emp)
        self.assertEqual(progress["percent"], 100)
        self.assertTrue(progress["complete"])

    def test_any_two_documents_complete_the_section(self):
        emp = self._employee(code="ONB-2DOC", is_fresher=True)
        EmployeeAttachment.objects.create(employee=emp, file_name="resume", file=a_file())
        progress = onboarding_progress(emp)
        self.assertEqual(progress["percent"], 90)
        self.assertIn("KYC documents (1 more of any 2)", progress["missing"])
        EmployeeAttachment.objects.create(employee=emp, file_name="other", other_file_name="Cheque", file=a_file())
        self.assertTrue(onboarding_progress(emp)["complete"])

    def test_existing_staff_start_from_date_of_joining(self):
        # Migration 0042 back-fills onboarding_started_at from date_of_joining;
        # new records start today.
        self.assertEqual(self._employee().onboarding_started_at, date.today())


class EditLockTest(OnboardingTestBase):
    def test_hr_edits_directly_within_fifteen_days(self):
        emp = self._employee(started=date.today() - timedelta(days=14))
        resp = self._post_edit(self.hr, emp, {"designation": "Lead"})
        self.assertEqual(resp.status_code, 302)
        emp.refresh_from_db()
        self.assertEqual(emp.designation, "Lead")
        self.assertFalse(EmployeeChangeRequest.objects.exists())

    def test_hr_edit_after_fifteen_days_goes_for_approval(self):
        emp = self._employee(started=date.today() - timedelta(days=15))
        self._post_edit(self.hr, emp, {"designation": "Lead"})
        emp.refresh_from_db()
        self.assertEqual(emp.designation, "Dev")
        cr = EmployeeChangeRequest.objects.get()
        self.assertEqual(cr.status, "pending")
        self.assertEqual(cr.field_changes["designation"]["old"], "Dev")
        self.assertEqual(cr.field_changes["designation"]["new"], "Lead")

    def test_hr_edit_of_complete_onboarding_goes_for_approval(self):
        emp = self._complete(self._employee())
        self._post_edit(self.hr, emp, {"designation": "Lead"})
        emp.refresh_from_db()
        self.assertEqual(emp.designation, "Dev")
        self.assertEqual(EmployeeChangeRequest.objects.count(), 1)

    def test_admin_always_edits_directly(self):
        emp = self._complete(self._employee(started=date.today() - timedelta(days=60)))
        self._post_edit(self.admin, emp, {"designation": "Lead"})
        emp.refresh_from_db()
        self.assertEqual(emp.designation, "Lead")
        self.assertFalse(EmployeeChangeRequest.objects.exists())

    def test_unchanged_submission_creates_nothing(self):
        emp = self._employee(started=date.today() - timedelta(days=30))
        self._post_edit(self.hr, emp)
        self.assertFalse(EmployeeChangeRequest.objects.exists())

    def test_pending_request_blocks_another(self):
        emp = self._employee(started=date.today() - timedelta(days=30))
        self._post_edit(self.hr, emp, {"designation": "Lead"})
        self._post_edit(self.hr, emp, {"department": "Ops"})
        self.assertEqual(EmployeeChangeRequest.objects.count(), 1)
        page = self.hr.client.get(reverse("employee_edit", args=[emp.pk]))
        self.assertContains(page, "waiting for approval")
        self.assertContains(page, "Submit for approval")

    def test_edit_page_shows_progress_and_lock_banner(self):
        emp = self._employee(started=date.today() - timedelta(days=20))
        page = self.hr.client.get(reverse("employee_edit", args=[emp.pk]))
        self.assertContains(page, "70% complete")
        self.assertContains(page, "sent to Admin for approval")
        fresh = self._employee(code="ONB009")
        page = self.hr.client.get(reverse("employee_edit", args=[fresh.pk]))
        self.assertNotContains(page, "sent to Admin for approval")
        self.assertContains(page, "Direct edits allowed until")

    def test_bulk_status_skips_locked_employees_for_hr(self):
        locked = self._employee(started=date.today() - timedelta(days=30))
        open_ = self._employee(code="ONB010")
        resp = self.hr.client.post(
            reverse("bulk-employee-action"),
            data=json.dumps({"employee_ids": [locked.pk, open_.pk], "status": "Pending"}),
            content_type="application/json",
        )
        self.assertEqual(resp.json()["updated"], 1)
        self.assertEqual(resp.json()["skipped_locked"], 1)
        locked.refresh_from_db()
        open_.refresh_from_db()
        self.assertEqual((locked.status, open_.status), ("Active", "Pending"))


class ApprovalTest(OnboardingTestBase):
    def setUp(self):
        super().setUp()
        self.emp = self._employee(started=date.today() - timedelta(days=30))

    def _request(self, changes=None, files=None, extra=None):
        self._post_edit(self.hr, self.emp, changes, files, extra)
        return EmployeeChangeRequest.objects.get()

    def _decide(self, user, cr, decision, note=""):
        return user.client.post(
            reverse("employee_change_request_detail", args=[cr.pk]), {"decision": decision, "note": note},
        )

    def test_approve_applies_field_changes(self):
        cr = self._request({"designation": "Lead", "date_of_birth": "1991-02-03", "is_fresher": "on"})
        self._decide(self.admin, cr, "approve", "ok")
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.designation, "Lead")
        self.assertEqual(self.emp.date_of_birth, date(1991, 2, 3))
        self.assertTrue(self.emp.is_fresher)
        cr.refresh_from_db()
        self.assertEqual((cr.status, cr.decided_by, cr.decision_note), ("approved", self.admin, "ok"))

    def test_reject_discards_changes(self):
        cr = self._request({"designation": "Lead"})
        self._decide(self.admin, cr, "reject", "wrong")
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.designation, "Dev")
        cr.refresh_from_db()
        self.assertEqual(cr.status, "rejected")

    def test_new_document_is_held_until_approved(self):
        prefix = AttachmentFormSet(instance=self.emp).prefix
        cr = self._request(
            extra={f"{prefix}-TOTAL_FORMS": 1, f"{prefix}-0-file_name": "aadhaar"},
            files={f"{prefix}-0-file": a_file("aadhaar.pdf")},
        )
        self.assertFalse(self.emp.attachments.exists())
        self.assertEqual(cr.files.count(), 1)
        self._decide(self.admin, cr, "approve")
        self.assertEqual(list(self.emp.attachments.values_list("file_name", flat=True)), ["aadhaar"])

    def test_new_previous_employment_is_held_until_approved(self):
        prefix = PreviousEmploymentFormSet(instance=self.emp).prefix
        cr = self._request(extra={
            f"{prefix}-TOTAL_FORMS": 1, f"{prefix}-0-employer_name": "Old Co",
            f"{prefix}-0-from_date": "2018-01-01", f"{prefix}-0-to_date": "2019-12-31",
            f"{prefix}-0-last_ctc": "500000",
        })
        self.assertFalse(self.emp.previous_employments.exists())
        self._decide(self.admin, cr, "approve")
        prev = self.emp.previous_employments.get()
        self.assertEqual((prev.employer_name, prev.to_date), ("Old Co", date(2019, 12, 31)))

    def test_hr_cannot_decide(self):
        cr = self._request({"designation": "Lead"})
        self.assertEqual(self._decide(self.hr, cr, "approve").status_code, 403)
        cr.refresh_from_db()
        self.assertEqual(cr.status, "pending")

    def test_hr_can_follow_requests(self):
        cr = self._request({"designation": "Lead"})
        resp = self.hr.client.get(reverse("employee_change_requests"))
        self.assertContains(resp, self.emp.employee_code)
        detail = self.hr.client.get(reverse("employee_change_request_detail", args=[cr.pk]))
        self.assertContains(detail, "Lead")
        self.assertNotContains(detail, "Approve &amp; apply")
        self.assertContains(
            self.admin.client.get(reverse("employee_change_request_detail", args=[cr.pk])), "Approve &amp; apply",
        )

    def test_decided_request_cannot_be_decided_again(self):
        cr = self._request({"designation": "Lead"})
        self._decide(self.admin, cr, "reject")
        self._decide(self.admin, cr, "approve")
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.designation, "Dev")

    def test_approval_rights_seeded_for_admin_roles_only(self):
        self.assertFalse(has_feature_permission(self.hr, "employee_change_approval", "approve"))
        self.assertTrue(has_feature_permission(self.admin, "employee_change_approval", "approve"))
        po = self._user("onb_po", "Payroll Officer")
        self.assertTrue(has_feature_permission(po, "employee_change_approval", "approve"))


class OnboardingListsTest(OnboardingTestBase):
    def test_list_shows_progress_and_filters_pending(self):
        incomplete = self._employee(code="ONB-INC")
        done = self._complete(self._employee(code="ONB-DONE"))
        resp = self.hr.client.get(reverse("employee_list"))
        rows = {r["code"]: r for r in resp.context["employees"]}
        self.assertEqual(rows["ONB-INC"]["percent"], 70)
        self.assertTrue(rows["ONB-DONE"]["complete"])
        self.assertContains(resp, done.employee_code)
        resp = self.hr.client.get(reverse("employee_list") + "?onboarding=pending")
        self.assertContains(resp, incomplete.employee_code)
        self.assertNotContains(resp, done.employee_code)

    def test_dashboard_lists_pending_onboarding_until_complete(self):
        emp = self._employee(code="ONB-DASH", started=date.today() - timedelta(days=20))
        resp = self.hr.client.get(reverse("admin-dashboard"))
        self.assertContains(resp, "Pending Onboarding")
        self.assertContains(resp, "ONB-DASH")
        self.assertContains(resp, "Needs approval")
        self._complete(emp)
        resp = self.hr.client.get(reverse("admin-dashboard"))
        self.assertNotContains(resp, "ONB-DASH")

    def test_dashboard_shows_change_count_to_approvers(self):
        emp = self._employee(code="ONB-CR", started=date.today() - timedelta(days=20))
        self._post_edit(self.hr, emp, {"designation": "Lead"})
        self.assertContains(self.admin.client.get(reverse("admin-dashboard")), "awaiting approval")
        self.assertNotContains(self.hr.client.get(reverse("admin-dashboard")), "awaiting approval")

    def test_detail_page_shows_checklist(self):
        emp = self._employee(code="ONB-DET")
        resp = self.hr.client.get(reverse("employee_detail", args=[emp.pk]))
        self.assertContains(resp, "70% complete")
        self.assertContains(resp, "Missing: KYC documents (2 more of any 2)")


class ApprovalEdgeCasesTest(OnboardingTestBase):
    def setUp(self):
        super().setUp()
        self.emp = self._employee(started=date.today() - timedelta(days=30), present_address="Line 1\nLine 2")

    def test_superuser_without_a_role_can_approve(self):
        self._post_edit(self.hr, self.emp, {"designation": "Lead"})
        cr = EmployeeChangeRequest.objects.get()
        root = User.objects.create_superuser("onb_root", "r@test.com", "pass12345")
        client = Client()
        client.force_login(root, backend="django.contrib.auth.backends.ModelBackend")
        page = client.get(reverse("employee_change_request_detail", args=[cr.pk]))
        self.assertContains(page, "Approve &amp; apply")
        client.post(reverse("employee_change_request_detail", args=[cr.pk]), {"decision": "approve"})
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.designation, "Lead")

    def test_browser_line_endings_are_not_a_change(self):
        # A browser posts the untouched address back with \r\n line breaks.
        self._post_edit(self.hr, self.emp, {"designation": "Lead", "present_address": "Line 1\r\nLine 2"})
        cr = EmployeeChangeRequest.objects.get()
        self.assertEqual(list(cr.field_changes), ["designation"])


class BulkApprovalTest(OnboardingTestBase):
    def setUp(self):
        super().setUp()
        self.a = self._employee(code="BLK-A", started=date.today() - timedelta(days=30))
        self.b = self._employee(code="BLK-B", started=date.today() - timedelta(days=30))
        self._post_edit(self.hr, self.a, {"designation": "Lead A"})
        self._post_edit(self.hr, self.b, {"designation": "Lead B"})
        self.ra = EmployeeChangeRequest.objects.get(employee=self.a)
        self.rb = EmployeeChangeRequest.objects.get(employee=self.b)

    def _bulk(self, client, decision, ids, note=""):
        return client.post(reverse("employee_change_requests_bulk"),
                           {"decision": decision, "ids": ids, "note": note}, follow=True)

    def test_list_offers_checkboxes_to_approvers_only(self):
        self.assertContains(self.admin.client.get(reverse("employee_change_requests")), 'id="selectAllRequests"')
        self.assertNotContains(self.hr.client.get(reverse("employee_change_requests")), 'id="selectAllRequests"')

    def test_approve_selected(self):
        resp = self._bulk(self.admin.client, "approve", [self.ra.pk, self.rb.pk], "bulk ok")
        self.assertContains(resp, "2 change requests approved and applied.")
        self.a.refresh_from_db(); self.b.refresh_from_db()
        self.assertEqual((self.a.designation, self.b.designation), ("Lead A", "Lead B"))
        self.assertEqual(set(EmployeeChangeRequest.objects.values_list("status", "decision_note")),
                         {("approved", "bulk ok")})

    def test_reject_selected(self):
        self._bulk(self.admin.client, "reject", [self.ra.pk])
        self.ra.refresh_from_db(); self.rb.refresh_from_db()
        self.assertEqual((self.ra.status, self.rb.status), ("rejected", "pending"))
        self.a.refresh_from_db()
        self.assertEqual(self.a.designation, "Dev")

    def test_already_decided_requests_are_left_alone(self):
        self._bulk(self.admin.client, "reject", [self.ra.pk])
        resp = self._bulk(self.admin.client, "approve", [self.ra.pk, self.rb.pk])
        self.assertContains(resp, "1 change request approved and applied.")
        self.assertContains(resp, "1 request was already decided")
        self.ra.refresh_from_db()
        self.assertEqual(self.ra.status, "rejected")

    def test_hr_cannot_bulk_decide(self):
        resp = self.hr.client.post(reverse("employee_change_requests_bulk"), {"decision": "approve", "ids": [self.ra.pk]})
        self.assertEqual(resp.status_code, 403)
        self.ra.refresh_from_db()
        self.assertEqual(self.ra.status, "pending")
