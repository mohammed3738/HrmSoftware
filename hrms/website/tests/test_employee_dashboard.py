"""
Regression tests for the Employee Dashboard (self-service landing page for
Employee-role logins, reached via login and the "Dashboards" nav link) and
my_profile, which sends the logged-in user to their own employee_detail
profile page ("My Profile" in the nav) -- these are two distinct
destinations for two distinct nav items.

Run with: python manage.py test website.tests.test_employee_dashboard
"""
from datetime import date, time, timedelta

from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from website.models import (
    Company, Employee, Attendance, LeaveBalance, Holiday, HolidayType, BiometricPunch, ShiftAssignment,
    PayrollRun, PayrollRecord, Branch, LeaveApplication, AttendanceCorrectionRequest, CompOffRequest, EmployeeChangeRequest,
)


class EmployeeDashboardTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="EDT", name="Emp Dashboard Test Co", phone="1", email="edt@test.com", address="Addr",
        )
        self.branch = Branch.objects.create(branch_name="Main Branch")
        self.user = User.objects.create_user(username="emp_dash_user", password="pass12345")
        self.user.groups.add(Group.objects.get(name="Employee"))

        self.employee = Employee.objects.create(
            company=self.company, branch=self.branch, user=self.user,
            salutation="Mr", first_name="Dash", last_name="Board",
            father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email="dash@test.com", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890", employee_code="EDT001",
            designation="Developer", department="IT", date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Dash",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active", force_password_change=False,
        )
        self.client = Client()
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def test_dashboard_loads_and_shows_own_data_only(self):
        Attendance.objects.create(employee=self.employee, date=date.today(), in_time=time(9, 0), out_time=time(18, 0))
        resp = self.client.get(reverse("employee-dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["employee"].id, self.employee.id)

    def test_department_roster_and_company_absence_have_distinct_scopes(self):
        from .test_role_dashboards import make_employee
        today = timezone.localdate()
        peer = make_employee(self.company, "ROSTER1", department=" it ")
        missing = make_employee(self.company, "ROSTER2", department="Finance")
        other = Company.objects.create(name="Elsewhere", short_name="ELS")
        outsider = make_employee(other, "ROSTER3", department="IT")
        Attendance.objects.create(employee=peer, date=today, in_time=time(9))
        Attendance.objects.create(employee=missing, date=today, status="Absent", status_overridden=True)
        response = self.client.get(reverse("employee-dashboard"))
        roster = {r.employee.pk: r.status for r in response.context["department_today"]}
        self.assertIn(peer.pk, roster)
        self.assertNotIn(missing.pk, roster)
        self.assertNotIn(outsider.pk, roster)
        absent = {person.pk for person in response.context["company_absent"]}
        self.assertIn(missing.pk, absent)
        self.assertNotIn(peer.pk, absent)
        self.assertNotIn(outsider.pk, absent)

    def test_dashboard_denies_user_with_no_employee_profile(self):
        bare_user = User.objects.create_user(username="no_profile_user", password="pass12345")
        client = Client()
        client.force_login(bare_user, backend="django.contrib.auth.backends.ModelBackend")
        resp = client.get(reverse("employee-dashboard"))
        self.assertEqual(resp.status_code, 302)  # redirected to login, not shown someone else's dashboard

    def test_today_card_distinguishes_placeholder_from_device_check_in(self):
        today = timezone.localdate()
        Attendance.objects.create(employee=self.employee, date=today, in_time=time.min,
                                  out_time=time.min, status="Absent", status_overridden=True)
        response = self.client.get(reverse("employee-dashboard"))
        self.assertIsNone(response.context["check_in"])
        self.assertIsNone(response.context["elapsed"])
        BiometricPunch.objects.create(employee=self.employee, device_user_id="EDT001",
                                      punch_date=today, punch_time=time(0, 1), direction="IN")
        response = self.client.get(reverse("employee-dashboard"))
        self.assertEqual(response.context["check_in"], time(0, 1))
        self.assertIsNone(response.context["check_out"])
        self.assertEqual(response.context["today_status"], "Checked in")

    def test_dashboard_request_link_opens_own_record_and_history(self):
        leave = LeaveApplication.objects.create(employee=self.employee, start_date=date.today(),
            end_date=date.today(), reason="Leave detail", status="Approved")
        link = reverse("employee-request-record", args=["leave", leave.pk])
        self.assertContains(self.client.get(reverse("employee-dashboard")), link)
        self.assertContains(self.client.get(link), "Leave detail")
        history = reverse("employee-request-history", args=["leave"])
        self.assertContains(self.client.get(history), "Leave detail")
        self.assertNotContains(self.client.get(history, {"status": "pending"}), "Leave detail")
        colleague = Employee.objects.create(company=self.company, first_name="Other", last_name="Employee", employee_code="OTHER123")
        leave.employee = colleague
        leave.save(update_fields=["employee"])
        self.assertEqual(self.client.get(link).status_code, 404)
        self.assertNotContains(self.client.get(history), "Leave detail")

    def test_monthly_team_request_history_includes_both_reporting_relationships(self):
        from .test_role_dashboards import make_employee
        lead = make_employee(self.company, "RH1", manager=self.employee)
        report = make_employee(self.company, "RH2", reporting_person=self.employee)
        outsider = make_employee(self.company, "RH3")
        for person, status in [(lead, "Approved"), (report, "Rejected"), (outsider, "Pending")]:
            LeaveApplication.objects.create(employee=person, start_date=date(2026, 6, 30),
                end_date=date(2026, 7, 2), status=status, reason=person.employee_code)
        path = reverse("employee-request-history", args=["leave"])
        filters = {"scope": "team", "month": "2026-07"}
        response = self.client.get(path, filters)
        self.assertEqual({r.employee_id for r in response.context["page"]}, {lead.pk, report.pk})
        rejected = self.client.get(path, {**filters, "status": "rejected"})
        self.assertEqual([r.employee_id for r in rejected.context["page"]], [report.pk])
        self.assertFalse(list(self.client.get(path, {**filters, "month": "2026-08"}).context["page"]))
        self.assertFalse(list(self.client.get(path).context["page"]))
        record = outsider.leaveapplication_set.get()
        self.assertEqual(self.client.get(reverse("employee-request-record", args=["leave", record.pk]),
                                        {"scope": "team"}).status_code, 404)

    def test_requests_show_correction_comp_off_and_profile_review_details(self):
        attendance = Attendance.objects.create(employee=self.employee, date=date.today())
        correction = AttendanceCorrectionRequest.objects.create(attendance=attendance, reason="Missed checkout",
            old_in_time=time(9), new_out_time=time(18), status="Rejected", rejection_reason="Missing evidence")
        comp_off = CompOffRequest.objects.create(employee=self.employee, from_date=date.today(),
            to_date=date.today(), reason="Weekend release")
        change = EmployeeChangeRequest.objects.create(employee=self.employee, status="approved", decision_note="Confirmed")
        for kind, row, expected in [("correction", correction, "Missing evidence"), ("comp-off", comp_off, "Weekend release"),
                                    ("profile", change, "Confirmed")]:
            response = self.client.get(reverse("employee-request-record", args=[kind, row.pk]))
            self.assertContains(response, expected)

    def test_team_leave_groups_overlaps_and_limits_preview(self):
        today = timezone.localdate()
        people = []
        for index in range(5):
            person = Employee.objects.create(company=self.company, first_name=f"Teammate{index}",
                last_name="Smith", employee_code=f"TEAM{index}", status="Active")
            Employee.objects.filter(pk=person.pk).update(manager=self.employee if index < 4 else None)
            LeaveApplication.objects.create(employee=person, start_date=today, end_date=today, status="Approved")
            people.append(person)
        latest = today + timedelta(days=2)
        LeaveApplication.objects.create(employee=people[0], start_date=today, end_date=latest, status="Approved")
        LeaveApplication.objects.create(employee=people[0], start_date=today, end_date=latest + timedelta(days=1))
        response = self.client.get(reverse("employee-dashboard"))
        rows = list(response.context["team_leave_today"])
        self.assertEqual([row.pk for row in rows], [person.pk for person in people[:4]])
        self.assertEqual(rows[0].leave_through, latest)
        self.assertContains(response, "More teammates (1)")

    def test_punch_in_overrides_approved_leave_across_dashboard_cards(self):
        from .test_role_dashboards import make_employee
        today = timezone.localdate()
        people = [make_employee(self.company, f"CHECK{i}", manager=self.employee, department="IT")
                  for i in range(3)]
        for person in people:
            LeaveApplication.objects.create(employee=person, start_date=today, end_date=today, status="Approved")
        Attendance.objects.create(employee=people[0], date=today, in_time=time(9),
                                  status="Half Day", status_overridden=True)
        BiometricPunch.objects.create(employee=people[1], device_user_id="CHECK1", punch_date=today,
                                      punch_time=time(9), direction="IN")
        response = self.client.get(reverse("employee-dashboard"))
        self.assertEqual([p.pk for p in response.context["team_leave_today"]], [people[2].pk])
        roster = {row.employee.pk: row.status for row in response.context["department_today"]}
        self.assertEqual([roster[p.pk] for p in people], ["Present", "Present", "Absent"])
        self.assertFalse({people[0].pk, people[1].pk} & {p.pk for p in response.context["company_absent"]})
        self.assertContains(response, response.context["daily_quote"])

    def test_daily_quotes_are_distinct_through_a_leap_year(self):
        from website.daily_quotes import daily_work_quote
        first = date(2028, 1, 1)
        self.assertEqual(len({daily_work_quote(first + timedelta(days=i)) for i in range(366)}), 366)

    def test_today_card_orders_recent_punches_and_uses_latest_receipt(self):
        today = timezone.localdate()
        ShiftAssignment.objects.create(employee=self.employee, shift_name="General", start_date=today,
            end_date=today, shift_start_time=time(9), shift_end_time=time(18, 30))
        Attendance.objects.create(employee=self.employee, date=today, in_time=time(9), out_time=time(16))
        for hour in [12, 13, 16, 9]:
            punch = BiometricPunch.objects.create(employee=self.employee, device_user_id="EDT001",
                punch_date=today, punch_time=time(hour))
        response = self.client.get(reverse("employee-dashboard"))
        self.assertEqual([p.punch_time.hour for p in response.context["today_punches"]], [12, 13, 16])
        self.assertEqual(response.context["last_punch_received"], punch.received_at)
        self.assertContains(response, "of 9h 30m")

    def test_leave_balance_shown_when_present(self):
        LeaveBalance.objects.create(
            employee=self.employee, period_from_date=date(2026, 1, 1), period_to_date=date(2026, 1, 31),
            final_leave_balance=12,
        )
        # Hidden from the employee until payroll has been run for the period.
        resp = self.client.get(reverse("employee-dashboard"))
        self.assertIsNone(resp.context["leave_balance"])
        PayrollRun.objects.create(company=self.employee.company, month=date(2026, 1, 1),
                                  start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
        resp = self.client.get(reverse("employee-dashboard"))
        self.assertEqual(resp.context["leave_balance"].final_leave_balance, 12)

        application = self.client.get(reverse("leave_apply"))
        self.assertEqual(application.context["balance"].pk, resp.context["leave_balance"].pk)

    def test_upcoming_holiday_shown_when_applicable(self):
        htype = HolidayType.objects.create(name="National", type_category="national")
        user_admin = User.objects.create_superuser("holiday_admin", "ha@test.com", "pass12345")
        Holiday.objects.create(
            holiday_date=date.today().replace(year=date.today().year + 1),
            name="Future Holiday", holiday_type=htype, created_by=user_admin,
        )
        resp = self.client.get(reverse("employee-dashboard"))
        names = [h.name for h in resp.context["upcoming_holidays"]]
        self.assertIn("Future Holiday", names)

    def test_only_finalized_payslips_shown(self):
        draft_run = PayrollRun.objects.create(
            company=self.company, month=date(2026, 1, 1), start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
            status=PayrollRun.STATUS_DRAFT,
        )
        PayrollRecord.objects.create(payroll=draft_run, employee=self.employee, employee_code="EDT001")
        finalized_run = PayrollRun.objects.create(
            company=self.company, month=date(2026, 2, 1), start_date=date(2026, 2, 1), end_date=date(2026, 2, 28),
            status=PayrollRun.STATUS_FINALIZED,
        )
        PayrollRecord.objects.create(payroll=finalized_run, employee=self.employee, employee_code="EDT001")

        resp = self.client.get(reverse("employee-dashboard"))
        self.assertEqual(resp.context["recent_payslips"].count(), 1)
        self.assertEqual(resp.context["recent_payslips"].first().payroll.status, PayrollRun.STATUS_FINALIZED)

    def test_login_redirects_employee_to_dashboard(self):
        client = Client()
        resp = client.post(reverse("login"), {"username": "emp_dash_user", "password": "pass12345"})
        self.assertRedirects(resp, reverse("employee-dashboard"))

    def test_my_profile_redirects_to_own_employee_detail_page(self):
        resp = self.client.get(reverse("my_profile"))
        self.assertRedirects(resp, reverse("employee_detail", args=[self.employee.pk]))

    def test_absent_employees_today_lists_absentees_of_every_company(self):
        other_company = Company.objects.create(
            short_name="OTH", name="Other Co", phone="1", email="oth@test.com", address="Addr",
        )
        absent_colleague = Employee.objects.create(
            company=self.company, branch=self.branch,
            salutation="Ms", first_name="Ann", last_name="Absent",
            father_name="Father", gender="Female", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email="ann@test.com", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890", employee_code="EDT002",
            designation="Developer", department="IT", date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Ann",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
        )
        Attendance.objects.create(employee=absent_colleague, date=date.today(), status="Absent", status_overridden=True)

        # Absentees of every company in the group are listed, not only this one.
        other_branch = Branch.objects.create(branch_name="Other Branch")
        other_company_employee = Employee.objects.create(
            company=other_company, branch=other_branch,
            salutation="Mr", first_name="Far", last_name="Away",
            father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email="far@test.com", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890", employee_code="OTH001",
            designation="Developer", department="IT", date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Far",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
        )
        Attendance.objects.create(employee=other_company_employee, date=date.today(), status="Absent", status_overridden=True)

        resp = self.client.get(reverse("employee-dashboard"))
        codes = [a.employee.employee_code for a in resp.context["absent_employees_today"]]
        self.assertIn("EDT002", codes)
        self.assertNotIn(absent_colleague.pk, [a.employee.pk for a in resp.context["team_absences_today"]])
        absent_colleague.manager = self.employee
        absent_colleague.save(update_fields=["manager"])
        resp = self.client.get(reverse("employee-dashboard"))
        codes = [a.employee.employee_code for a in resp.context["absent_employees_today"]]
        self.assertIn("EDT002", codes)
        self.assertIn("OTH001", codes)
