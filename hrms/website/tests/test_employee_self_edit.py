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
