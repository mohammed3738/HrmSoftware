"""
Regression tests for the Roles & Permissions feature: the database-driven
permission matrix (Feature + RoleFeaturePermission) that replaced the
hardcoded @group_required(...) decorators across ~69 views.

Two layers of verification, deliberately independent of each other:

1. test_seed_matches_hand_written_golden_table — a hand-typed copy of what
   access SHOULD be for every (feature, action) pair, written fresh here
   rather than imported from website/permissions_registry.py, checked
   against has_feature_permission(). This catches a transcription error
   between the registry and what actually got seeded into the DB by
   migration 0019 -- it is NOT just re-checking the seed data against
   itself, since it never imports SEED_GRANTS.

2. RolesPermissionsEndToEndTest — real HTTP requests through real URLs for
   a representative view per category, proving the @feature_required(...)
   decorator wiring itself works, including the two cases explicitly
   verified during design to have genuinely different access than their
   neighbors (create_company vs create_branchs; admin_dashboard excluding
   Manager) and superuser/staff bypass.

Run with: python manage.py test website.tests.test_roles_permissions
"""
from datetime import date

from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse

from website.models import Company, Employee, Feature
from website.utils.permissions import has_feature_permission


# Hand-typed independently of website/permissions_registry.py's SEED_GRANTS.
# {(feature_key, action): frozenset of group names that should have access}
GOLDEN_TABLE = {
    ("employee_records", "view"): {"Admin", "HR"},
    ("employee_records", "edit"): {"Admin", "HR"},
    ("offboarding", "edit"): {"Admin", "HR"},

    ("company_management", "view"): {"Admin", "HR"},
    ("company_management", "edit"): {"Admin"},
    ("branch_management", "view"): {"Admin", "HR"},
    ("branch_management", "edit"): {"Admin", "HR"},
    ("holiday_calendar", "edit"): {"Admin", "HR"},

    ("attendance_data", "edit"): {"Admin", "HR"},
    ("attendance_review", "view"): {"Admin", "HR", "Manager"},
    ("attendance_review", "edit"): {"Admin", "HR", "Manager"},
    ("shift_roster", "view"): {"Admin", "HR", "Manager"},
    ("shift_roster", "edit"): {"Admin", "HR", "Manager"},
    ("attendance_corrections", "view"): {"Admin", "HR", "Manager"},
    ("attendance_corrections", "approve"): {"Admin", "HR", "Manager"},

    ("leave_management", "view"): {"Admin", "HR"},
    ("leave_management", "edit"): {"Admin", "HR"},
    ("leave_management", "approve"): {"Admin", "HR", "Manager"},
    ("comp_off", "view"): {"Admin", "HR", "Manager"},
    ("comp_off", "approve"): {"Admin", "HR", "Manager"},

    ("salary_structure", "view"): {"Admin", "HR", "Manager"},
    ("salary_structure", "edit"): {"Admin", "HR"},
    ("payroll", "edit"): {"Admin", "HR"},
    ("advances", "view"): {"Admin", "HR"},
    ("advances", "edit"): {"Admin", "HR"},

    ("company_settings_broadcast", "edit"): {"Admin"},
    ("user_accounts", "edit"): {"Admin"},
    ("admin_dashboard", "view"): {"Admin", "HR"},
}

ALL_GROUPS = ("Admin", "HR", "Manager", "Employee")


class SeedParityTest(TestCase):
    """Layer 1: the seeded RoleFeaturePermission rows (created by migration
    0019 during test-DB setup) must exactly match GOLDEN_TABLE, for every
    group, not just the groups expected to be granted."""

    def setUp(self):
        self.users = {}
        for name in ALL_GROUPS:
            group = Group.objects.get(name=name)
            user = User.objects.create_user(username=f"golden_{name.lower()}", password="pass12345")
            user.groups.add(group)
            self.users[name] = user

    def test_seed_matches_hand_written_golden_table(self):
        mismatches = []
        for (feature_key, action), expected_groups in GOLDEN_TABLE.items():
            for group_name in ALL_GROUPS:
                user = self.users[group_name]
                actual = has_feature_permission(user, feature_key, action)
                expected = group_name in expected_groups
                if actual != expected:
                    mismatches.append(
                        f"{feature_key}/{action} for {group_name}: expected {expected}, got {actual}"
                    )
        self.assertEqual(mismatches, [], "\n".join(mismatches))


