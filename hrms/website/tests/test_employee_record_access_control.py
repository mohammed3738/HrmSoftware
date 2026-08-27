"""
Regression tests for the ownership check added to employee_detail,
employee_attendance_detail, and salary_slip_view. These views used to have
no access control beyond @login_required: any authenticated user could view
any employee's profile, attendance, or payslip just by editing the URL's
numeric ID. can_access_employee_record() now allows: the employee viewing
their own record, superuser/staff, or a role with the matching feature
permission (so HR/Admin/Manager keep their existing cross-employee access).

Run with: python manage.py test website.tests.test_employee_record_access_control
"""
from datetime import date

from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse

from website.models import Company, Employee, PayrollRun, PayrollRecord


class EmployeeRecordAccessControlTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="EAC", name="Emp Access Control Co", phone="1", email="eac@test.com", address="Addr",
        )

        def make_employee(code, first_name, user=None):
            return Employee.objects.create(
                company=self.company, user=user, salutation="Mr", first_name=first_name, last_name="Doe",
                father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
                place_of_birth="City", personal_email=f"{code}@test.com", present_address="Addr",
                permanent_address="Addr", personal_mobile="1234567890", employee_code=code,
                designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), location="City",
                pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank=first_name,
                salary_account_number="1234567890", ifsc_code="TEST0001234",
                emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
                emergency_contact_mobile1="0987654321", status="Active", force_password_change=False,
            )

        self.self_user = User.objects.create_user(username="eac_self", password="pass12345")
        self.self_user.groups.add(Group.objects.get(name="Employee"))
        self.self_employee = make_employee("EAC001", "Self", user=self.self_user)

        self.other_employee = make_employee("EAC002", "Other")

        self.hr_user = User.objects.create_user(username="eac_hr", password="pass12345")
        self.hr_user.groups.add(Group.objects.get(name="HR"))

        self.manager_user = User.objects.create_user(username="eac_manager", password="pass12345")
        self.manager_user.groups.add(Group.objects.get(name="Manager"))

        self.other_employee_user = User.objects.create_user(username="eac_other_login", password="pass12345")
        self.other_employee_user.groups.add(Group.objects.get(name="Employee"))

    def _client_as(self, user):
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return client

    # ── employee_detail ──────────────────────────────────────────────────
    def test_employee_can_view_own_detail_page(self):
        resp = self._client_as(self.self_user).get(reverse("employee_detail", args=[self.self_employee.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_employee_cannot_view_other_employees_detail_page(self):
        resp = self._client_as(self.self_user).get(reverse("employee_detail", args=[self.other_employee.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_hr_can_view_any_employee_detail_page(self):
        resp = self._client_as(self.hr_user).get(reverse("employee_detail", args=[self.other_employee.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_manager_cannot_view_employee_detail_page(self):
        # employee_records view was never granted to Manager, before or after this fix.
        resp = self._client_as(self.manager_user).get(reverse("employee_detail", args=[self.other_employee.pk]))
        self.assertEqual(resp.status_code, 403)

    # ── employee_attendance_detail ───────────────────────────────────────
    def test_employee_can_view_own_attendance(self):
        resp = self._client_as(self.self_user).get(reverse("employee_attendance_detail", args=[self.self_employee.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_employee_cannot_view_other_employees_attendance(self):
        resp = self._client_as(self.self_user).get(reverse("employee_attendance_detail", args=[self.other_employee.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_manager_can_view_any_employees_attendance(self):
        # attendance_review view IS granted to Manager (unlike employee_records).
        resp = self._client_as(self.manager_user).get(reverse("employee_attendance_detail", args=[self.other_employee.pk]))
        self.assertEqual(resp.status_code, 200)

    # ── salary_slip_view ─────────────────────────────────────────────────
    def test_employee_can_view_own_payslip(self):
        run = PayrollRun.objects.create(
            company=self.company, month=date(2026, 1, 1), start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
        )
        record = PayrollRecord.objects.create(payroll=run, employee=self.self_employee, employee_code="EAC001")
        resp = self._client_as(self.self_user).get(reverse("salary-slip", args=[record.id]))
        self.assertEqual(resp.status_code, 200)

    def test_employee_cannot_view_other_employees_payslip(self):
        run = PayrollRun.objects.create(
            company=self.company, month=date(2026, 1, 1), start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
        )
        record = PayrollRecord.objects.create(payroll=run, employee=self.other_employee, employee_code="EAC002")
        resp = self._client_as(self.self_user).get(reverse("salary-slip", args=[record.id]))
        self.assertEqual(resp.status_code, 403)

    def test_hr_can_view_any_payslip(self):
        run = PayrollRun.objects.create(
            company=self.company, month=date(2026, 1, 1), start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
        )
        record = PayrollRecord.objects.create(payroll=run, employee=self.other_employee, employee_code="EAC002")
        resp = self._client_as(self.hr_user).get(reverse("salary-slip", args=[record.id]))
        self.assertEqual(resp.status_code, 200)

    def test_manager_cannot_view_others_payslip(self):
        # payroll edit was never granted to Manager, before or after this fix.
        run = PayrollRun.objects.create(
            company=self.company, month=date(2026, 1, 1), start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
        )
        record = PayrollRecord.objects.create(payroll=run, employee=self.other_employee, employee_code="EAC002")
        resp = self._client_as(self.manager_user).get(reverse("salary-slip", args=[record.id]))
        self.assertEqual(resp.status_code, 403)

    def test_superuser_bypasses_all_ownership_checks(self):
        superuser = User.objects.create_superuser("eac_super", "super@test.com", "pass12345")
        resp = self._client_as(superuser).get(reverse("employee_detail", args=[self.other_employee.pk]))
        self.assertEqual(resp.status_code, 200)
