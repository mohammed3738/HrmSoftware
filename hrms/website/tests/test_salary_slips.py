"""
Salary slip self-service list and the combined multi-month statement.

Run with: python manage.py test website.tests.test_salary_slips
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse

from website.models import Company, Employee, PayrollRun, PayrollRecord


class SalarySlipsTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="SS", name="Slip Co", phone="1", email="ss@test.com", address="Addr",
        )
        self.self_user = User.objects.create_user(username="ss_self", password="pass12345")
        self.self_user.groups.add(Group.objects.get(name="Employee"))
        self.me = self._employee("SS001", "Self", user=self.self_user)
        self.other = self._employee("SS002", "Other")

        self.officer = User.objects.create_user(username="ss_payroll", password="pass12345")
        self.officer.groups.add(Group.objects.get(name="Payroll Officer"))
        self.hr = User.objects.create_user(username="ss_hr", password="pass12345")
        self.hr.groups.add(Group.objects.get(name="HR"))

        self.jan = self._record(self.me, date(2026, 1, 1), net=20000)
        self.feb = self._record(self.me, date(2026, 2, 1), net=21000)
        self.mar = self._record(self.me, date(2026, 3, 1), net=22000)
        self.apr_draft = self._record(self.me, date(2026, 4, 1), net=23000, finalized=False)
        self.other_jan = self._record(self.other, date(2026, 1, 1), net=50000)

    def _employee(self, code, first_name, user=None):
        return Employee.objects.create(
            company=self.company, user=user, salutation="Mr", first_name=first_name, last_name="Doe",
            father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email=f"{code}@test.com", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890", employee_code=code,
            designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank=first_name,
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active", force_password_change=False,
        )

    def _record(self, employee, month, net, finalized=True):
        run = PayrollRun.objects.create(
            company=self.company, month=month, start_date=month, end_date=month.replace(day=28),
            status=PayrollRun.STATUS_FINALIZED if finalized else PayrollRun.STATUS_DRAFT,
        )
        return PayrollRecord.objects.create(
            payroll=run, employee=employee, employee_code=employee.employee_code,
            employee_name=f"{employee.first_name} Doe", total_days=28, leave_without_pay=Decimal("1"),
            basic_processed=Decimal(net), gross_processed=Decimal(net + 200),
            professional_tax=Decimal(200), total_deductions=Decimal(200), net_salary=Decimal(net),
        )

    def _client(self, user):
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return client

    # ── list ────────────────────────────────────────────────────────────
    def test_employee_list_shows_only_own_finalized_slips(self):
        resp = self._client(self.self_user).get(reverse("salary-slips"))
        self.assertEqual(resp.status_code, 200)
        ids = {r.id for r in resp.context["records"]}
        self.assertEqual(ids, {self.jan.id, self.feb.id, self.mar.id})

    def test_employee_cannot_list_someone_else_by_query_param(self):
        resp = self._client(self.self_user).get(reverse("salary-slips"), {"employee": self.other.id})
        self.assertEqual(resp.context["employee"], self.me)

    def test_year_filter(self):
        resp = self._client(self.self_user).get(reverse("salary-slips"), {"year": "2025"})
        self.assertEqual(list(resp.context["records"]), [])
        self.assertEqual(resp.context["years"], [2026])

    def test_payroll_officer_can_list_any_employee_including_drafts(self):
        resp = self._client(self.officer).get(reverse("salary-slips"), {"employee": self.me.id})
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.apr_draft.id, {r.id for r in resp.context["records"]})

    def test_hr_without_employee_profile_is_denied(self):
        resp = self._client(self.hr).get(reverse("salary-slips"))
        self.assertEqual(resp.status_code, 403)

    # ── combined statement ──────────────────────────────────────────────
    def _statement(self, user, records, **extra):
        return self._client(user).get(
            reverse("salary-slip-statement"), {"ids": [r.id for r in records], **extra},
        )

    def test_employee_combined_statement_lists_each_month_and_totals(self):
        resp = self._statement(self.self_user, [self.mar, self.jan, self.feb])
        self.assertEqual(resp.status_code, 200)
        months = [cells[0]["value"] for cells in resp.context["rows"]]
        self.assertEqual(months, ["Jan-26", "Feb-26", "Mar-26"])
        self.assertEqual(resp.context["net_total"], "63,000")
        self.assertEqual(resp.context["period_label"], "Jan-26 to Mar-26")

    def test_combined_statement_pdf(self):
        resp = self._statement(self.self_user, [self.jan, self.feb, self.mar], format="pdf")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_employee_cannot_include_draft_month(self):
        resp = self._statement(self.self_user, [self.jan, self.apr_draft])
        self.assertEqual(resp.status_code, 404)

    def test_employee_cannot_combine_someone_elses_slips(self):
        resp = self._statement(self.self_user, [self.other_jan])
        self.assertEqual(resp.status_code, 403)

    def test_cannot_mix_employees_in_one_statement(self):
        resp = self._statement(self.officer, [self.jan, self.other_jan])
        self.assertEqual(resp.status_code, 400)

    def test_requires_at_least_one_month(self):
        resp = self._client(self.self_user).get(reverse("salary-slip-statement"))
        self.assertEqual(resp.status_code, 400)
