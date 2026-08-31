"""
Regression test for the "Absent Today" list on the Admin/HR dashboard
(admin_dashboard view, rendered as d/f.html) -- shows employee code + name
for every employee marked Absent today, scoped to the viewing user's
company like the rest of that dashboard's KPIs.

Run with: python manage.py test website.tests.test_admin_dashboard_absentees
"""
from datetime import date

from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse

from website.models import Attendance, Branch, Company, Employee


class AdminDashboardAbsenteesTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="ADA", name="Admin Dashboard Absentees Co", phone="1", email="ada@test.com", address="Addr",
        )
        self.branch = Branch.objects.create(branch_name="HQ")

        self.admin = User.objects.create_user(username="ada_admin", password="pass12345")
        self.admin.groups.add(Group.objects.get(name="Admin"))
        self.client = Client()
        self.client.login(username="ada_admin", password="pass12345")

        self.present_employee = self._make_employee("ADA1", "Present", "Person")
        Attendance.objects.create(employee=self.present_employee, date=date.today(), status="Present", status_overridden=True)

        self.absent_employee = self._make_employee("ADA2", "Absent", "Person")
        Attendance.objects.create(employee=self.absent_employee, date=date.today(), status="Absent", status_overridden=True)

    def _make_employee(self, code, first_name, last_name):
        return Employee.objects.create(
            company=self.company, branch=self.branch, salutation="Mr", first_name=first_name, last_name=last_name,
            father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email=f"{code}@test.com", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890", employee_code=code,
            designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank=first_name,
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
        )

    def test_only_absent_employees_are_listed(self):
        resp = self.client.get(reverse("admin-dashboard"))
        self.assertEqual(resp.status_code, 200)
        codes = [a.employee.employee_code for a in resp.context["absent_employees_today"]]
        self.assertIn("ADA2", codes)
        self.assertNotIn("ADA1", codes)

    def test_absent_employee_name_and_code_available_for_display(self):
        resp = self.client.get(reverse("admin-dashboard"))
        row = resp.context["absent_employees_today"][0]
        self.assertEqual(row.employee.employee_code, "ADA2")
        self.assertEqual(row.employee.first_name, "Absent")