class RolesPermissionsEndToEndTest(TestCase):
    """Layer 2: real requests through real URLs, proving the
    @feature_required(...) decorator wiring on the actual view functions
    works, not just the permission-check function in isolation."""

    def setUp(self):
        self.company = Company.objects.create(
            short_name="RPT", name="Roles Perm Test Co", phone="1", email="rpt@test.com", address="Addr",
        )

        def make_user_in_group(group_name, username):
            user = User.objects.create_user(username=username, password="pass12345")
            if group_name:
                user.groups.add(Group.objects.get(name=group_name))
            return user

        self.admin_user = make_user_in_group("Admin", "e2e_admin")
        self.hr_user = make_user_in_group("HR", "e2e_hr")
        self.manager_user = make_user_in_group("Manager", "e2e_manager")
        self.employee_user = make_user_in_group("Employee", "e2e_employee")
        self.superuser = User.objects.create_superuser("e2e_super", "super@test.com", "pass12345")

    def _client_as(self, user):
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return client

    def test_create_company_admin_only_not_hr(self):
        # Verified divergent case: company_management edit = Admin only,
        # unlike branch_management edit (Admin, HR) right next to it.
        url = reverse("create-company")
        self.assertNotEqual(self._client_as(self.admin_user).get(url).status_code, 403)
        self.assertEqual(self._client_as(self.hr_user).get(url).status_code, 403)
        self.assertEqual(self._client_as(self.manager_user).get(url).status_code, 403)
        self.assertEqual(self._client_as(self.employee_user).get(url).status_code, 403)

    def test_create_branch_admin_and_hr(self):
        url = reverse("create-branch")
        self.assertNotEqual(self._client_as(self.admin_user).get(url).status_code, 403)
        self.assertNotEqual(self._client_as(self.hr_user).get(url).status_code, 403)
        self.assertEqual(self._client_as(self.manager_user).get(url).status_code, 403)

    def test_admin_dashboard_excludes_manager(self):
        # Verified divergent case: admin_dashboard view = Admin, HR --
        # Manager is deliberately NOT granted, unlike most Attendance/Leave
        # approval features which do include Manager.
        url = reverse("admin-dashboard")
        self.assertNotEqual(self._client_as(self.admin_user).get(url).status_code, 403)
        self.assertNotEqual(self._client_as(self.hr_user).get(url).status_code, 403)
        self.assertEqual(self._client_as(self.manager_user).get(url).status_code, 403)

    def test_employee_create_admin_and_hr_not_manager(self):
        url = reverse("employee_create")
        self.assertNotEqual(self._client_as(self.admin_user).get(url).status_code, 403)
        self.assertNotEqual(self._client_as(self.hr_user).get(url).status_code, 403)
        self.assertEqual(self._client_as(self.manager_user).get(url).status_code, 403)

    def test_bulk_approve_correction_includes_manager(self):
        url = reverse("bulk_approve_correction")
        self.assertNotEqual(self._client_as(self.manager_user).post(url, {}, content_type="application/json").status_code, 403)
        self.assertEqual(self._client_as(self.employee_user).post(url, {}, content_type="application/json").status_code, 403)

    def test_payroll_run_finalize_not_manager(self):
        # payroll feature has no Manager grant at all (edit = Admin, HR only).
        url = reverse("payroll-run-finalize", args=[1])
        self.assertEqual(self._client_as(self.manager_user).post(url).status_code, 403)
        self.assertEqual(self._client_as(self.employee_user).post(url).status_code, 403)

    def test_employee_with_no_role_denied_gated_page(self):
        url = reverse("create-company")
        self.assertEqual(self._client_as(self.employee_user).get(url).status_code, 403)

    def test_superuser_and_staff_bypass_every_feature_gate(self):
        url = reverse("create-company")
        self.assertNotEqual(self._client_as(self.superuser).get(url).status_code, 403)

        staff_user = User.objects.create_user(username="e2e_staff", password="pass12345", is_staff=True)
        self.assertNotEqual(self._client_as(staff_user).get(url).status_code, 403)

    def test_unauthenticated_user_redirected_not_403(self):
        client = Client()
        resp = client.get(reverse("create-company"))
        self.assertEqual(resp.status_code, 302)  # redirected to login, not a 403


