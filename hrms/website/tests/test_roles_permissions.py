"""
Regression tests for the Roles & Permissions feature: the database-driven
permission matrix (Feature + RoleFeaturePermission) that replaced the
hardcoded @group_required(...) decorators across ~69 views.

The six roles are Super Admin, Admin, Payroll Officer, HR, HOD and Employee
(migration 0033 renamed the old "Manager" to HOD and added the other two).
The separations that actually matter, and are asserted below:

  * only Super Admin may change companies -- everyone else reads them;
  * running payroll is the Payroll Officer's job: Admin can read a run but
    not create, edit, recalculate or finalize one, and HR has no payroll
    access at all;
  * HR may add employees, salary structures and offboardings but not change
    existing ones -- the reason the `create` action exists at all -- and
    approves nothing;
  * HOD and Employee hold no company-wide grants. They read their own
    records, and a HOD approves for the people who report to them through
    the reporting line (see test_reporting_line.py), not through a blanket
    role grant.

Two layers of verification, deliberately independent of each other:

1. test_seed_matches_hand_written_golden_table — a hand-typed copy of what
   access SHOULD be for every (feature, action) pair, written fresh here
   rather than imported from website/permissions_registry.py, checked
   against has_feature_permission(). This catches a transcription error
   between the registry and what actually got seeded into the DB -- it is
   NOT just re-checking the seed data against itself, since it never
   imports SEED_GRANTS.

2. RolesPermissionsEndToEndTest — real HTTP requests through real URLs for
   a representative view per category, proving the decorator wiring itself
   works, including superuser/staff bypass.

Run with: python manage.py test website.tests.test_roles_permissions
"""
from datetime import date

from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse

from website.models import Company, Employee, Feature, RoleFeaturePermission
from website.utils.permissions import has_feature_permission


# Hand-typed independently of website/permissions_registry.py's SEED_GRANTS.
# {(feature_key, action): set of group names that should have access}
STAFF = {"Super Admin", "Admin", "Payroll Officer", "HR"}
NOT_HR = {"Super Admin", "Admin", "Payroll Officer"}

GOLDEN_TABLE = {
    # Employee lifecycle -- HR adds but cannot change.
    ("employee_records", "view"): STAFF,
    ("employee_records", "create"): STAFF,
    ("employee_records", "edit"): NOT_HR,
    ("department_management", "view"): STAFF,
    ("department_management", "edit"): STAFF,
    ("offboarding", "view"): STAFF,
    ("offboarding", "create"): STAFF,
    ("offboarding", "edit"): NOT_HR,

    # Organization setup -- only Super Admin may change companies.
    ("company_management", "view"): STAFF,
    ("company_management", "edit"): {"Super Admin"},
    ("branch_management", "view"): STAFF,
    ("branch_management", "edit"): STAFF,
    ("holiday_calendar", "edit"): STAFF,

    # Attendance & scheduling -- HR uploads and reads, doesn't correct.
    ("attendance_data", "edit"): STAFF,
    ("attendance_review", "view"): STAFF,
    ("attendance_review", "edit"): NOT_HR,
    ("shift_roster", "view"): STAFF,
    ("shift_roster", "edit"): STAFF,
    ("attendance_corrections", "view"): STAFF,
    ("attendance_corrections", "approve"): NOT_HR,

    # Leave & comp-off -- HR reads balances but approves nothing.
    ("leave_management", "view"): STAFF,
    ("leave_management", "edit"): NOT_HR,
    ("leave_management", "approve"): NOT_HR,
    ("comp_off", "view"): STAFF,
    ("comp_off", "approve"): NOT_HR,

    # Compensation -- HR drafts a structure; Admin cannot run payroll.
    ("salary_structure", "view"): STAFF,
    ("salary_structure", "create"): STAFF,
    ("salary_structure", "edit"): NOT_HR,
    ("payroll", "view"): NOT_HR,
    ("payroll", "edit"): {"Super Admin", "Payroll Officer"},
    # Advances are payroll's, not HR's. HR still reads their OWN advance --
    # that's self-service scoping on advance_list, not a grant.
    ("advances", "view"): NOT_HR,
    ("advances", "edit"): NOT_HR,

    # Administration
    ("company_settings_broadcast", "edit"): NOT_HR,
    ("user_accounts", "edit"): NOT_HR,
    ("admin_dashboard", "view"): STAFF,
    ("announcements", "view"): STAFF,
    ("announcements", "edit"): STAFF,
    ("audit_log", "view"): STAFF,
}

