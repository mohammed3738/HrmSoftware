"""
Regression tests for endpoints that were left behind by the
@feature_required gating pass.

Each view below had only @login_required, while every sibling view in the
same family carried a feature gate -- which is what makes these omissions
rather than deliberately-open pages:

  * holiday calendar WRITES: add_holiday, edit_holiday, delete_holiday,
    create/edit/delete_holiday_type and delete_half_day_scenario all
    require holiday_calendar:edit, but save_holiday_settings,
    edit_earned_leave, add_half_day_scenario and edit_half_day_scenario
    required nothing. Any logged-in employee could rewrite their company's
    financial-year start (which deletes and regenerates every
    auto-generated MonthlyEarnedLeaves row), set a month's earned leaves to
    any value 0-31, or create and approve a half-day scenario with an
    arbitrary credit_count. All three feed leave balance and payroll.

  * branch: create_branchs, delete_branch, upload_branch_excel all require
    branch_management:edit and branch_details_api requires
    branch_management:view, but edit_branch (a write) and get_branch (a
    near-duplicate of branch_details_api) required nothing.

  * offboarding: offboarding_export_excel requires offboarding:view and
    offboarding_delete requires offboarding:edit, but offboarding_detail
    and offboarding_edit_data -- which return resignation dates, personal
    email, personal mobile and the media URLs of the experience
    certificate, relieving letter and F&F documents -- required nothing.

  * shift roster: add/edit/delete_shift_assignment all require
    shift_roster:edit and the list page requires shift_roster:view, but
    api_get_shift_assignment required nothing.

  * employee_leave_history returned any employee's LeaveBalanceHistory to
    any logged-in user from a numeric URL id, with no ownership check --
    the same hole can_access_employee_record() was introduced to close on
    employee_detail / employee_attendance_detail / salary_slip_view.

The holiday calendar's READ endpoints (holiday_calendar_dashboard,
holiday_list, earned_leaves_config, api_holidays_json, api_earned_leaves,
api_holiday_types, api_get_holiday, api_get_holiday_type,
api_get_half_day_scenario) are deliberately open to any logged-in user --
employees are meant to see the holiday calendar, and the feature registry
declares holiday_calendar with has_view=False for exactly that reason. They
are asserted to stay open here so a future tightening pass does not lock
employees out of their own holiday list by accident.

Run with:
    python manage.py test website.tests.test_ungated_endpoint_permissions
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import (
    Branch,
    Company,
    Employee,
    HalfDayScenario,
    LeaveBalanceHistory,
    MonthlyEarnedLeaves,
    Offboarding,
    PayrollSettings,
    ShiftAssignment,
)


def make_employee(company, code, first_name, user=None, **extra):
    return Employee.objects.create(
        company=company, user=user, salutation="Mr", first_name=first_name, last_name="Doe",
        father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
        place_of_birth="City", personal_email=f"{code}@test.com", present_address="Addr",
        permanent_address="Addr", personal_mobile="1234567890", employee_code=code,
        designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), location="City",
        pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank=first_name,
        salary_account_number="1234567890", ifsc_code="TEST0001234",
        emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
        emergency_contact_mobile1="0987654321", status="Active", force_password_change=False,
        **extra,
    )


class UngatedEndpointPermissionTest(TestCase):
    """A plain Employee must not reach the write endpoints; a Super Admin
    (who holds every grant in the seed matrix) still must."""

    def setUp(self):
        self.company = Company.objects.create(
            short_name="UGE", name="Ungated Co", phone="1", email="uge@test.com", address="Addr",
        )
        self.branch = Branch.objects.create(branch_name="Main")
        self.settings = PayrollSettings.objects.create(
            company=self.company, financial_year_start_month=4,
        )

        # A plain employee with a login, in the employee's own company.
        self.emp_user = User.objects.create_user(username="uge_emp", password="pass12345")
        self.emp_user.groups.add(Group.objects.get(name="Employee"))
        self.employee = make_employee(self.company, "UGE001", "Self", user=self.emp_user)

        # Somebody else's record, for the cross-employee reads.
        self.other = make_employee(self.company, "UGE002", "Other")

        self.super_user = User.objects.create_user(username="uge_super", password="pass12345")
        self.super_user.groups.add(Group.objects.get(name="Super Admin"))

        self.hr_user = User.objects.create_user(username="uge_hr", password="pass12345")
        self.hr_user.groups.add(Group.objects.get(name="HR"))

        # PayrollSettings creation auto-generates the financial year's
        # MonthlyEarnedLeaves rows through a signal, so take one of those
        # rather than racing it with a second row for the same month.
        self.earned_leave, _ = MonthlyEarnedLeaves.objects.get_or_create(
            payroll_settings=self.settings, month=4, year=2026,
            defaults={"earned_leaves": Decimal("2.00"), "is_auto_generated": True},
        )
        self.earned_leave.earned_leaves = Decimal("2.00")
        self.earned_leave.is_auto_generated = True
        self.earned_leave.save(update_fields=["earned_leaves", "is_auto_generated"])
        self.scenario = HalfDayScenario.objects.create(
            branch=self.branch, scenario_date=date(2026, 5, 1), scenario_type="other",
            description="Original", credit_count=Decimal("0.50"), created_by=self.super_user,
        )
        self.offboarding = Offboarding.objects.create(
            employee=self.other, date_of_resignation=date(2026, 1, 1),
            date_of_relieving=date(2026, 1, 31),
        )
        self.shift = ShiftAssignment.objects.create(
            employee=self.other, shift_name="Night", start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 31), created_by=self.super_user,
        )
        LeaveBalanceHistory.objects.create(employee=self.other, month=date(2026, 4, 1))

    def _as(self, user):
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return client

    # ── holiday calendar writes ──────────────────────────────────────────

    def test_employee_cannot_save_holiday_settings(self):
        resp = self._as(self.emp_user).post(
            reverse("save-holiday-settings"),
            {"financial_year_start_month": "1", "branch_specific_holidays": "false"},
        )
        self.assertEqual(resp.status_code, 403)
        self.settings.refresh_from_db()
        self.assertEqual(self.settings.financial_year_start_month, 4)

    def test_employee_cannot_wipe_earned_leaves_by_changing_financial_year(self):
        """The real damage of save_holiday_settings: a changed FY start
        month deletes every auto-generated MonthlyEarnedLeaves row."""
        self._as(self.emp_user).post(
            reverse("save-holiday-settings"),
            {"financial_year_start_month": "1", "branch_specific_holidays": "false"},
        )
        self.assertTrue(
            MonthlyEarnedLeaves.objects.filter(pk=self.earned_leave.pk).exists(),
            "an employee's POST deleted auto-generated earned-leave rows",
        )

    def test_employee_cannot_edit_earned_leave(self):
        resp = self._as(self.emp_user).post(
            reverse("edit-earned-leave", args=[self.earned_leave.pk]),
            {"earned_leaves": "31", "is_auto_generated": "off"},
        )
        self.assertEqual(resp.status_code, 403)
        self.earned_leave.refresh_from_db()
        self.assertEqual(self.earned_leave.earned_leaves, Decimal("2.00"))

    def test_employee_cannot_add_half_day_scenario(self):
        resp = self._as(self.emp_user).post(
            reverse("add-half-day-scenario"),
            {"scenario_date": "2026-06-01", "description": "Injected",
             "scenario_type": "other", "credit_count": "1.00", "branch": "all"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(HalfDayScenario.objects.filter(description="Injected").exists())

    def test_employee_cannot_edit_half_day_scenario(self):
        resp = self._as(self.emp_user).post(
            reverse("edit-half-day-scenario", args=[self.scenario.pk]),
            {"scenario_date": "2026-05-01", "description": "Tampered",
             "scenario_type": "other", "credit_count": "1.00", "branch": "all",
             "is_approved": "on"},
        )
        self.assertEqual(resp.status_code, 403)
        self.scenario.refresh_from_db()
        self.assertEqual(self.scenario.description, "Original")
        self.assertEqual(self.scenario.credit_count, Decimal("0.50"))

    def test_super_admin_can_still_save_holiday_settings(self):
        # A global-access user has no employee profile, so the view takes the
        # company from company_id rather than from get_user_company().
        resp = self._as(self.super_user).post(
            reverse("save-holiday-settings"),
            {"financial_year_start_month": "1", "branch_specific_holidays": "false",
             "company_id": str(self.company.pk)},
        )
        self.assertNotEqual(resp.status_code, 403)
        self.settings.refresh_from_db()
        self.assertEqual(self.settings.financial_year_start_month, 1)

    def test_super_admin_can_still_edit_earned_leave(self):
        resp = self._as(self.super_user).post(
            reverse("edit-earned-leave", args=[self.earned_leave.pk]),
            {"earned_leaves": "3.5", "is_auto_generated": "off"},
        )
        self.assertNotEqual(resp.status_code, 403)
        self.earned_leave.refresh_from_db()
        self.assertEqual(self.earned_leave.earned_leaves, Decimal("3.50"))

    def test_super_admin_can_still_add_half_day_scenario(self):
        resp = self._as(self.super_user).post(
            reverse("add-half-day-scenario"),
            {"scenario_date": "2026-06-01", "description": "Legitimate",
             "scenario_type": "other", "credit_count": "0.50", "branch": "all"},
        )
        self.assertNotEqual(resp.status_code, 403)
        self.assertTrue(HalfDayScenario.objects.filter(description="Legitimate").exists())

    def test_super_admin_can_still_edit_half_day_scenario(self):
        resp = self._as(self.super_user).post(
            reverse("edit-half-day-scenario", args=[self.scenario.pk]),
            {"scenario_date": "2026-05-01", "description": "Updated",
             "scenario_type": "other", "credit_count": "0.50", "branch": "all"},
        )
        self.assertNotEqual(resp.status_code, 403)
        self.scenario.refresh_from_db()
        self.assertEqual(self.scenario.description, "Updated")

    # ── holiday calendar reads stay open ─────────────────────────────────

    def test_employee_can_still_read_the_holiday_calendar(self):
        """These are open on purpose -- holiday_calendar is registered with
        has_view=False precisely so employees can see their holidays."""
        client = self._as(self.emp_user)
        for name in ("holiday-list", "api-holidays", "holiday-calendar"):
            with self.subTest(endpoint=name):
                # holiday_list redirects to the calendar tab rather than
                # rendering on its own, so the assertion is "not forbidden",
                # which is the property being protected here.
                resp = client.get(reverse(name))
                self.assertIn(resp.status_code, (200, 302))
                self.assertNotEqual(resp.status_code, 403)
                if resp.status_code == 302:
                    self.assertNotIn("/login", resp["Location"])

    # ── branch ───────────────────────────────────────────────────────────

    def test_employee_cannot_edit_branch(self):
        resp = self._as(self.emp_user).post(
            reverse("edit_branch", args=[self.branch.pk]),
            {"branch_name": "Hijacked", "branch_address": "Elsewhere"},
        )
        self.assertEqual(resp.status_code, 403)
        self.branch.refresh_from_db()
        self.assertEqual(self.branch.branch_name, "Main")

    def test_employee_cannot_read_branch_via_get_branch(self):
        resp = self._as(self.emp_user).get(reverse("get_branch", args=[self.branch.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_hr_can_still_edit_and_read_branch(self):
        client = self._as(self.hr_user)
        self.assertNotEqual(
            client.get(reverse("edit_branch", args=[self.branch.pk])).status_code, 403,
        )
        self.assertEqual(client.get(reverse("get_branch", args=[self.branch.pk])).status_code, 200)

    # ── offboarding ──────────────────────────────────────────────────────

    def test_employee_cannot_read_offboarding_detail(self):
        resp = self._as(self.emp_user).get(
            reverse("offboarding-detail", args=[self.offboarding.pk]),
        )
        self.assertEqual(resp.status_code, 403)

    def test_employee_cannot_read_offboarding_edit_data(self):
        resp = self._as(self.emp_user).get(
            reverse("offboarding-edit-data", args=[self.offboarding.pk]),
        )
        self.assertEqual(resp.status_code, 403)

    def test_hr_can_still_read_offboarding_detail(self):
        client = self._as(self.hr_user)
        self.assertEqual(
            client.get(reverse("offboarding-detail", args=[self.offboarding.pk])).status_code, 200,
        )
        self.assertEqual(
            client.get(reverse("offboarding-edit-data", args=[self.offboarding.pk])).status_code, 200,
        )

    # ── shift roster ─────────────────────────────────────────────────────

    def test_employee_cannot_read_shift_assignment_api(self):
        resp = self._as(self.emp_user).get(
            reverse("api_get_shift_assignment", args=[self.shift.pk]),
        )
        self.assertEqual(resp.status_code, 403)

    def test_hr_can_still_read_shift_assignment_api(self):
        resp = self._as(self.hr_user).get(
            reverse("api_get_shift_assignment", args=[self.shift.pk]),
        )
        self.assertEqual(resp.status_code, 200)

    # ── employee leave history ───────────────────────────────────────────

    def test_employee_cannot_read_another_employees_leave_history(self):
        resp = self._as(self.emp_user).get(
            reverse("employee_leave_history", args=[self.other.pk]),
        )
        self.assertEqual(resp.status_code, 403)

    def test_employee_can_read_own_leave_history(self):
        LeaveBalanceHistory.objects.create(employee=self.employee, month=date(2026, 4, 1))
        resp = self._as(self.emp_user).get(
            reverse("employee_leave_history", args=[self.employee.pk]),
        )
        self.assertEqual(resp.status_code, 200)

    def test_hr_can_read_any_employees_leave_history(self):
        resp = self._as(self.hr_user).get(
            reverse("employee_leave_history", args=[self.other.pk]),
        )
        self.assertEqual(resp.status_code, 200)
