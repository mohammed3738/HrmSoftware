"""
Regression tests for the Audit Trail feature: the log_audit()/diff()
helpers, company-scoped visibility on the Audit Log page, Admin/HR-only
permission gating, and a representative instrumentation smoke-test per
call-site pattern (shared-helper diff, direct model action, shared
approval helper).

Run with: python manage.py test website.tests.test_audit_log
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse

from website.models import (
    AuditLog, Company, Employee, Feature, LeaveApplication, PayrollRecord,
    PayrollRun, PayrollSettings, RoleFeaturePermission,
)
from website.services.audit import diff, log_audit, snapshot


class AuditLogHelperTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="AUD", name="Audit Co", phone="1", email="aud@test.com", address="Addr",
        )

    def make_employee(self, code="AUDEMP1"):
        return Employee.objects.create(
            company=self.company, salutation="Mr", first_name="Audit", last_name=code,
            father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email=f"{code}@test.com", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890", employee_code=code,
            designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Audit",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
        )

    def test_log_audit_populates_fields_from_target_and_infers_employee_company(self):
        employee = self.make_employee()
        admin = User.objects.create_user(username="aud_admin", password="pass12345")

        log_audit(admin, AuditLog.Action.EMPLOYEE_UPDATED, employee, summary="Test summary")

        row = AuditLog.objects.get()
        self.assertEqual(row.actor, admin)
        self.assertEqual(row.action, AuditLog.Action.EMPLOYEE_UPDATED)
        self.assertEqual(row.target_type, "Employee")
        self.assertEqual(row.target_id, employee.pk)
        self.assertEqual(row.target_repr, str(employee))
        self.assertEqual(row.employee, employee)
        self.assertEqual(row.company, self.company)
        self.assertEqual(row.summary, "Test summary")
        self.assertEqual(row.changes, {})

    def test_log_audit_anonymous_actor_stored_as_none(self):
        employee = self.make_employee()
        from django.contrib.auth.models import AnonymousUser
        log_audit(AnonymousUser(), AuditLog.Action.EMPLOYEE_UPDATED, employee, summary="Anon test")
        row = AuditLog.objects.get()
        self.assertIsNone(row.actor)

    def test_diff_ignores_decimal_and_none_noise(self):
        class Dummy:
            amount = Decimal("0.00")
            note = None

        before = snapshot(Dummy(), ("amount", "note"))
        d = Dummy()
        d.amount = Decimal("0")  # numerically equal, differently represented
        d.note = None
        changes = diff(before, d, ("amount", "note"))
        self.assertEqual(changes, {})

    def test_diff_reports_real_changes(self):
        class Dummy:
            amount = Decimal("100.00")

        before = snapshot(Dummy(), ("amount",))
        d = Dummy()
        d.amount = Decimal("200.00")
        changes = diff(before, d, ("amount",))
        self.assertEqual(changes, {"amount": {"old": "100.00", "new": "200.00"}})


class AuditLogVisibilityTest(TestCase):
    def setUp(self):
        self.company_a = Company.objects.create(
            short_name="AVA", name="Audit Vis A", phone="1", email="ava@test.com", address="Addr",
        )
        self.company_b = Company.objects.create(
            short_name="AVB", name="Audit Vis B", phone="1", email="avb@test.com", address="Addr",
        )

    def make_employee(self, company, code, group_name="Employee"):
        employee = Employee.objects.create(
            company=company, salutation="Mr", first_name="Vis", last_name=code,
            father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email=f"{code}@test.com", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890", employee_code=code,
            designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Vis",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
        )
        employee.force_password_change = False
        employee.save(update_fields=["force_password_change"])
        employee.user.groups.clear()
        employee.user.groups.add(Group.objects.get(name=group_name))
        return employee

    def test_hr_sees_only_own_company_rows(self):
        emp_a = self.make_employee(self.company_a, "AVAEMP1")
        emp_b = self.make_employee(self.company_b, "AVBEMP1")
        log_audit(None, AuditLog.Action.EMPLOYEE_UPDATED, emp_a, summary="A row")
        log_audit(None, AuditLog.Action.EMPLOYEE_UPDATED, emp_b, summary="B row")

        hr = self.make_employee(self.company_a, "AVAHR1", group_name="HR")
        client = Client()
        client.login(username=hr.user.username, password="Temp@123")
        resp = client.get(reverse("audit-log"))

        summaries = {row.summary for row in resp.context["page_obj"]}
        self.assertIn("A row", summaries)
        self.assertNotIn("B row", summaries)

    def test_global_admin_sees_all_rows(self):
        emp_a = self.make_employee(self.company_a, "AVAEMP2")
        emp_b = self.make_employee(self.company_b, "AVBEMP2")
        log_audit(None, AuditLog.Action.EMPLOYEE_UPDATED, emp_a, summary="A row 2")
        log_audit(None, AuditLog.Action.EMPLOYEE_UPDATED, emp_b, summary="B row 2")

        admin = User.objects.create_user(username="avis_admin", password="pass12345")
        admin.groups.add(Group.objects.get(name="Admin"))
        client = Client()
        client.login(username="avis_admin", password="pass12345")
        resp = client.get(reverse("audit-log"))

        summaries = {row.summary for row in resp.context["page_obj"]}
        self.assertIn("A row 2", summaries)
        self.assertIn("B row 2", summaries)


class AuditLogPermissionTest(TestCase):
    def make_user(self, username, group_name):
        user = User.objects.create_user(username=username, password="pass12345")
        user.groups.add(Group.objects.get(name=group_name))
        return user

    def test_admin_can_view(self):
        self.make_user("aperm_admin", "Admin")
        client = Client()
        client.login(username="aperm_admin", password="pass12345")
        resp = client.get(reverse("audit-log"))
        self.assertEqual(resp.status_code, 200)

    def test_hr_can_view(self):
        self.make_user("aperm_hr", "HR")
        client = Client()
        client.login(username="aperm_hr", password="pass12345")
        resp = client.get(reverse("audit-log"))
        self.assertEqual(resp.status_code, 200)

    def test_manager_cannot_view(self):
        self.make_user("aperm_mgr", "Manager")
        client = Client()
        client.login(username="aperm_mgr", password="pass12345")
        resp = client.get(reverse("audit-log"))
        self.assertEqual(resp.status_code, 403)

    def test_employee_cannot_view(self):
        self.make_user("aperm_emp", "Employee")
        client = Client()
        client.login(username="aperm_emp", password="pass12345")
        resp = client.get(reverse("audit-log"))
        self.assertEqual(resp.status_code, 403)


class AuditLogInstrumentationTest(TestCase):
    """One representative call site per instrumentation pattern: a
    shared-helper aggregated diff (save_role_permissions), a direct
    model action (payroll_run_finalize), and a shared approval helper
    used by both single and bulk endpoints (approve_leave)."""

    def setUp(self):
        self.company = Company.objects.create(
            short_name="AIT", name="Audit Instr Co", phone="1", email="ait@test.com", address="Addr",
        )
        self.admin = User.objects.create_user(username="ait_admin", password="pass12345")
        self.admin.groups.add(Group.objects.get(name="Admin"))
        self.client = Client()
        self.client.login(username="ait_admin", password="pass12345")

    def test_save_role_permissions_writes_one_row_with_diff(self):
        role = Group.objects.create(name="Audit Test Role")
        feature = Feature.objects.get(key="salary_structure")
        RoleFeaturePermission.objects.get_or_create(role=role, feature=feature)

        resp = self.client.post(reverse("save-role-permissions"), {
            "role_id": role.id,
            f"can_view_{feature.id}": "on",
        })
        self.assertEqual(resp.status_code, 200)

        row = AuditLog.objects.filter(action=AuditLog.Action.ROLE_PERMISSIONS_UPDATED).first()
        self.assertIsNotNone(row)
        self.assertEqual(row.actor, self.admin)
        self.assertEqual(row.target_type, "Group")
        self.assertEqual(row.target_id, role.id)
        self.assertIn("salary_structure", row.changes)
        self.assertTrue(row.changes["salary_structure"]["can_view"]["new"])

    def test_payroll_run_finalize_writes_row_with_correct_actor(self):
        run = PayrollRun.objects.create(
            company=self.company, month=date(2026, 8, 1),
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 31),
        )
        resp = self.client.post(reverse("payroll-run-finalize", args=[run.id]))
        self.assertEqual(resp.status_code, 200)

        row = AuditLog.objects.filter(action=AuditLog.Action.PAYROLL_FINALIZED).first()
        self.assertIsNotNone(row)
        self.assertEqual(row.actor, self.admin)
        self.assertEqual(row.target_type, "PayrollRun")
        self.assertEqual(row.target_id, run.id)
        self.assertEqual(row.company, self.company)

    def test_approve_leave_writes_row_with_correct_employee(self):
        employee = Employee.objects.create(
            company=self.company, salutation="Mr", first_name="Leave", last_name="Emp",
            father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email="leaveemp@test.com", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890", employee_code="AITLEAVE1",
            designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Leave",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
        )
        leave = LeaveApplication.objects.create(
            employee=employee, leave_type="CL", start_date=date(2026, 8, 10), end_date=date(2026, 8, 10),
            reason="Personal",
        )
        resp = self.client.post(reverse("approve_leave", args=[leave.id]))
        self.assertEqual(resp.status_code, 200)

        row = AuditLog.objects.filter(action=AuditLog.Action.LEAVE_APPROVED).first()
        self.assertIsNotNone(row)
        self.assertEqual(row.employee, employee)
        self.assertEqual(row.actor, self.admin)
