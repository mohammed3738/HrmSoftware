"""
HR may edit employee details, but may neither delete (archive) employees nor
change anyone's login role.

Run with: python manage.py test website.tests.test_hr_employee_edit
"""
import json
from datetime import date

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import Company, Employee


class HrEmployeeEditTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="HR Edit Co", short_name="HREC")
        self.employee = Employee.objects.create(
            company=self.company, salutation="Mr", first_name="Edit", last_name="Me",
            father_name="F", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email="hre1@test.com", present_address="A",
            permanent_address="A", personal_mobile="1234567890", employee_code="HRE001",
            designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Edit",
            salary_account_number="1", ifsc_code="TEST0001234", emergency_contact_name1="J",
            emergency_contact_relation1="Spouse", emergency_contact_mobile1="0987654321", status="Active",
        )
        self.hr = self._user("hre_hr", "HR")
        self.admin = self._user("hre_admin", "Admin")

    def _user(self, username, role):
        user = User.objects.create_user(username=username, password="pass12345")
        user.groups.add(Group.objects.get(name=role))
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        user.client = client
        return user

    def _bulk(self, user, **payload):
        return user.client.post(
            reverse("bulk-employee-action"),
            data=json.dumps({"employee_ids": [self.employee.id], **payload}),
            content_type="application/json",
        )

    def test_hr_can_open_edit_page_without_role_field(self):
        resp = self.hr.client.get(reverse("employee_edit", args=[self.employee.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'name="employee_group"')
        self.assertNotContains(resp, 'id="bulkRole"')

    def test_admin_still_sees_role_field(self):
        resp = self.admin.client.get(reverse("employee_edit", args=[self.employee.id]))
        self.assertContains(resp, 'name="employee_group"')

    def test_hr_cannot_archive(self):
        resp = self.hr.client.post(reverse("delete_employee", args=[self.employee.id]))
        self.assertEqual(resp.status_code, 403)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, "Active")

    def test_admin_can_archive(self):
        self.admin.client.post(reverse("delete_employee", args=[self.employee.id]))
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, "Archived")

    def test_hr_bulk_status_allowed_but_role_change_refused(self):
        self.assertEqual(self._bulk(self.hr, status="Pending").status_code, 200)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, "Pending")

        resp = self._bulk(self.hr, role="Admin")
        self.assertEqual(resp.status_code, 403)
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.user and self.employee.user.groups.filter(name="Admin").exists())

    def test_admin_bulk_role_change_allowed(self):
        self.assertEqual(self._bulk(self.admin, role="HR").status_code, 200)
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.user.groups.filter(name="HR").exists())
