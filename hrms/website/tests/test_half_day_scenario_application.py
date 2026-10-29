"""
Regression tests for how a half-day scenario reaches an employee's
attendance.

HalfDayScenario had no test coverage at all before this file, and the two
defects below both change a day's `count`, which is what payroll pro-rates
against -- so each of them is a pay difference, not a display nicety.

1. "All Branches" scenarios never applied to anyone with a branch.
   add_half_day_scenario() stores branch=None for the "All Branches" option
   and labels it so in the success message. Attendance.get_half_day_scenario()
   looked it up with

       HalfDayScenario.objects.filter(branch=branch, ...)

   which for an employee in branch 5 is `branch_id = 5` and never matches
   the branch_id IS NULL row. So picking "All Branches" silently applied the
   scenario to nobody except employees who had no branch -- and those were
   excluded too, by defect 2. The model's own partial unique constraints
   (models.py:1610,1615) treat branch=NULL as its own distinct scope, which
   is what tells you NULL was meant to mean "all branches" rather than "no
   branch".

2. Employees with no branch skipped holiday and half-day evaluation
   entirely. Both STEP 1 and STEP 2 of calculate_status() sat inside
   `if branch:`, so for an employee whose `branch` is NULL -- a nullable
   field, and 2 of the 104 employees in the working database are in that
   state -- a national holiday was computed as an ordinary working day:
   no punch, therefore Absent with count 0.00 instead of Holiday with
   count 1.00. Holiday.is_applicable_to_branch() already handles a None
   branch deliberately (`branch is not None and branch.pk in selected`),
   so the guard was the only thing in the way.

A branch-specific scenario still wins over an all-branches one for the same
day, which is the only sensible reading of having both.

Run with:
    python manage.py test website.tests.test_half_day_scenario_application
"""
from datetime import date, time
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from website.models import (
    Attendance,
    Branch,
    Company,
    Employee,
    HalfDayScenario,
    Holiday,
    HolidayType,
    PayrollSettings,
    attendance_rule_cache,
)

WORKDAY = date(2026, 5, 20)        # a Wednesday
HOLIDAY_DAY = date(2026, 5, 21)    # a Thursday


class HalfDayScenarioApplicationTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="HDS", name="Half Day Co", phone="1",
            email="hds@test.com", address="Addr",
        )
        PayrollSettings.objects.create(company=self.company, weekend_days="sun")
        self.branch = Branch.objects.create(branch_name="Pune")
        self.other_branch = Branch.objects.create(branch_name="Nashik")
        self.author = User.objects.create_superuser("hds_admin", "hds@test.com", "pass12345")

        self.branched = self._employee("HDS001", "Branched", branch=self.branch)
        self.branchless = self._employee("HDS002", "Branchless", branch=None)

    def _employee(self, code, first_name, branch):
        return Employee.objects.create(
            company=self.company, branch=branch, salutation="Mr",
            first_name=first_name, last_name="Doe", father_name="Father",
            gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email=f"{code}@test.com",
            present_address="Addr", permanent_address="Addr",
            personal_mobile="1234567890", employee_code=code, designation="Dev",
            department="IT", date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank=first_name,
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
            force_password_change=False,
        )

    def _scenario(self, branch, credit=Decimal("0.50"), day=WORKDAY, description="Heavy rain"):
        return HalfDayScenario.objects.create(
            branch=branch, scenario_date=day, scenario_type="rain_closure",
            description=description, credit_count=credit, is_approved=True,
            created_by=self.author,
        )

    def _attendance(self, employee, day=WORKDAY, worked=True):
        with attendance_rule_cache():
            return Attendance.objects.create(
                employee=employee, date=day,
                in_time=time(9, 0) if worked else None,
                out_time=time(18, 0) if worked else None,
            )

    # ── defect 1: "All Branches" scenarios ───────────────────────────────

    def test_all_branches_scenario_applies_to_an_employee_with_a_branch(self):
        self._scenario(branch=None, credit=Decimal("0.50"))
        attendance = self._attendance(self.branched)
        self.assertEqual(attendance.status, "Present (Half-Day)")
        self.assertEqual(attendance.count, Decimal("0.50"))

    def test_all_branches_scenario_applies_to_an_employee_with_no_branch(self):
        self._scenario(branch=None, credit=Decimal("0.50"))
        attendance = self._attendance(self.branchless)
        self.assertEqual(attendance.status, "Present (Half-Day)")
        self.assertEqual(attendance.count, Decimal("0.50"))

    def test_branch_specific_scenario_still_applies_to_that_branch(self):
        self._scenario(branch=self.branch, credit=Decimal("0.50"))
        attendance = self._attendance(self.branched)
        self.assertEqual(attendance.status, "Present (Half-Day)")
        self.assertEqual(attendance.count, Decimal("0.50"))

    def test_another_branchs_scenario_does_not_apply(self):
        self._scenario(branch=self.other_branch, credit=Decimal("0.50"))
        attendance = self._attendance(self.branched)
        self.assertEqual(attendance.status, "Present")
        self.assertEqual(attendance.count, Decimal("1.00"))

    def test_branch_specific_scenario_wins_over_an_all_branches_one(self):
        self._scenario(branch=None, credit=Decimal("0.50"), description="All branches")
        self._scenario(branch=self.branch, credit=Decimal("0.75"), description="Pune only")
        attendance = self._attendance(self.branched)
        self.assertEqual(attendance.count, Decimal("0.75"))
        self.assertEqual(attendance.half_day_scenario.description, "Pune only")

    def test_unapproved_scenario_is_ignored(self):
        scenario = self._scenario(branch=None)
        scenario.is_approved = False
        scenario.save(update_fields=["is_approved"])
        attendance = self._attendance(self.branched)
        self.assertEqual(attendance.status, "Present")

    # ── defect 2: employees with no branch ───────────────────────────────

    def test_national_holiday_credits_an_employee_with_no_branch(self):
        holiday_type = HolidayType.objects.create(name="National", type_category="national")
        Holiday.objects.create(
            holiday_date=HOLIDAY_DAY, name="Test National Day",
            holiday_type=holiday_type, status="declared", is_national=True,
            created_by=self.author,
        )
        attendance = self._attendance(self.branchless, day=HOLIDAY_DAY, worked=False)
        self.assertEqual(attendance.status, "Holiday")
        self.assertEqual(attendance.count, Decimal("1.00"))

    def test_national_holiday_still_credits_an_employee_with_a_branch(self):
        holiday_type = HolidayType.objects.create(name="National", type_category="national")
        Holiday.objects.create(
            holiday_date=HOLIDAY_DAY, name="Test National Day",
            holiday_type=holiday_type, status="declared", is_national=True,
            created_by=self.author,
        )
        attendance = self._attendance(self.branched, day=HOLIDAY_DAY, worked=False)
        self.assertEqual(attendance.status, "Holiday")
        self.assertEqual(attendance.count, Decimal("1.00"))

    def test_branch_scoped_holiday_does_not_reach_a_branchless_employee(self):
        """is_applicable_to_branch() returns False for branch=None when the
        holiday names specific branches -- that part was already correct and
        must stay that way."""
        holiday_type = HolidayType.objects.create(name="Regional", type_category="regional")
        holiday = Holiday.objects.create(
            holiday_date=HOLIDAY_DAY, name="Pune Only Day",
            holiday_type=holiday_type, status="declared", is_national=False,
            created_by=self.author,
        )
        holiday.branches.set([self.branch])
        attendance = self._attendance(self.branchless, day=HOLIDAY_DAY, worked=False)
        self.assertEqual(attendance.status, "Absent")
        self.assertEqual(attendance.count, Decimal("0.00"))

    def test_a_branchless_employee_who_worked_is_unaffected(self):
        attendance = self._attendance(self.branchless)
        self.assertEqual(attendance.status, "Present")
        self.assertEqual(attendance.count, Decimal("1.00"))