ALL_GROUPS = ("Super Admin", "Admin", "Payroll Officer", "HR", "HOD", "Employee")


class SeedParityTest(TestCase):
    """Layer 1: the seeded RoleFeaturePermission rows must exactly match
    GOLDEN_TABLE, for every group -- not just the groups expected to be
    granted."""

    def setUp(self):
        self.users = {}
        for name in ALL_GROUPS:
            group = Group.objects.get(name=name)
            user = User.objects.create_user(
                username=f"golden_{name.lower().replace(' ', '_')}", password="pass12345"
            )
            user.groups.add(group)
            self.users[name] = user

    def test_seed_matches_hand_written_golden_table(self):
        mismatches = []
        for (feature_key, action), expected_groups in GOLDEN_TABLE.items():
            for group_name in ALL_GROUPS:
                actual = has_feature_permission(self.users[group_name], feature_key, action)
                expected = group_name in expected_groups
                if actual != expected:
                    mismatches.append(
                        f"{feature_key}/{action} for {group_name}: expected {expected}, got {actual}"
                    )
        self.assertEqual(mismatches, [], "\n".join(mismatches))

    def test_self_service_roles_hold_no_company_wide_grants(self):
        """HOD and Employee read their own records and (for a HOD) approve
        through the reporting line. Any blanket grant here would hand them
        the whole company's data."""
        leaked = []
        for feature in Feature.objects.all():
            for action in ("view", "create", "edit", "approve"):
                for group_name in ("HOD", "Employee"):
                    if has_feature_permission(self.users[group_name], feature.key, action):
                        leaked.append(f"{group_name} has {feature.key}/{action}")
        self.assertEqual(leaked, [], "\n".join(leaked))

    def test_the_old_manager_role_is_gone(self):
        self.assertFalse(Group.objects.filter(name="Manager").exists())

    def test_every_role_in_the_structure_exists(self):
        for name in ALL_GROUPS:
            self.assertTrue(Group.objects.filter(name=name).exists(), name)


