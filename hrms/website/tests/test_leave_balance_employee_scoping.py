"""
Regression test: an Employee-role user hitting the leave balance report
used to see every active employee in their company (and their leave
balances), not just their own. leave_balance_view's "single company" branch
now restricts the employee list to the requesting user's own record when
they don't have global (Admin/HR/Manager) access.

Run with: python manage.py test website.tests.test_leave_balance_employee_scoping
"""
from datetime import date

from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse

from website.models import Company, Employee, PayrollSettings, LeaveBalance


class LeaveBalanceEmployeeScopingTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="LBS", name="Leave Balance Scoping Co", phone="1", email="lbs@test.com", address="Addr",
        )
        PayrollSettings.objects.create(company=self.company)

        def make_employee(code, first_name, user=None):
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

        self.self_user = User.objects.create_user(username="lbs_self", password="pass12345")
        self.self_user.groups.add(Group.objects.get(name="Employee"))
        self.self_employee = make_employee("LBS001", "Self", user=self.self_user)

        self.colleague = make_employee("LBS002", "Colleague")

        for emp in (self.self_employee, self.colleague):
            LeaveBalance.objects.create(
                employee=emp, period_from_date=date(2026, 1, 1), period_to_date=date(2026, 1, 31),
                final_leave_balance=10,
            )

        self.hr_user = User.objects.create_user(username="lbs_hr", password="pass12345")
        self.hr_user.groups.add(Group.objects.get(name="HR"))

    def _client_as(self, user):
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return client

    def test_employee_sees_only_own_leave_balance(self):
        resp = self._client_as(self.self_user).get(reverse("leave_balance"))
        self.assertEqual(resp.status_code, 200)
        rows = list(resp.context["leave_balances"])
        employee_ids = {row["employee"].id for row in rows}
        self.assertEqual(employee_ids, {self.self_employee.id})

    def test_hr_still_sees_whole_company(self):
        resp = self._client_as(self.hr_user).get(reverse("leave_balance"), {"company_id": self.company.id})
        self.assertEqual(resp.status_code, 200)
        rows = list(resp.context["leave_balances"])
        employee_ids = {row["employee"].id for row in rows}
        self.assertEqual(employee_ids, {self.self_employee.id, self.colleague.id})
