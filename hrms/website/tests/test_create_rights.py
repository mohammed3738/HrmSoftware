"""
Create is its own right on Roles & Permissions: a role can be allowed to
ADD (branches, departments, announcements, ...) without being allowed to
CHANGE what already exists. Edit still includes Create, so the roles that
could add things before still can. And every box on the matrix is tickable:
ones the app doesn't check yet are saved and shown faded.

Run with: python manage.py test website.tests.test_create_rights
"""
from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import Announcement, Branch, Department, Feature, RoleFeaturePermission
from website.utils.permissions import has_feature_permission


class RoleTestBase(TestCase):
    def role_client(self, name, grants):
        """A custom role holding exactly `grants`: {(feature, action), ...}."""
        group = Group.objects.create(name=name)
        for key in {k for k, _ in grants}:
            RoleFeaturePermission.objects.create(
                role=group, feature=Feature.objects.get(key=key),
                **{f"can_{a}": True for k, a in grants if k == key},
            )
        user = User.objects.create_user(username=name.lower(), password="pass12345")
        user.groups.add(group)
        c = Client()
        c.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return c, user


class CreateRightTest(RoleTestBase):
    def test_create_only_can_add_a_branch_but_not_change_one(self):
        c, _ = self.role_client("BranchClerk", {("branch_management", "create")})
        resp = c.post(reverse("create-branch"), {"branch_name": "Pune", "branch_address": "A"})
        self.assertEqual(resp.status_code, 302)
        branch = Branch.objects.get(branch_name="Pune")
        self.assertEqual(c.post(reverse("edit_branch", args=[branch.id]), {"branch_name": "X"}).status_code, 403)

    def test_create_only_can_add_a_department_but_not_change_one(self):
        c, _ = self.role_client("DeptClerk", {("department_management", "create")})
        c.post(reverse("department-create"), {"name": "Accounts"})
        dept = Department.objects.get(name="Accounts")
        resp = c.post(reverse("department-edit", args=[dept.id]), {"name": "Renamed"})
        self.assertEqual(resp.status_code, 403)
        dept.refresh_from_db()
        self.assertEqual(dept.name, "Accounts")

    def test_create_only_can_post_an_announcement_but_not_edit_one(self):
        c, _ = self.role_client("Poster", {("announcements", "create"), ("announcements", "view")})
        resp = c.post(reverse("save-announcement"), {"title": "Hello", "body": "World"})
        self.assertEqual(resp.status_code, 200, resp.content)
        ann = Announcement.objects.get(title="Hello")
        resp = c.post(reverse("save-announcement"), {"announcement_id": ann.id, "title": "Changed", "body": "x"})
        self.assertEqual(resp.status_code, 403)

    def test_edit_still_includes_create(self):
        _, user = self.role_client("Editor", {("branch_management", "edit")})
        self.assertTrue(has_feature_permission(user, "branch_management", "create"))
        _, viewer = self.role_client("Viewer", {("branch_management", "view")})
        self.assertFalse(has_feature_permission(viewer, "branch_management", "create"))

    def test_existing_edit_holders_hold_create_too(self):
        # Migration 0062: every role with Edit on these features starts with Create ticked.
        for key in ("branch_management", "department_management", "announcements", "payroll"):
            editors = set(RoleFeaturePermission.objects.filter(feature__key=key, can_edit=True)
                          .values_list("role__name", flat=True))
            creators = set(RoleFeaturePermission.objects.filter(feature__key=key, can_create=True)
                           .values_list("role__name", flat=True))
            self.assertTrue(editors, key)
            self.assertEqual(editors, creators, key)


class MatrixBoxesTest(TestCase):
    """Only actions that do something can be ticked; the rest show "—"."""

    def setUp(self):
        self.su = User.objects.create_superuser("matrix_su", "m@t.com", "pass12345")
        self.client.force_login(self.su, backend="django.contrib.auth.backends.ModelBackend")
        self.role = Group.objects.create(name="Custom")

    def test_every_box_is_tickable_and_saved(self):
        audit = Feature.objects.get(key="audit_log")   # no separate edit function
        page = self.client.get(reverse("roles-permissions-hub"), {"role_id": self.role.id})
        self.assertContains(page, f'name="can_edit_{audit.id}"')
        self.assertNotContains(page, "Nothing to allow here")
        self.client.post(reverse("save-role-permissions"),
                         {"role_id": self.role.id, f"can_edit_{audit.id}": "on"})
        rfp = RoleFeaturePermission.objects.get(role=self.role, feature=audit)
        self.assertTrue(rfp.can_edit)

    def test_tick_without_its_own_function_opens_the_feature_read_only(self):
        audit = Feature.objects.get(key="audit_log")
        RoleFeaturePermission.objects.create(role=self.role, feature=audit, can_edit=True)
        user = User.objects.create_user(username="audit_editor", password="pass12345")
        user.groups.add(self.role)
        self.assertTrue(has_feature_permission(user, "audit_log", "view"))
        c = Client()
        c.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        self.assertEqual(c.get(reverse("audit-log")).status_code, 200)

    def test_new_boxes_are_tickable(self):
        page = self.client.get(reverse("roles-permissions-hub"), {"role_id": self.role.id})
        for key, action in (("payroll", "approve"), ("employee_change_approval", "view"),
                            ("archive_records", "view"), ("advances", "approve"),
                            ("branch_management", "create")):
            self.assertContains(page, f'name="can_{action}_{Feature.objects.get(key=key).id}"', msg_prefix=key)


