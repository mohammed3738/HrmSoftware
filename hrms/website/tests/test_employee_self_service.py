"""
What an Employee can see and reach.

Two halves:
  * the correction-request and comp-off lists scope to the viewer -- staff
    see the whole company's, an employee sees only the ones they raised, so
    following your own request needs no company-wide grant;
  * the nav offers an employee exactly the pages they can open, and nothing
    that would 403 on click.

Run with: python manage.py test website.tests.test_employee_self_service
"""
from datetime import date, time

from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse

from website.models import (
    Attendance, AttendanceCorrectionRequest, Company, CompOffRequest, Employee,
    PayrollSettings,
)

WORK_DAY = date(2026, 6, 1)  # a Monday

# Nav items an employee must never be offered: every one of these points at
# a staff-gated page.
STAFF_ONLY_NAV = [
    "Add Employee",
    "Download Employee List",
    "Employee Offboarding",
    "Attendance List",
    "Upload Attendance (Excel)",
    "Attendance Correction",
    "Shift Roster",
    "Attendance Register",
    "Leave Credit Policy",
    "Recalculate Leaves",
    "Create Salary Structure",
    "Salary History",
    "Salary Increment",
    "Late Attendance Review",
    "Payroll Run",
    "Entity",
    "Branch",
    "Departments",
]

# ...and the ones they must be offered.
SELF_SERVICE_NAV = [
    "My Attendance",
    "Leave Apply",
    "Leave Balance",
    "Attendance Correction Request Status",
    "Comp-Off Request Status",
    "All Advances",
]


def make_employee(company, code, user=None, first_name="Self"):
    return Employee.objects.create(
        company=company, user=user, salutation="Mr", first_name=first_name, last_name="Service",
        father_name="Father", gender="Male", date_of_birth=date(1990, 1, 1),
        personal_email=f"{code}@test.com", personal_mobile="1234567890",
        employee_code=code, designation="Dev", department="IT",
        date_of_joining=date(2020, 1, 1), status="Active", force_password_change=False,
    )


class EmployeeSelfServiceTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="SLF", name="Self Service Co", phone="1", email="slf@test.com", address="Addr",
        )
        PayrollSettings.objects.create(company=self.company)

        self.user = User.objects.create_user(username="slf_emp", password="pass12345")
        self.user.groups.add(Group.objects.get(name="Employee"))
        self.employee = make_employee(self.company, "SLF001", user=self.user)
        self.colleague = make_employee(self.company, "SLF002", first_name="Colleague")

        self.attendance = Attendance.objects.create(
            employee=self.employee, date=WORK_DAY, in_time=time(10, 0), out_time=time(17, 0),
        )
        colleague_attendance = Attendance.objects.create(
            employee=self.colleague, date=WORK_DAY, in_time=time(10, 0), out_time=time(17, 0),
        )

        self.my_correction = AttendanceCorrectionRequest.objects.create(
            attendance=self.attendance, old_in_time=time(10, 0), old_out_time=time(17, 0),
            new_in_time=time(9, 0), new_out_time=time(18, 0), reason="mine",
        )
        self.colleagues_correction = AttendanceCorrectionRequest.objects.create(
            attendance=colleague_attendance, old_in_time=time(10, 0), old_out_time=time(17, 0),
            new_in_time=time(9, 0), new_out_time=time(18, 0), reason="theirs",
        )

        self.my_compoff = CompOffRequest.objects.create(
            employee=self.employee, from_date=WORK_DAY, to_date=WORK_DAY, count=1, reason="mine",
        )
        self.colleagues_compoff = CompOffRequest.objects.create(
            employee=self.colleague, from_date=WORK_DAY, to_date=WORK_DAY, count=1, reason="theirs",
        )

        self.client = Client()
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    # ── own requests, and only their own ──────────────────────────────

    def test_employee_sees_only_the_corrections_they_raised(self):
        resp = self.client.get(reverse("attendance_correction_requests_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["can_see_all_requests"])
        codes = {row["emp_code"] for row in resp.context["attendance_requests"]}
        self.assertEqual(codes, {"SLF001"})

    def test_employee_sees_only_their_own_compoffs(self):
        resp = self.client.get(reverse("comp_off_requests_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["can_see_all_requests"])
        names = {row.get("emp_code") or row.get("employee_code") for row in resp.context["comp_off_requests"]}
        self.assertNotIn("SLF002", names)

    def test_the_pages_are_titled_for_the_viewer(self):
        self.assertContains(self.client.get(reverse("attendance_correction_requests_list")),
                            "My Correction Requests")
        self.assertContains(self.client.get(reverse("comp_off_requests_list")),
                            "My Comp-Off Requests")

    def test_staff_still_see_every_request(self):
        hr = User.objects.create_user(username="slf_hr", password="pass12345")
        hr.groups.add(Group.objects.get(name="HR"))
        client = Client()
        client.force_login(hr, backend="django.contrib.auth.backends.ModelBackend")

        resp = client.get(reverse("attendance_correction_requests_list"))
        self.assertTrue(resp.context["can_see_all_requests"])
        codes = {row["emp_code"] for row in resp.context["attendance_requests"]}
        self.assertEqual(codes, {"SLF001", "SLF002"})
        self.assertContains(resp, "Attendance Correction Requests List")

    def test_a_login_with_no_employee_record_is_refused(self):
        bare = User.objects.create_user(username="slf_bare", password="pass12345")
        bare.groups.add(Group.objects.get(name="Employee"))
        client = Client()
        client.force_login(bare, backend="django.contrib.auth.backends.ModelBackend")
        self.assertEqual(client.get(reverse("comp_off_requests_list")).status_code, 403)

    # ── my_attendance shortcut ────────────────────────────────────────

    def test_my_attendance_lands_on_the_users_own_record(self):
        resp = self.client.get(reverse("my_attendance"))
        self.assertRedirects(
            resp, reverse("employee_attendance_detail", args=[self.employee.pk]),
            fetch_redirect_response=False,
        )

    # ── the nav an employee actually gets ─────────────────────────────

    def test_nav_offers_the_self_service_pages(self):
        resp = self.client.get(reverse("employee-dashboard"))
        for item in SELF_SERVICE_NAV:
            self.assertContains(resp, "<div>%s</div>" % item, html=False, msg_prefix=item)

    def test_nav_hides_every_staff_only_page(self):
        """A menu item that 403s on click is worse than no menu item."""
        resp = self.client.get(reverse("employee-dashboard"))
        offered = [item for item in STAFF_ONLY_NAV
                   if "<div>%s</div>" % item in resp.content.decode("utf-8", "ignore")]
        self.assertEqual(offered, [], "employee was offered: %s" % offered)

    def test_the_hidden_pages_really_do_refuse_an_employee(self):
        """Proves the nav is hiding them for a reason, not out of caution."""
        for url_name in ("employee_list", "attendance", "shift_roster_list",
                         "attendance-register", "leave_credit_policy",
                         "payroll-run-list", "create-company"):
            self.assertEqual(
                self.client.get(reverse(url_name)).status_code, 403, url_name,
            )
