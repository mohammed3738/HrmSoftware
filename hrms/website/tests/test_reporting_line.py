"""
Regression tests for departments and the reporting line.

Two halves:
  * Department defines a reporting person and a manager; employees inherit
    both unless individually overridden (use_department_defaults), because
    departments aren't uniform -- most of Sales may report to one person
    while a handful report to someone else.
  * Those approvers can then actually approve/reject their reportees'
    leave, comp-off and attendance-correction requests, without holding the
    Admin/HR/Manager role -- and crucially cannot touch anyone else's.

Run with: python manage.py test website.tests.test_reporting_line
"""
from datetime import date, time

from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse

from website.models import (
    Attendance, AttendanceCorrectionRequest, Company, CompOffRequest, Department,
    Employee, LeaveApplication, PayrollSettings,
)

WORK_DAY = date(2026, 6, 1)  # a Monday


def make_employee(company, code, first_name, **kwargs):
    """Employee fixtures pass user= explicitly: the sync_user signal
    otherwise provisions a login of its own on every save."""
    return Employee.objects.create(
        company=company, salutation="Mr", first_name=first_name, last_name="Test",
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


class DepartmentReportingDefaultsTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="RL", name="Reporting Line Co", phone="1", email="rl@test.com", address="Addr",
        )
        PayrollSettings.objects.create(company=self.company)

        self.abc = make_employee(self.company, "RL_ABC", "Abc", department="Sales")
        self.xyz = make_employee(self.company, "RL_XYZ", "Xyz", department="Sales")
        self.sales = Department.objects.create(
            name="Sales", reporting_person=self.abc, manager=self.xyz,
        )

    def test_employee_inherits_department_reporting_person_and_manager(self):
        emp = make_employee(self.company, "RL001", "Sam", department="Sales")
        self.assertEqual(emp.reporting_person, self.abc)
        self.assertEqual(emp.manager, self.xyz)

    def test_department_name_match_is_case_insensitive(self):
        emp = make_employee(self.company, "RL002", "Case", department="sales")
        self.assertEqual(emp.reporting_person, self.abc)

    def test_individual_override_survives_when_defaults_are_off(self):
        """The whole reason the checkbox exists: a few people in a
        department report to somebody else."""
        other = make_employee(self.company, "RL_OTHER", "Other", department="Sales")
        emp = make_employee(
            self.company, "RL003", "Odd", department="Sales",
            use_department_defaults=False, reporting_person=other, manager=other,
        )
        self.assertEqual(emp.reporting_person, other)
        self.assertEqual(emp.manager, other)

    def test_changing_the_department_resyncs_followers_but_not_overrides(self):
        follower = make_employee(self.company, "RL004", "Follower", department="Sales")
        odd = make_employee(
            self.company, "RL005", "Odd", department="Sales",
            use_department_defaults=False, reporting_person=self.xyz, manager=self.xyz,
        )

        new_lead = make_employee(self.company, "RL_NEW", "NewLead", department="Sales")
        self.sales.reporting_person = new_lead
        self.sales.save()

        follower.refresh_from_db()
        odd.refresh_from_db()
        self.assertEqual(follower.reporting_person, new_lead)
        self.assertEqual(odd.reporting_person, self.xyz)  # untouched

    def test_reporting_person_is_not_made_their_own_approver(self):
        """The reporting person is usually a member of the department they
        sign off for, and the department re-sync would otherwise point them
        at themselves."""
        self.sales.save()  # triggers sync_employees over the whole department
        self.abc.refresh_from_db()
        self.assertIsNone(self.abc.reporting_person)

    def test_department_and_manager_may_be_the_same_person(self):
        Department.objects.create(name="Solo", reporting_person=self.abc, manager=self.abc)
        emp = make_employee(self.company, "RL006", "Solo", department="Solo")
        self.assertEqual(emp.reporting_person, self.abc)
        self.assertEqual(emp.manager, self.abc)

    def test_free_text_department_with_no_record_leaves_approvers_unset(self):
        emp = make_employee(self.company, "RL007", "Legacy", department="Some Old Team")
        self.assertIsNone(emp.reporting_person)
        self.assertIsNone(emp.manager)


class ReportingPersonApprovalTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="RLA", name="Reporting Approval Co", phone="1", email="rla@test.com", address="Addr",
        )
        PayrollSettings.objects.create(company=self.company)

        # The reporting person is a plain Employee-role login -- no
        # Admin/HR/Manager group, so the only thing granting them approval
        # rights is the reporting line itself.
        self.lead_user = User.objects.create_user(username="rla_lead", password="pass12345")
        self.lead_user.groups.add(Group.objects.get(name="Employee"))
        self.lead = make_employee(self.company, "RLA_LEAD", "Lead", user=self.lead_user)

        self.sales = Department.objects.create(name="Sales", reporting_person=self.lead, manager=self.lead)

        self.reportee = make_employee(self.company, "RLA001", "Reportee", department="Sales")
        self.outsider = make_employee(self.company, "RLA002", "Outsider", department="Engineering")

    def _client_as(self, user):
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return client

    def _leave_for(self, employee):
        return LeaveApplication.objects.create(
            employee=employee, leave_type="CL", start_date=WORK_DAY, end_date=WORK_DAY,
            reason="Personal", status="Pending",
        )

    def _correction_for(self, employee):
        attendance = Attendance.objects.create(
            employee=employee, date=WORK_DAY, in_time=time(10, 0), out_time=time(17, 0),
        )
        return AttendanceCorrectionRequest.objects.create(
            attendance=attendance, old_in_time=attendance.in_time, old_out_time=attendance.out_time,
            new_in_time=attendance.in_time, new_out_time=attendance.out_time,
            reason="Late for a medical reason",
        )

    def test_reporting_person_can_approve_their_reportees_leave(self):
        leave = self._leave_for(self.reportee)
        resp = self._client_as(self.lead_user).post(reverse("approve_leave", args=[leave.id]))
        self.assertEqual(resp.status_code, 200)
        leave.refresh_from_db()
        self.assertEqual(leave.status, "Approved")

    def test_reporting_person_cannot_approve_someone_elses_leave(self):
        leave = self._leave_for(self.outsider)
        resp = self._client_as(self.lead_user).post(reverse("approve_leave", args=[leave.id]))
        self.assertEqual(resp.status_code, 400)
        leave.refresh_from_db()
        self.assertEqual(leave.status, "Pending")

    def test_reporting_person_can_approve_a_correction_with_a_status_decision(self):
        req = self._correction_for(self.reportee)
        resp = self._client_as(self.lead_user).post(
            reverse("approve_correction", args=[req.id]), {"status_decision": "Present"},
        )
        self.assertEqual(resp.status_code, 200)
        req.attendance.refresh_from_db()
        self.assertEqual(req.attendance.status, "Present")

    def test_reporting_person_cannot_approve_an_outsiders_correction(self):
        req = self._correction_for(self.outsider)
        resp = self._client_as(self.lead_user).post(reverse("approve_correction", args=[req.id]))
        self.assertEqual(resp.status_code, 400)
        req.refresh_from_db()
        self.assertEqual(req.status, "Pending")

    def test_reporting_person_can_approve_a_reportees_compoff(self):
        compoff = CompOffRequest.objects.create(
            employee=self.reportee, from_date=WORK_DAY, to_date=WORK_DAY,
            count=1, reason="Worked a weekend", status="Pending",
        )
        resp = self._client_as(self.lead_user).post(reverse("approve_compoff", args=[compoff.id]))
        self.assertEqual(resp.status_code, 200)
        compoff.refresh_from_db()
        self.assertEqual(compoff.status, "Approved")

    def test_plain_employee_with_no_reportees_is_locked_out_entirely(self):
        nobody_user = User.objects.create_user(username="rla_nobody", password="pass12345")
        nobody_user.groups.add(Group.objects.get(name="Employee"))
        make_employee(self.company, "RLA003", "Nobody", user=nobody_user)

        leave = self._leave_for(self.reportee)
        resp = self._client_as(nobody_user).post(reverse("approve_leave", args=[leave.id]))
        self.assertEqual(resp.status_code, 403)
        leave.refresh_from_db()
        self.assertEqual(leave.status, "Pending")

    def test_hr_keeps_blanket_approval_across_every_department(self):
        hr_user = User.objects.create_user(username="rla_hr", password="pass12345")
        hr_user.groups.add(Group.objects.get(name="HR"))
        leave = self._leave_for(self.outsider)
        resp = self._client_as(hr_user).post(reverse("approve_leave", args=[leave.id]))
        self.assertEqual(resp.status_code, 200)
        leave.refresh_from_db()
        self.assertEqual(leave.status, "Approved")

    def test_bulk_approve_skips_requests_outside_the_reporting_line(self):
        mine = self._leave_for(self.reportee)
        theirs = self._leave_for(self.outsider)
        resp = self._client_as(self.lead_user).post(
            reverse("bulk_approve_leave"),
            data={"ids": [mine.id, theirs.id]},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["approved"], [mine.id])
        self.assertEqual([f["id"] for f in data["failed"]], [theirs.id])

        mine.refresh_from_db()
        theirs.refresh_from_db()
        self.assertEqual(mine.status, "Approved")
        self.assertEqual(theirs.status, "Pending")


class MyApprovalsPageTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="MAP", name="My Approvals Co", phone="1", email="map@test.com", address="Addr",
        )
        self.lead_user = User.objects.create_user(username="map_lead", password="pass12345")
        self.lead_user.groups.add(Group.objects.get(name="Employee"))
        self.lead = make_employee(self.company, "MAP_LEAD", "Lead", user=self.lead_user)
        Department.objects.create(name="Sales", reporting_person=self.lead, manager=self.lead)
        self.reportee = make_employee(self.company, "MAP001", "Reportee", department="Sales")
        make_employee(self.company, "MAP002", "Outsider", department="Engineering")

    def _client_as(self, user):
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return client

    def test_reporting_person_sees_only_their_reportees_requests(self):
        mine = LeaveApplication.objects.create(
            employee=self.reportee, leave_type="CL", start_date=WORK_DAY, end_date=WORK_DAY,
            reason="Personal", status="Pending",
        )
        outsider = Employee.objects.get(employee_code="MAP002")
        LeaveApplication.objects.create(
            employee=outsider, leave_type="CL", start_date=WORK_DAY, end_date=WORK_DAY,
            reason="Personal", status="Pending",
        )

        resp = self._client_as(self.lead_user).get(reverse("my-approvals"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["has_reportees"])
        self.assertEqual([l.id for l in resp.context["leave_requests"]], [mine.id])

    def test_page_is_empty_for_someone_with_no_reportees(self):
        user = User.objects.create_user(username="map_nobody", password="pass12345")
        user.groups.add(Group.objects.get(name="Employee"))
        make_employee(self.company, "MAP003", "Nobody", user=user)

        resp = self._client_as(user).get(reverse("my-approvals"))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["has_reportees"])


class ReportsDirectlyToManagerTest(TestCase):
    """An employee may report straight to the manager, with no reporting
    person in between -- a department with only a manager set."""

    def setUp(self):
        self.company = Company.objects.create(
            short_name="RDM", name="Direct Manager Co", phone="1", email="rdm@test.com", address="Addr",
        )
        self.mgr_user = User.objects.create_user(username="rdm_mgr", password="pass12345")
        self.mgr_user.groups.add(Group.objects.get(name="Employee"))
        self.mgr = make_employee(self.company, "RDM_MGR", "Manager", user=self.mgr_user)
        Department.objects.create(name="Ops", reporting_person=None, manager=self.mgr)
        self.reportee = make_employee(self.company, "RDM001", "Reportee", department="Ops")

    def test_employee_has_only_a_manager(self):
        self.assertIsNone(self.reportee.reporting_person)
        self.assertEqual(self.reportee.manager, self.mgr)
        self.assertEqual(self.reportee.get_approvers(), [self.mgr])

    def test_manager_alone_can_approve(self):
        leave = LeaveApplication.objects.create(
            employee=self.reportee, leave_type="CL", start_date=WORK_DAY, end_date=WORK_DAY,
            reason="Personal", status="Pending",
        )
        client = Client()
        client.force_login(self.mgr_user, backend="django.contrib.auth.backends.ModelBackend")
        resp = client.post(reverse("approve_leave", args=[leave.id]))
        self.assertEqual(resp.status_code, 200)
        leave.refresh_from_db()
        self.assertEqual(leave.status, "Approved")