class PayrollApproveTest(RoleTestBase):
    def test_finalizing_needs_approve(self):
        from datetime import date
        from website.models import Company, PayrollRun
        company = Company.objects.create(short_name="PA", name="Pay Appr", phone="1", email="p@t.com", address="A")
        run = PayrollRun.objects.create(company=company, month=date(2026, 10, 1),
                                        start_date=date(2026, 9, 27), end_date=date(2026, 10, 26))
        runner, _ = self.role_client("Runner", {("payroll", "view"), ("payroll", "edit")})
        self.assertEqual(runner.post(reverse("payroll-run-finalize", args=[run.id])).status_code, 403)
        page = runner.get(reverse("payroll-run-detail", args=[run.id]))
        self.assertNotContains(page, 'id="btnFinalize"')

        finalizer, _ = self.role_client("Finalizer", {("payroll", "view"), ("payroll", "approve")})
        self.assertNotEqual(finalizer.post(reverse("payroll-run-finalize", args=[run.id])).status_code, 403)


class ChangeQueueViewTest(RoleTestBase):
    def test_view_shows_the_queue_but_cannot_decide(self):
        watcher, _ = self.role_client("Watcher", {("employee_change_approval", "view")})
        self.assertEqual(watcher.get(reverse("employee_change_requests")).status_code, 200)
        self.assertEqual(watcher.post(reverse("employee_change_requests_bulk"),
                                      {"decision": "approve", "ids": ["1"]}).status_code, 403)
        outsider, _ = self.role_client("Outsider", {("employee_records", "view")})
        self.assertEqual(outsider.get(reverse("employee_change_requests")).status_code, 403)


class ArchiveViewTest(RoleTestBase):
    def setUp(self):
        Branch.objects.create(branch_name="Live", branch_address="A", is_active=True)
        Branch.objects.create(branch_name="Closed", branch_address="A", is_active=False)

    def names(self, client):
        resp = client.get(reverse("create-branch"), {"show": "archived"})
        return {b.branch_name for b in resp.context["branches"]}

    def test_archived_tab_needs_archive_view(self):
        plain, _ = self.role_client("Plain", {("branch_management", "create")})
        self.assertEqual(self.names(plain), {"Live"})            # falls back to active
        archivist, _ = self.role_client("Archivist", {("branch_management", "create"),
                                                      ("archive_records", "view")})
        self.assertEqual(self.names(archivist), {"Closed"})


class AdvanceApprovalTest(RoleTestBase):
    def setUp(self):
        from datetime import date
        from website.models import Company, Employee
        company = Company.objects.create(short_name="AA", name="Adv Co", phone="1", email="a@t.com", address="A")
        self.emp = Employee.objects.create(company=company, first_name="Adv", last_name="E", employee_code="AA1",
                                           date_of_joining=date(2020, 1, 1), status="Active")
        self.month = date.today().replace(day=1)

    def create(self, client):
        client.post(reverse("create-advance"), {
            "employee": self.emp.id, "advance_amount": 3000, "default_months": 3,
            "start_date": self.month.isoformat(),
        })
        from website.models import AdvanceMaster
        return AdvanceMaster.objects.get(employee=self.emp)

    def deduction(self):
        import calendar
        from website.services import get_advance_for_employee_month
        last = self.month.replace(day=calendar.monthrange(self.month.year, self.month.month)[1])
        return get_advance_for_employee_month(self.emp, self.month, last)

    def test_advance_from_creator_waits_for_approval(self):
        from website.models import AdvanceMaster
        clerk, _ = self.role_client("AdvClerk", {("advances", "view"), ("advances", "create")})
        adv = self.create(clerk)
        self.assertEqual(adv.status, AdvanceMaster.STATUS_AWAITING_APPROVAL)
        self.assertEqual(self.deduction(), 0)                    # not deducted yet
        self.assertEqual(clerk.post(reverse("advance-decide", args=[adv.id]),
                                    {"decision": "approve"}).status_code, 403)

        approver, _ = self.role_client("AdvBoss", {("advances", "view"), ("advances", "approve")})
        approver.post(reverse("advance-decide", args=[adv.id]), {"decision": "approve"})
        adv.refresh_from_db()
        self.assertEqual(adv.status, AdvanceMaster.STATUS_ACTIVE)
        self.assertEqual(self.deduction(), 1000)

    def test_rejected_advance_is_never_deducted(self):
        from website.models import AdvanceMaster
        clerk, _ = self.role_client("AdvClerk2", {("advances", "view"), ("advances", "create")})
        adv = self.create(clerk)
        approver, _ = self.role_client("AdvBoss2", {("advances", "view"), ("advances", "approve")})
        approver.post(reverse("advance-decide", args=[adv.id]), {"decision": "reject"})
        adv.refresh_from_db()
        self.assertEqual(adv.status, AdvanceMaster.STATUS_REJECTED)
        self.assertEqual(self.deduction(), 0)

    def test_creator_who_can_approve_creates_it_active(self):
        from website.models import AdvanceMaster
        boss, _ = self.role_client("AdvBoss3", {("advances", "view"), ("advances", "create"), ("advances", "approve")})
        self.assertEqual(self.create(boss).status, AdvanceMaster.STATUS_ACTIVE)