class RolesPermissionsEndToEndTest(TestCase):
    """Layer 2: real requests through real URLs, proving the decorator
    wiring on the actual view functions works."""

    def setUp(self):
        self.company = Company.objects.create(
            short_name="RPT", name="Roles Perm Test Co", phone="1", email="rpt@test.com", address="Addr",
        )

        def make_user_in_group(group_name, username):
            user = User.objects.create_user(username=username, password="pass12345")
            if group_name:
                user.groups.add(Group.objects.get(name=group_name))
            return user

        self.super_admin = make_user_in_group("Super Admin", "e2e_super_admin")
        self.admin_user = make_user_in_group("Admin", "e2e_admin")
        self.payroll_officer = make_user_in_group("Payroll Officer", "e2e_payroll")
        self.hr_user = make_user_in_group("HR", "e2e_hr")
        self.hod_user = make_user_in_group("HOD", "e2e_hod")
        self.employee_user = make_user_in_group("Employee", "e2e_employee")
        self.superuser = User.objects.create_superuser("e2e_super", "super@test.com", "pass12345")

    def _client_as(self, user):
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return client

    def _status(self, user, url):
        return self._client_as(user).get(url).status_code

    # ── companies: Super Admin alone may change them ──────────────────

    def test_everyone_on_staff_can_view_the_company_list(self):
        url = reverse("create-company")
        for user in (self.super_admin, self.admin_user, self.payroll_officer, self.hr_user):
            self.assertNotEqual(self._status(user, url), 403)
        self.assertEqual(self._status(self.hod_user, url), 403)
        self.assertEqual(self._status(self.employee_user, url), 403)

    def test_only_super_admin_can_actually_add_a_company(self):
        """The list page doubles as the add form, so the POST is what has to
        be restricted -- being able to open the page is not permission to
        create."""
        payload = {"short_name": "NEW", "name": "New Co", "address": "Addr",
                   "phone": "1", "email": "new@test.com", "status": "active"}
        url = reverse("create-company")
        for user in (self.admin_user, self.payroll_officer, self.hr_user):
            self.assertEqual(self._client_as(user).post(url, payload).status_code, 403)
        self.assertNotEqual(self._client_as(self.super_admin).post(url, payload).status_code, 403)
        self.assertTrue(Company.objects.filter(short_name="NEW").exists())

    # ── payroll: Admin reads, Payroll Officer runs ────────────────────

    def test_admin_can_view_payroll_but_not_create_a_run(self):
        self.assertNotEqual(self._status(self.admin_user, reverse("payroll-run-list")), 403)
        self.assertEqual(self._status(self.admin_user, reverse("payroll-run-create")), 403)

    def test_payroll_officer_can_create_a_run(self):
        self.assertNotEqual(self._status(self.payroll_officer, reverse("payroll-run-create")), 403)

    def test_admin_cannot_finalize_a_payroll_run(self):
        url = reverse("payroll-run-finalize", args=[1])
        self.assertEqual(self._client_as(self.admin_user).post(url).status_code, 403)
        self.assertNotEqual(self._client_as(self.payroll_officer).post(url).status_code, 403)

    def test_hr_has_no_payroll_access_at_all(self):
        """Not even read -- payroll sits entirely with the Payroll Officer."""
        self.assertEqual(self._status(self.hr_user, reverse("payroll-run-list")), 403)
        self.assertEqual(self._status(self.hr_user, reverse("payroll-run-create")), 403)
        self.assertEqual(
            self._client_as(self.hr_user).post(reverse("payroll-run-finalize", args=[1])).status_code, 403,
        )

    def test_hr_cannot_approve_anything(self):
        """HR administers people; sign-off belongs to Admin/Super Admin and
        to HODs through their reporting line."""
        for url in (
            reverse("bulk_approve_leave"),
            reverse("bulk_approve_compoff"),
            reverse("bulk_approve_correction"),
        ):
            resp = self._client_as(self.hr_user).post(url, {}, content_type="application/json")
            self.assertEqual(resp.status_code, 403, url)

    def test_hr_can_still_read_leave_balances(self):
        self.assertNotEqual(self._status(self.hr_user, reverse("leave_balance_report")), 403)

    def test_hr_can_read_every_employees_salary_structure(self):
        """HR drafts structures and reads them back -- their own and
        everyone's -- without being able to change one."""
        self.assertNotEqual(self._status(self.hr_user, reverse("salary_history")), 403)

    def test_hr_has_no_advances_grant(self):
        """HR can still reach their own advance (self-service scoping on
        advance_list), but holds no company-wide advances grant."""
        from website.utils.permissions import has_feature_permission
        self.assertFalse(has_feature_permission(self.hr_user, "advances", "view"))
        self.assertFalse(has_feature_permission(self.hr_user, "advances", "edit"))

    # ── HR: add but don't change ──────────────────────────────────────

    def test_hr_can_open_the_new_employee_form(self):
        self.assertNotEqual(self._status(self.hr_user, reverse("employee_create")), 403)

    def test_hr_cannot_open_an_existing_employee_for_editing(self):
        employee = Employee.objects.create(
            company=self.company, salutation="Mr", first_name="Ed", last_name="Itable",
            father_name="Father", gender="Male", date_of_birth=date(1990, 1, 1),
            personal_email="ed@test.com", personal_mobile="1234567890", employee_code="RPT001",
            designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), status="Active",
        )
        url = reverse("employee_edit", args=[employee.id])
        self.assertEqual(self._status(self.hr_user, url), 403)
        self.assertNotEqual(self._status(self.admin_user, url), 403)

    def test_hr_can_open_the_salary_structure_form(self):
        self.assertNotEqual(self._status(self.hr_user, reverse("create-salary")), 403)

    def test_hr_is_not_offered_the_salary_edit_link(self):
        """HR drafts new structures, so the page opens -- but the Edit
        affordance on an existing one must not be there to click."""
        resp = self._client_as(self.hr_user).get(reverse("create-salary"))
        self.assertFalse(resp.context["can_edit_salary"])
        # Targets the anchor's href -- the page also carries a JS comment
        # mentioning "?edit=".
        self.assertNotContains(resp, "/create-salary?edit=")

        admin_resp = self._client_as(self.admin_user).get(reverse("create-salary"))
        self.assertTrue(admin_resp.context["can_edit_salary"])

    def test_hr_cannot_change_an_existing_salary_structure(self):
        """A salary_id in the POST means an existing structure is being
        edited, which HR may not do even though they may draft new ones."""
        resp = self._client_as(self.hr_user).post(reverse("create-salary"), {
            "salary_id": "1", "employee": "1",
        })
        self.assertEqual(resp.status_code, 403)

    def test_edit_rights_satisfy_a_create_requirement(self):
        """Actions form a ladder -- a role holding `edit` never has to also
        be granted `create` for the same feature."""
        role = Group.objects.create(name="Editor Only")
        feature = Feature.objects.get(key="employee_records")
        RoleFeaturePermission.objects.create(role=role, feature=feature, can_edit=True)
        user = User.objects.create_user(username="ladder_editor", password="pass12345")
        user.groups.add(role)

        # Granted edit only, yet the add form (which requires create) opens.
        self.assertNotEqual(self._status(user, reverse("employee_create")), 403)

    def test_create_rights_do_not_satisfy_an_edit_requirement(self):
        role = Group.objects.create(name="Creator Only")
        feature = Feature.objects.get(key="employee_records")
        RoleFeaturePermission.objects.create(role=role, feature=feature, can_create=True)
        user = User.objects.create_user(username="ladder_creator", password="pass12345")
        user.groups.add(role)

        employee = Employee.objects.create(
            company=self.company, salutation="Mr", first_name="Lad", last_name="Der",
            father_name="Father", gender="Male", date_of_birth=date(1990, 1, 1),
            personal_email="ladder@test.com", personal_mobile="1234567890",
            employee_code="RPT900", designation="Dev", department="IT",
            date_of_joining=date(2020, 1, 1), status="Active",
        )
        self.assertNotEqual(self._status(user, reverse("employee_create")), 403)
        self.assertEqual(self._status(user, reverse("employee_edit", args=[employee.id])), 403)

    # ── self-service roles are locked out of company-wide pages ───────

    def test_hod_and_employee_cannot_reach_the_admin_dashboard(self):
        url = reverse("admin-dashboard")
        self.assertEqual(self._status(self.hod_user, url), 403)
        self.assertEqual(self._status(self.employee_user, url), 403)
        self.assertNotEqual(self._status(self.hr_user, url), 403)

    def test_hod_cannot_reach_the_employee_list(self):
        self.assertEqual(self._status(self.hod_user, reverse("employee_list")), 403)

    # ── bypasses ──────────────────────────────────────────────────────

    def test_superuser_bypasses_every_feature_gate(self):
        for url in (reverse("create-company"), reverse("payroll-run-create"), reverse("admin-dashboard")):
            self.assertNotEqual(self._status(self.superuser, url), 403, url)
        self.assertNotEqual(self._client_as(self.superuser).post(reverse("create-company"), {
            "short_name": "SU", "name": "Su Co", "address": "Addr",
            "phone": "1", "email": "su@test.com", "status": "active",
        }).status_code, 403)

    def test_super_admin_can_reach_the_roles_page(self):
        """The Roles & Permissions page is gated on a hardcoded group list
        rather than the matrix (so nobody can revoke their way out of it) --
        Super Admin has to be on that list or the top role can't manage
        roles at all."""
        url = reverse("roles-permissions-hub")
        self.assertNotEqual(self._status(self.super_admin, url), 403)
        self.assertNotEqual(self._status(self.admin_user, url), 403)
        self.assertEqual(self._status(self.hr_user, url), 403)
        self.assertEqual(self._status(self.hod_user, url), 403)

    def test_super_admin_reaches_everything_admin_cannot(self):
        self.assertNotEqual(self._status(self.super_admin, reverse("payroll-run-create")), 403)
