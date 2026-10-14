"""
Payroll waits for approvals: a run can't be created or finalized while
leave, comp-off, attendance-correction or employee-change requests for
that company and period are still pending.

Run with: python manage.py test website.tests.test_payroll_pending_approvals
"""
from datetime import date, time

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import (
    Attendance, AttendanceCorrectionRequest, Company, CompOffRequest, Employee, EmployeeChangeRequest,
    LeaveApplication, PayrollRun, PayrollSettings,
)
from website.services.pending_approvals import pending_approvals_for_payroll

START, END = date(2026, 3, 1), date(2026, 3, 31)


class PayrollPendingApprovalsTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Gate Co", short_name="GTE", address="A")
        self.other_company = Company.objects.create(name="Other Co", short_name="OTH", address="A")
        PayrollSettings.objects.create(company=self.company)
        PayrollSettings.objects.create(company=self.other_company)
        self.emp = Employee.objects.create(company=self.company, first_name="Gate", last_name="Emp",
                                           employee_code="GT1", status="Active", date_of_joining=date(2020, 1, 1))
        officer = User.objects.create_user(username="gate_po", password="pass12345")
        officer.groups.add(Group.objects.get(name="Payroll Officer"))
        self.client = Client()
        self.client.force_login(officer, backend="django.contrib.auth.backends.ModelBackend")

    def _create(self, company_id):
        return self.client.post(reverse("payroll-run-create"), {"company": company_id, "month": "2026-03"}, follow=True)

    def _pending_leave(self):
        return LeaveApplication.objects.create(employee=self.emp, start_date=date(2026, 3, 10),
                                               end_date=date(2026, 3, 11), reason="x")

    def test_nothing_pending_means_nothing_to_report(self):
        self.assertEqual(pending_approvals_for_payroll(self.company, START, END), [])

    def test_each_kind_of_pending_request_is_found(self):
        self._pending_leave()
        CompOffRequest.objects.create(employee=self.emp, from_date=date(2026, 3, 5), to_date=date(2026, 3, 5),
                                      count=1, reason="x")
        att = Attendance.objects.create(employee=self.emp, date=date(2026, 3, 3), in_time=time(9), out_time=time(18))
        AttendanceCorrectionRequest.objects.create(attendance=att, old_in_time=time(9), old_out_time=time(18),
                                                   new_in_time=time(9), new_out_time=time(19), reason="x")
        EmployeeChangeRequest.objects.create(employee=self.emp, field_changes={})
        labels = {p["label"]: p["count"] for p in pending_approvals_for_payroll(self.company, START, END)}
        self.assertEqual(labels, {"leave application": 1, "comp-off request": 1,
                                  "attendance correction": 1, "employee change request": 1})

    def test_requests_outside_the_period_or_company_do_not_block(self):
        LeaveApplication.objects.create(employee=self.emp, start_date=date(2026, 4, 10),
                                        end_date=date(2026, 4, 11), reason="later")
        LeaveApplication.objects.create(employee=self.emp, start_date=date(2026, 3, 2),
                                        end_date=date(2026, 3, 2), reason="decided", status="Approved")
        self.assertEqual(pending_approvals_for_payroll(self.company, START, END), [])
        self._pending_leave()
        self.assertEqual(pending_approvals_for_payroll(self.other_company, START, END), [])

    def test_create_is_refused_until_approvals_are_decided(self):
        leave = self._pending_leave()
        resp = self._create(self.company.pk)
        self.assertFalse(PayrollRun.objects.exists())
        self.assertContains(resp, "can&#x27;t proceed until these are approved or rejected: 1 leave application")
        leave.status = "Approved"
        leave.save()
        self._create(self.company.pk)
        self.assertTrue(PayrollRun.objects.filter(company=self.company).exists())

    def test_all_companies_skips_only_the_blocked_one(self):
        self._pending_leave()
        self._create("all")
        self.assertEqual(list(PayrollRun.objects.values_list("company__short_name", flat=True)), ["OTH"])

    def test_finalize_is_refused_while_something_is_pending(self):
        run = PayrollRun.objects.create(company=self.company, month=START, start_date=START, end_date=END)
        self._pending_leave()
        page = self.client.get(reverse("payroll-run-detail", args=[run.pk]))
        self.assertContains(page, "Payroll can't be finalized until these are approved or rejected")
        resp = self.client.post(reverse("payroll-run-finalize", args=[run.pk]))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("1 leave application", resp.json()["error"])
        run.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.STATUS_DRAFT)
