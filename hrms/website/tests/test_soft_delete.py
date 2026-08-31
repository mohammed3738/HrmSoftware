"""
Regression tests for the soft-delete (archive/restore) refactor: "Delete"
buttons across the app now archive a record (flip is_active / status) via
the existing view instead of calling .delete(), and a generic restore_record
view flips it back. Covers one representative model per pattern (Branch --
plain boolean field; Company -- string status field; Employee -- status
field with a pre-existing business-meaningful third value; SalaryIncrement
-- a model with an existing guard that must still block archiving the same
way it used to block deleting).

Run with: python manage.py test website.tests.test_soft_delete
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse

from website.models import (
    AuditLog, Branch, Company, Employee, Holiday, HolidayType, HolidayCalendar,
    SalaryIncrement,
)


class SoftDeleteHelperMixin:
    def make_admin(self, username="sd_admin"):
        user = User.objects.create_user(username=username, password="pass12345")
        user.groups.add(Group.objects.get(name="Admin"))
        return user

    def make_employee(self, company, code, branch=None):
        employee = Employee.objects.create(
            company=company, branch=branch, salutation="Mr", first_name="Soft", last_name=code,
            father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email=f"{code}@test.com", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890", employee_code=code,
            designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Soft",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
        )
        employee.force_password_change = False
        employee.save(update_fields=["force_password_change"])
        return employee


class BranchSoftDeleteTest(SoftDeleteHelperMixin, TestCase):
    def setUp(self):
        self.admin = self.make_admin("branch_admin")
        self.client = Client()
        self.client.login(username="branch_admin", password="pass12345")
        self.branch = Branch.objects.create(branch_name="Test Branch", branch_address="Addr")

    def test_archive_flips_is_active_not_deletes(self):
        resp = self.client.post(reverse("delete_branch", args=[self.branch.id]))
        self.assertEqual(resp.status_code, 302)
        self.branch.refresh_from_db()
        self.assertFalse(self.branch.is_active)
        self.assertTrue(Branch.objects.filter(pk=self.branch.pk).exists())

    def test_archive_writes_audit_log(self):
        self.client.post(reverse("delete_branch", args=[self.branch.id]))
        row = AuditLog.objects.filter(action=AuditLog.Action.RECORD_ARCHIVED, target_type="Branch").first()
        self.assertIsNotNone(row)
        self.assertEqual(row.actor, self.admin)
        self.assertEqual(row.target_id, self.branch.id)

    def test_restore_flips_it_back(self):
        self.branch.is_active = False
        self.branch.save(update_fields=["is_active"])
        resp = self.client.post(reverse("restore-record", args=["branch", self.branch.id]))
        self.assertEqual(resp.status_code, 302)
        self.branch.refresh_from_db()
        self.assertTrue(self.branch.is_active)
        row = AuditLog.objects.filter(action=AuditLog.Action.RECORD_RESTORED, target_type="Branch").first()
        self.assertIsNotNone(row)

    def test_manager_cannot_archive_branch(self):
        manager = User.objects.create_user(username="branch_mgr", password="pass12345")
        manager.groups.add(Group.objects.get(name="Manager"))
        client = Client()
        client.login(username="branch_mgr", password="pass12345")
        resp = client.post(reverse("delete_branch", args=[self.branch.id]))
        self.assertEqual(resp.status_code, 403)
        self.branch.refresh_from_db()
        self.assertTrue(self.branch.is_active)


class CompanySoftDeleteTest(SoftDeleteHelperMixin, TestCase):
    def setUp(self):
        self.admin = self.make_admin("company_admin")
        self.client = Client()
        self.client.login(username="company_admin", password="pass12345")
        self.company = Company.objects.create(
            short_name="SDC", name="Soft Delete Co", phone="1", email="sdc@test.com", address="Addr",
        )

    def test_archive_sets_status_inactive_not_deletes(self):
        resp = self.client.post(reverse("delete_company", args=[self.company.id]))
        self.assertEqual(resp.status_code, 302)
        self.company.refresh_from_db()
        self.assertEqual(self.company.status, "inactive")
        self.assertTrue(Company.objects.filter(pk=self.company.pk).exists())

    def test_restore_sets_status_active(self):
        self.company.status = "inactive"
        self.company.save(update_fields=["status"])
        resp = self.client.post(reverse("restore-record", args=["company", self.company.id]))
        self.assertEqual(resp.status_code, 302)
        self.company.refresh_from_db()
        self.assertEqual(self.company.status, "active")


class EmployeeSoftDeleteTest(SoftDeleteHelperMixin, TestCase):
    def setUp(self):
        self.admin = self.make_admin("emp_admin")
        self.client = Client()
        self.client.login(username="emp_admin", password="pass12345")
        self.company = Company.objects.create(
            short_name="ESD", name="Employee Soft Delete Co", phone="1", email="esd@test.com", address="Addr",
        )
        self.employee = self.make_employee(self.company, "SDEMP1")

    def test_archive_sets_status_archived_distinct_from_left(self):
        resp = self.client.post(reverse("delete_employee", args=[self.employee.id]))
        self.assertEqual(resp.status_code, 302)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, "Archived")
        self.assertNotEqual(self.employee.status, "Left")
        self.assertTrue(Employee.objects.filter(pk=self.employee.pk).exists())

    def test_archiving_does_not_cascade_delete_related_records(self):
        # The whole point of this refactor: archiving an employee must NOT
        # cascade-destroy their salary/attendance/payroll history the way
        # employee.delete() used to.
        from website.models import SalaryMaster
        SalaryMaster.objects.create(employee=self.employee, is_active=True, gross_ctc_pm=Decimal("50000"))
        self.client.post(reverse("delete_employee", args=[self.employee.id]))
        self.assertTrue(SalaryMaster.objects.filter(employee=self.employee).exists())

    def test_restore_sets_status_active(self):
        self.employee.status = "Archived"
        self.employee.save(update_fields=["status"])
        resp = self.client.post(reverse("restore-record", args=["employee", self.employee.id]))
        self.assertEqual(resp.status_code, 302)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, "Active")

    def test_employee_form_excludes_archived_branch_but_keeps_existing_reference(self):
        from website.forms import EmployeeForm
        active_branch = Branch.objects.create(branch_name="Active Branch")
        archived_branch = Branch.objects.create(branch_name="Archived Branch", is_active=False)

        # A brand new form must not offer the archived branch as a choice.
        form = EmployeeForm()
        branch_ids = set(form.fields['branch'].queryset.values_list('id', flat=True))
        self.assertIn(active_branch.id, branch_ids)
        self.assertNotIn(archived_branch.id, branch_ids)

        # But an employee already pointing at the now-archived branch must
        # keep it selectable, so editing them doesn't silently blank it out.
        self.employee.branch = archived_branch
        self.employee.save(update_fields=["branch"])
        edit_form = EmployeeForm(instance=self.employee)
        edit_branch_ids = set(edit_form.fields['branch'].queryset.values_list('id', flat=True))
        self.assertIn(archived_branch.id, edit_branch_ids)


class SalaryIncrementSoftDeleteTest(SoftDeleteHelperMixin, TestCase):
    """Confirms the pre-existing is_processed guard still blocks archiving
    the same way it used to block deleting."""

    def setUp(self):
        self.admin = self.make_admin("inc_admin")
        self.client = Client()
        self.client.login(username="inc_admin", password="pass12345")
        self.company = Company.objects.create(
            short_name="INC", name="Increment Co", phone="1", email="inc@test.com", address="Addr",
        )
        self.employee = self.make_employee(self.company, "SDEMP2")

    def test_unprocessed_increment_can_be_archived(self):
        inc = SalaryIncrement.objects.create(
            employee=self.employee, effective_date=date(2026, 1, 1), change_set={}, is_processed=False,
        )
        resp = self.client.post(reverse("delete_increment", args=[inc.id]))
        self.assertEqual(resp.status_code, 200)
        inc.refresh_from_db()
        self.assertFalse(inc.is_active)

    def test_processed_increment_cannot_be_archived(self):
        inc = SalaryIncrement.objects.create(
            employee=self.employee, effective_date=date(2026, 1, 1), change_set={}, is_processed=True,
        )
        resp = self.client.post(reverse("delete_increment", args=[inc.id]))
        self.assertEqual(resp.status_code, 400)
        inc.refresh_from_db()
        self.assertTrue(inc.is_active)


class HolidaySoftDeleteTest(SoftDeleteHelperMixin, TestCase):
    """Confirms the conditional unique constraint: an archived holiday must
    not block adding a new active holiday on the same date."""

    def setUp(self):
        self.admin = self.make_admin("hol_admin")
        self.client = Client()
        self.client.login(username="hol_admin", password="pass12345")
        self.branch = Branch.objects.create(branch_name="Holiday Branch")
        self.calendar = HolidayCalendar.objects.create(
            branch=self.branch, year=2026, name="2026 Calendar", created_by=self.admin,
        )
        self.holiday_type = HolidayType.objects.create(name="Test Type")

    def test_archived_holiday_frees_up_its_date_for_a_new_one(self):
        d = date(2026, 8, 15)
        h1 = Holiday.objects.create(
            holiday_calendar=self.calendar, holiday_date=d, name="Old Holiday",
            holiday_type=self.holiday_type, created_by=self.admin,
        )
        self.client.post(reverse("delete-holiday", args=[h1.id]))
        h1.refresh_from_db()
        self.assertFalse(h1.is_active)

        # Creating a second, active holiday on the same date must now succeed.
        h2 = Holiday.objects.create(
            holiday_calendar=self.calendar, holiday_date=d, name="New Holiday",
            holiday_type=self.holiday_type, created_by=self.admin,
        )
        self.assertTrue(h2.is_active)
        self.assertEqual(Holiday.objects.filter(holiday_date=d).count(), 2)