class RolesPermissionsCrudTest(TestCase):
    """The Roles & Permissions page itself: role list, create/rename/delete
    role, saving the permission matrix, and reassigning a user's role."""

    def setUp(self):
        self.admin_user = User.objects.create_user(username="crud_admin", password="pass12345")
        self.admin_user.groups.add(Group.objects.get(name="Admin"))
        self.hr_user = User.objects.create_user(username="crud_hr", password="pass12345")
        self.hr_user.groups.add(Group.objects.get(name="HR"))

        self.client = Client()
        self.client.force_login(self.admin_user, backend="django.contrib.auth.backends.ModelBackend")

        self.company = Company.objects.create(
            short_name="RPC", name="Roles Perm Crud Co", phone="1", email="rpc@test.com", address="Addr",
        )
        self.employee = Employee.objects.create(
            company=self.company, user=self.hr_user, salutation="Mr", first_name="Crud", last_name="Tester",
            father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email="crud@test.com", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890", employee_code="RPC001",
            designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Crud",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
            force_password_change=False,  # otherwise ForcePasswordChangeMiddleware
                                           # redirects every request for this user
                                           # to /change-password/ before the view's
                                           # own permission check even runs
        )

    def test_hub_page_loads_for_admin(self):
        resp = self.client.get(reverse("roles-permissions-hub"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Roles &amp; Permissions")

    def test_hub_page_denied_for_hr(self):
        client = Client()
        client.force_login(self.hr_user, backend="django.contrib.auth.backends.ModelBackend")
        resp = client.get(reverse("roles-permissions-hub"))
        self.assertEqual(resp.status_code, 403)

    def test_create_role_creates_group_with_full_permission_rows(self):
        resp = self.client.post(reverse("create-role"), {"name": "Payroll Only"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        group = Group.objects.get(id=data["role_id"])
        self.assertEqual(group.name, "Payroll Only")
        # every active feature should have gotten a (default all-False) row
        self.assertEqual(group.feature_permissions.count(), Feature.objects.filter(is_active=True).count())

    def test_create_role_rejects_duplicate_name(self):
        resp = self.client.post(reverse("create-role"), {"name": "Admin"})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])

    def test_rename_role_blocked_for_system_role(self):
        admin_group = Group.objects.get(name="Admin")
        resp = self.client.post(reverse("rename-role", args=[admin_group.id]), {"name": "Super Admin"})
        self.assertEqual(resp.status_code, 400)
        admin_group.refresh_from_db()
        self.assertEqual(admin_group.name, "Admin")

    def test_rename_role_works_for_custom_role(self):
        custom = Group.objects.create(name="Custom Role")
        resp = self.client.post(reverse("rename-role", args=[custom.id]), {"name": "Renamed Role"})
        self.assertEqual(resp.status_code, 200)
        custom.refresh_from_db()
        self.assertEqual(custom.name, "Renamed Role")

    def test_delete_role_blocked_for_system_role(self):
        hr_group = Group.objects.get(name="HR")
        resp = self.client.post(reverse("delete-role", args=[hr_group.id]))
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(Group.objects.filter(name="HR").exists())

    def test_delete_role_blocked_when_users_assigned(self):
        custom = Group.objects.create(name="Has Users")
        self.hr_user.groups.add(custom)
        resp = self.client.post(reverse("delete-role", args=[custom.id]))
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(Group.objects.filter(name="Has Users").exists())

    def test_delete_role_works_when_no_users_assigned(self):
        custom = Group.objects.create(name="Empty Role")
        resp = self.client.post(reverse("delete-role", args=[custom.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Group.objects.filter(name="Empty Role").exists())

    def test_save_role_permissions_updates_matrix_and_enforcement(self):
        custom = Group.objects.create(name="Matrix Test Role")
        feature = Feature.objects.get(key="payroll")
        probe_user = User.objects.create_user(username="probe_matrix_test", password="x")
        probe_user.groups.add(custom)

        # Grant payroll edit to the new role.
        payload = {"role_id": custom.id, f"can_edit_{feature.id}": "on"}
        resp = self.client.post(reverse("save-role-permissions"), payload)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(has_feature_permission(probe_user, "payroll", "edit"))

        # Revoke it again (no can_edit_<id> key sent at all this time).
        resp = self.client.post(reverse("save-role-permissions"), {"role_id": custom.id})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(has_feature_permission(probe_user, "payroll", "edit"))

    def test_reassign_user_role_changes_group(self):
        manager_group = Group.objects.get(name="Manager")
        resp = self.client.post(reverse("reassign-user-role"), {
            "employee_id": self.employee.id, "role_id": manager_group.id,
        })
        self.assertEqual(resp.status_code, 200)
        self.hr_user.refresh_from_db()
        self.assertEqual(list(self.hr_user.groups.values_list("name", flat=True)), ["Manager"])

    def test_reassign_user_role_denied_for_hr(self):
        client = Client()
        client.force_login(self.hr_user, backend="django.contrib.auth.backends.ModelBackend")
        manager_group = Group.objects.get(name="Manager")
        resp = client.post(reverse("reassign-user-role"), {
            "employee_id": self.employee.id, "role_id": manager_group.id,
        })
        self.assertEqual(resp.status_code, 403)
