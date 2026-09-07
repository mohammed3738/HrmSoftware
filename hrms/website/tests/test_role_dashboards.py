"""
Regression tests for role-shaped dashboards.

There are two dashboard pages, not six: the admin dashboard assembles the
panels a user is actually allowed to act on, and the self-service dashboard
grows a "My Team" block for anyone people report to. The panels are chosen
from feature permissions rather than role names, so a custom role built in
the permission matrix also gets a coherent page instead of buttons that
403 when clicked.

Run with: python manage.py test website.tests.test_role_dashboards
"""
from datetime import date

from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse

from website.models import (
    Attendance, Company, CompOffRequest, Department, Employee, Feature,
    LeaveApplication, PayrollRun, PayrollSettings, RoleFeaturePermission,
    SalaryMaster,
)


def make_employee(company, code, first_name="Dash", user=None, **kwargs):
    return Employee.objects.create(
        company=company, user=user, salutation="Mr", first_name=first_name, last_name="Board",
        father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
        place_of_birth="City", personal_email=f"{code}@test.com", present_address="Addr",
        permanent_address="Addr", personal_mobile="1234567890", employee_code=code,
        designation="Dev", date_of_joining=date(2020, 1, 1), location="City",
        pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank=first_name,
        salary_account_number="1234567890", ifsc_code="TEST0001234",
        emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
        emergency_contact_mobile1="0987654321", status="Active", force_password_change=False,
        **kwargs
    )


class AdminDashboardPanelsTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="RDB", name="Role Dash Co", phone="1", email="rdb@test.com", address="Addr",
        )
        PayrollSettings.objects.create(company=self.company)

        def staff(role, username):
            user = User.objects.create_user(username=username, password="pass12345")
            user.groups.add(Group.objects.get(name=role))
            return user

        self.super_admin = staff("Super Admin", "rdb_super")
        self.admin = staff("Admin", "rdb_admin")
        self.payroll_officer = staff("Payroll Officer", "rdb_payroll")
        self.hr = staff("HR", "rdb_hr")

    def _dash(self, user):
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return client.get(reverse("admin-dashboard"))

    # ── payroll panel ─────────────────────────────────────────────────

    def test_payroll_panel_shown_to_everyone_who_can_read_payroll(self):
        for user in (self.super_admin, self.admin, self.payroll_officer):
            resp = self._dash(user)
            self.assertTrue(resp.context["show_payroll_panel"], user.username)
            self.assertContains(resp, "Payroll Runs")

    def test_payroll_runs_are_hidden_from_hr_everywhere_they_surface(self):
        """The Payroll *menu* stays -- it also holds Create Salary Structure
        and Salary History, which HR needs. What HR must not see is the
        payroll run itself: the nav item, the dashboard panel, the pages."""
        resp = self._dash(self.hr)
        self.assertNotContains(resp, "<div>Payroll Run</div>", html=False)
        self.assertNotContains(resp, "Payroll Runs")
        self.assertNotContains(resp, "New Payroll Run")

        client = Client()
        client.force_login(self.hr, backend="django.contrib.auth.backends.ModelBackend")
        for url in (reverse("payroll-run-list"), reverse("payroll-run-create")):
            self.assertEqual(client.get(url).status_code, 403, url)

    def test_late_attendance_review_is_hidden_from_hr(self):
        """The page exists to convert/forgive late days, which needs
        attendance_review:edit -- HR reads attendance but doesn't correct
        it, so the nav item goes and the page refuses."""
        resp = self._dash(self.hr)
        self.assertNotContains(resp, "<div>Late Attendance Review</div>", html=False)

        client = Client()
        client.force_login(self.hr, backend="django.contrib.auth.backends.ModelBackend")
        self.assertEqual(client.get(reverse("late_attendance_review")).status_code, 403)

    def test_late_attendance_review_stays_for_roles_that_correct_attendance(self):
        resp = self._dash(self.admin)
        self.assertContains(resp, "<div>Late Attendance Review</div>", html=False)

        client = Client()
        client.force_login(self.admin, backend="django.contrib.auth.backends.ModelBackend")
        self.assertNotEqual(client.get(reverse("late_attendance_review")).status_code, 403)

    def test_hr_gets_a_read_only_attendance_register(self):
        """HR may review the register but not change a recorded day, so the
        day cells must not be clickable -- they post to an endpoint HR
        cannot use."""
        client = Client()
        client.force_login(self.hr, backend="django.contrib.auth.backends.ModelBackend")
        resp = client.get(reverse("attendance-register"))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["can_edit_attendance"])
        self.assertNotContains(resp, "openDayOverride(this)")
        self.assertContains(resp, "Read-only")

    def test_hr_keeps_salary_structure_in_the_payroll_menu(self):
        """Gating the whole Payroll menu on payroll:view would take Create
        Salary Structure away from HR, who needs it."""
        resp = self._dash(self.hr)
        self.assertContains(resp, "<div>Payroll</div>", html=False)
        self.assertContains(resp, "<div>Create Salary Structure</div>", html=False)
        self.assertContains(resp, "<div>Salary History</div>", html=False)
        # Salary Increment edits an existing structure -- that is edit-only.
        self.assertNotContains(resp, "<div>Salary Increment</div>", html=False)

    def test_payroll_pages_render_read_only_for_a_view_only_role(self):
        """Admin reads payroll runs but cannot change them, so the page must
        not offer Recalculate/Finalize or editable amount fields."""
        run = PayrollRun.objects.create(
            company=self.company, month=date(2026, 1, 1),
            start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
            status=PayrollRun.STATUS_DRAFT,
        )
        admin_client = Client()
        admin_client.force_login(self.admin, backend="django.contrib.auth.backends.ModelBackend")

        listing = admin_client.get(reverse("payroll-run-list"))
        self.assertEqual(listing.status_code, 200)
        self.assertFalse(listing.context["can_run_payroll"])
        self.assertNotContains(listing, "New Payroll Run")

        detail = admin_client.get(reverse("payroll-run-detail", args=[run.id]))
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, 'id="btnFinalize"')
        self.assertNotContains(detail, 'id="btnRecalculate"')
        self.assertContains(detail, "Read only")

    def test_payroll_officer_gets_the_editable_payroll_page(self):
        run = PayrollRun.objects.create(
            company=self.company, month=date(2026, 1, 1),
            start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
            status=PayrollRun.STATUS_DRAFT,
        )
        client = Client()
        client.force_login(self.payroll_officer, backend="django.contrib.auth.backends.ModelBackend")
        detail = client.get(reverse("payroll-run-detail", args=[run.id]))
        self.assertContains(detail, 'id="btnFinalize"')
        self.assertNotContains(detail, "Read only")

    def test_hr_dashboard_has_no_payroll_panel(self):
        """HR holds no payroll access at all, so the panel would only tease
        a page they cannot open."""
        resp = self._dash(self.hr)
        self.assertFalse(resp.context["show_payroll_panel"])
        self.assertNotContains(resp, "Payroll Runs")

    def test_only_payroll_runners_get_the_new_run_button(self):
        """Admin can read a payroll run but not create one, so offering the
        button would just 403 them."""
        self.assertFalse(self._dash(self.admin).context["can_run_payroll"])
        self.assertTrue(self._dash(self.payroll_officer).context["can_run_payroll"])
        self.assertNotContains(self._dash(self.admin), "New Payroll Run")
        self.assertContains(self._dash(self.payroll_officer), "New Payroll Run")

    def test_nav_only_offers_menus_the_role_can_open(self):
        """A menu that 403s when clicked is worse than no menu."""
        admin_nav = self._dash(self.admin)
        self.assertContains(admin_nav, "<div>Payroll</div>", html=False)

        role = Group.objects.create(name="Dashboard Nav Only")
        RoleFeaturePermission.objects.create(
            role=role, feature=Feature.objects.get(key="admin_dashboard"), can_view=True,
        )
        user = User.objects.create_user(username="rdb_nav", password="pass12345")
        user.groups.add(role)
        resp = self._dash(user)
        for menu in ("<div>Payroll</div>", "<div>Employees</div>", "<div>Company</div>"):
            self.assertNotContains(resp, menu, html=False)

    def test_self_service_menus_stay_open_to_everyone(self):
        """Leave Apply and the attendance list are ungated pages every
        employee needs -- gating their menus would lock people out of
        applying for leave."""
        role = Group.objects.create(name="Bare Dashboard")
        RoleFeaturePermission.objects.create(
            role=role, feature=Feature.objects.get(key="admin_dashboard"), can_view=True,
        )
        user = User.objects.create_user(username="rdb_bare", password="pass12345")
        user.groups.add(role)

        resp = self._dash(user)
        self.assertContains(resp, "<div>Leaves &amp; Comp-Off</div>".replace("&amp;", "&"), html=False)
        self.assertContains(resp, "<div>Leave Apply</div>", html=False)

    def test_payroll_panel_counts_runs_and_flags_missing_salary_structures(self):
        paid = make_employee(self.company, "RDB001")
        make_employee(self.company, "RDB002")  # no salary structure
        SalaryMaster.objects.create(employee=paid, is_active=True)
        PayrollRun.objects.create(
            company=self.company, month=date(2026, 1, 1),
            start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
            status=PayrollRun.STATUS_DRAFT,
        )
        PayrollRun.objects.create(
            company=self.company, month=date(2026, 2, 1),
            start_date=date(2026, 2, 1), end_date=date(2026, 2, 28),
            status=PayrollRun.STATUS_FINALIZED,
        )

        resp = self._dash(self.payroll_officer)
        self.assertEqual(resp.context["draft_run_count"], 1)
        self.assertEqual(resp.context["finalized_run_count"], 1)
        self.assertEqual(resp.context["employees_without_salary"], 1)
        self.assertEqual(len(resp.context["recent_payroll_runs"]), 2)

    def test_payroll_data_is_not_computed_for_users_who_cannot_see_it(self):
        """A custom role without payroll:view shouldn't pay for the panel's
        queries, nor leak run data into its template context."""
        role = Group.objects.create(name="People Only")
        RoleFeaturePermission.objects.create(
            role=role, feature=Feature.objects.get(key="admin_dashboard"), can_view=True,
        )
        RoleFeaturePermission.objects.create(
            role=role, feature=Feature.objects.get(key="employee_records"), can_view=True,
        )
        user = User.objects.create_user(username="rdb_people", password="pass12345")
        user.groups.add(role)

        resp = self._dash(user)
        self.assertFalse(resp.context["show_payroll_panel"])
        self.assertNotIn("recent_payroll_runs", resp.context)

    # ── panels follow permissions, not role names ─────────────────────

    def test_attendance_tools_hidden_without_attendance_data_edit(self):
        role = Group.objects.create(name="Dashboard Reader")
        for key in ("admin_dashboard", "attendance_review"):
            RoleFeaturePermission.objects.create(
                role=role, feature=Feature.objects.get(key=key), can_view=True,
            )
        user = User.objects.create_user(username="rdb_reader", password="pass12345")
        user.groups.add(role)

        resp = self._dash(user)
        self.assertTrue(resp.context["show_attendance_panels"])
        self.assertFalse(resp.context["show_attendance_tools"])
        # The nav also carries an "Upload Attendance (Excel)" link, so this
        # targets the dashboard's own button.
        self.assertNotContains(resp, 'id="openUploadModal"')
        # ...but the read-only attendance breakdown is still there.
        self.assertContains(resp, "View Full Attendance")

    def test_approval_panels_hidden_when_no_approval_rights(self):
        role = Group.objects.create(name="Dashboard Only")
        RoleFeaturePermission.objects.create(
            role=role, feature=Feature.objects.get(key="admin_dashboard"), can_view=True,
        )
        user = User.objects.create_user(username="rdb_only", password="pass12345")
        user.groups.add(role)

        resp = self._dash(user)
        self.assertFalse(resp.context["show_any_approvals"])
        self.assertNotContains(resp, "Pending Leave Requests")

    def test_hr_sees_the_people_panels_but_no_approval_queues(self):
        """HR administers people -- onboarding, attendance, offboarding --
        while sign-off sits with Admin and with HODs on the reporting line."""
        resp = self._dash(self.hr)
        self.assertTrue(resp.context["show_people_panels"])
        self.assertTrue(resp.context["show_offboarding_panel"])
        self.assertTrue(resp.context["show_attendance_tools"])
        self.assertContains(resp, "Recent Joiners")
        self.assertContains(resp, "Upload Attendance")

        self.assertFalse(resp.context["show_any_approvals"])
        self.assertNotContains(resp, "Pending Leave Requests")

    def test_admin_still_sees_the_approval_queues(self):
        resp = self._dash(self.admin)
        self.assertTrue(resp.context["show_any_approvals"])
        self.assertContains(resp, "Pending Leave Requests")


class HodTeamPanelTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="HTD", name="HOD Dash Co", phone="1", email="htd@test.com", address="Addr",
        )
        PayrollSettings.objects.create(company=self.company)

        self.hod_user = User.objects.create_user(username="htd_hod", password="pass12345")
        self.hod_user.groups.add(Group.objects.get(name="HOD"))
        self.hod = make_employee(self.company, "HTD_HOD", "Head", user=self.hod_user)

        Department.objects.create(name="Sales", reporting_person=self.hod, manager=self.hod)
        self.reportee = make_employee(self.company, "HTD001", "Report", department="Sales")

    def _dash(self, user):
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return client.get(reverse("employee-dashboard"))

    def test_hod_lands_on_the_self_service_dashboard(self):
        from website.views import role_based_dashboard_url
        self.assertEqual(role_based_dashboard_url(self.hod_user), "employee-dashboard")

    def test_team_panel_appears_with_reportees(self):
        resp = self._dash(self.hod_user)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["has_team"])
        self.assertEqual(resp.context["team_size"], 1)
        self.assertContains(resp, "My Team")

    def test_team_panel_counts_pending_requests_from_reportees_only(self):
        LeaveApplication.objects.create(
            employee=self.reportee, leave_type="CL", start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 1), reason="Personal", status="Pending",
        )
        outsider = make_employee(self.company, "HTD002", "Outside", department="Engineering")
        LeaveApplication.objects.create(
            employee=outsider, leave_type="CL", start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 1), reason="Personal", status="Pending",
        )

        resp = self._dash(self.hod_user)
        self.assertEqual(resp.context["team_pending_leave"], 1)
        self.assertEqual(resp.context["team_pending_total"], 1)

    def test_team_panel_shows_todays_status_per_reportee(self):
        Attendance.objects.create(
            employee=self.reportee, date=date.today(), status="Absent", status_overridden=True,
        )
        resp = self._dash(self.hod_user)
        self.assertEqual(resp.context["team_absent_today"], 1)
        rows = {r["employee"].employee_code: r for r in resp.context["team_today"]}
        self.assertEqual(rows["HTD001"]["attendance"].status, "Absent")

    def test_plain_employee_gets_no_team_panel(self):
        user = User.objects.create_user(username="htd_emp", password="pass12345")
        user.groups.add(Group.objects.get(name="Employee"))
        make_employee(self.company, "HTD003", "Plain", user=user)

        resp = self._dash(user)
        self.assertFalse(resp.context["has_team"])
        self.assertNotContains(resp, "My Team")

    def test_a_hod_with_nobody_reporting_to_them_gets_no_empty_panel(self):
        lonely_user = User.objects.create_user(username="htd_lonely", password="pass12345")
        lonely_user.groups.add(Group.objects.get(name="HOD"))
        make_employee(self.company, "HTD004", "Lonely", user=lonely_user)

        resp = self._dash(lonely_user)
        self.assertFalse(resp.context["has_team"])

    def test_hod_dashboard_carries_the_approval_queues_themselves(self):
        """Not just counts and a link -- the HOD approves from their own
        dashboard."""
        LeaveApplication.objects.create(
            employee=self.reportee, leave_type="CL", start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 1), reason="Personal", status="Pending",
        )
        resp = self._dash(self.hod_user)
        self.assertContains(resp, "Pending Leave Requests")
        self.assertContains(resp, "Pending Comp-Off Requests")
        self.assertContains(resp, "Pending Attendance Corrections")
        self.assertContains(resp, "actOn('leave'")
        self.assertEqual([l.id for l in resp.context["leave_requests"]],
                         [LeaveApplication.objects.get().id])

    def test_hod_can_approve_a_leave_straight_from_the_dashboard(self):
        leave = LeaveApplication.objects.create(
            employee=self.reportee, leave_type="CL", start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 1), reason="Personal", status="Pending",
        )
        client = Client()
        client.force_login(self.hod_user, backend="django.contrib.auth.backends.ModelBackend")
        resp = client.post(reverse("approve_leave", args=[leave.id]))
        self.assertEqual(resp.status_code, 200)
        leave.refresh_from_db()
        self.assertEqual(leave.status, "Approved")

        # ...and it drops off the dashboard queue.
        self.assertEqual(list(self._dash(self.hod_user).context["leave_requests"]), [])

    def test_hod_can_reject_a_compoff_straight_from_the_dashboard(self):
        compoff = CompOffRequest.objects.create(
            employee=self.reportee, from_date=date(2026, 6, 1), to_date=date(2026, 6, 1),
            count=1, reason="Worked a weekend", status="Pending",
        )
        client = Client()
        client.force_login(self.hod_user, backend="django.contrib.auth.backends.ModelBackend")
        resp = client.post(
            reverse("reject_compoff", args=[compoff.id]),
            data='{"reason": "Not approved"}', content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        compoff.refresh_from_db()
        self.assertEqual(compoff.status, "Rejected")

    def test_the_dashboard_queues_never_show_someone_elses_reportees(self):
        outsider = Employee.objects.get(employee_code="HTD002") if Employee.objects.filter(
            employee_code="HTD002").exists() else make_employee(self.company, "HTD002", "Outside", department="Engineering")
        LeaveApplication.objects.create(
            employee=outsider, leave_type="CL", start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 1), reason="Personal", status="Pending",
        )
        resp = self._dash(self.hod_user)
        self.assertEqual(list(resp.context["leave_requests"]), [])

    def test_a_plain_employee_dashboard_has_no_approval_queues(self):
        user = User.objects.create_user(username="htd_plain2", password="pass12345")
        user.groups.add(Group.objects.get(name="Employee"))
        make_employee(self.company, "HTD005", "Plain", user=user)
        resp = self._dash(user)
        self.assertNotContains(resp, "Pending Leave Requests")

    def test_dashboard_offers_an_apply_for_leave_button(self):
        """Applying for leave is the thing an employee comes to their
        dashboard to do, so it shouldn't be buried in a nav menu."""
        resp = self._dash(self.hod_user)
        self.assertContains(resp, reverse("leave_apply"))
        self.assertContains(resp, "Apply for Leave")

    def test_a_plain_employee_gets_the_apply_for_leave_button_too(self):
        user = User.objects.create_user(username="htd_leavebtn", password="pass12345")
        user.groups.add(Group.objects.get(name="Employee"))
        make_employee(self.company, "HTD006", "Leave", user=user)
        resp = self._dash(user)
        self.assertContains(resp, "Apply for Leave")

    def test_dashboard_offers_a_my_details_button_that_lands_on_own_record(self):
        """Goes through my_profile rather than employee_detail with a
        hardcoded id, so the link can't be edited into someone else's
        record and the ownership check lives in one place."""
        resp = self._dash(self.hod_user)
        self.assertContains(resp, reverse("my_profile"))
        self.assertContains(resp, "My Details")

        client = Client()
        client.force_login(self.hod_user, backend="django.contrib.auth.backends.ModelBackend")
        follow = client.get(reverse("my_profile"))
        self.assertRedirects(
            follow, reverse("employee_detail", args=[self.hod.pk]), fetch_redirect_response=False,
        )

    def test_hod_still_cannot_reach_the_admin_dashboard(self):
        client = Client()
        client.force_login(self.hod_user, backend="django.contrib.auth.backends.ModelBackend")
        self.assertEqual(client.get(reverse("admin-dashboard")).status_code, 403)
