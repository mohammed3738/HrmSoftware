"""
Regression tests for advances access.

Advances are a payroll matter: only Super Admin, Admin and the Payroll
Officer administer them, and HR has no grant at all. But everybody -- HR
included -- needs to be able to check their own advance, so advance_list
and advance_detail scope to the signed-in employee's own records when the
viewer holds no advances:view grant, rather than making self-service depend
on a company-wide permission.

Run with: python manage.py test website.tests.test_advances_self_service
"""
from datetime import date

from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse

from website.models import AdvanceMaster, Company, Employee


def make_employee(company, code, user=None, first_name="Adv"):
    return Employee.objects.create(
        company=company, user=user, salutation="Mr", first_name=first_name, last_name="Ance",
        father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
        place_of_birth="City", personal_email=f"{code}@test.com", present_address="Addr",
        permanent_address="Addr", personal_mobile="1234567890", employee_code=code,
        designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), location="City",
        pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank=first_name,
        salary_account_number="1234567890", ifsc_code="TEST0001234",
        emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
        emergency_contact_mobile1="0987654321", status="Active", force_password_change=False,
    )


def make_advance(employee, amount=12000):
    return AdvanceMaster.objects.create(
        employee=employee, advance_amount=amount, start_date=date(2026, 1, 1),
        default_months=12, outstanding_amount=amount,
    )


class AdvanceAccessTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="ADV", name="Advance Co", phone="1", email="adv@test.com", address="Addr",
        )

        def linked(role, username, code):
            user = User.objects.create_user(username=username, password="pass12345")
            if role:
                user.groups.add(Group.objects.get(name=role))
            return user, make_employee(self.company, code, user=user)

        self.hr_user, self.hr_employee = linked("HR", "adv_hr", "ADV_HR")
        self.emp_user, self.employee = linked("Employee", "adv_emp", "ADV001")
        self.officer_user, self.officer = linked("Payroll Officer", "adv_po", "ADV_PO")

        self.my_advance = make_advance(self.hr_employee, 10000)
        self.someone_elses = make_advance(self.employee, 24000)

    def _client_as(self, user):
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return client

    # ── HR: own advance only ──────────────────────────────────────────

    def test_hr_sees_only_their_own_advance(self):
        resp = self._client_as(self.hr_user).get(reverse("advances-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["can_see_all_advances"])
        ids = {a.id for a in resp.context["advances"]}
        self.assertEqual(ids, {self.my_advance.id})

    def test_hr_stats_cover_only_their_own_advance(self):
        """The summary tiles must not leak the company's totals to someone
        who can only see their own row."""
        resp = self._client_as(self.hr_user).get(reverse("advances-list"))
        self.assertEqual(resp.context["stats"]["total"], 1)

    def test_hr_cannot_open_someone_elses_advance(self):
        resp = self._client_as(self.hr_user).get(
            reverse("advance-detail", args=[self.someone_elses.id])
        )
        self.assertEqual(resp.status_code, 403)

    def test_hr_can_open_their_own_advance(self):
        resp = self._client_as(self.hr_user).get(reverse("advance-detail", args=[self.my_advance.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["can_manage_advances"])

    def test_hr_cannot_create_an_advance(self):
        self.assertEqual(
            self._client_as(self.hr_user).get(reverse("create-advance")).status_code, 403
        )

    def test_hr_cannot_record_a_payment(self):
        resp = self._client_as(self.hr_user).post(
            reverse("advances-pay", args=[self.my_advance.id]), {"amount": "1000"}
        )
        self.assertEqual(resp.status_code, 403)

    # ── plain employee: same self-service ─────────────────────────────

    def test_employee_sees_only_their_own_advance(self):
        resp = self._client_as(self.emp_user).get(reverse("advances-list"))
        self.assertEqual(resp.status_code, 200)
        ids = {a.id for a in resp.context["advances"]}
        self.assertEqual(ids, {self.someone_elses.id})

    def test_manage_controls_are_hidden_from_a_self_viewer(self):
        resp = self._client_as(self.emp_user).get(reverse("advances-list"))
        self.assertFalse(resp.context["can_manage_advances"])
        self.assertNotContains(resp, "New Advance")
        self.assertContains(resp, "My Advances")

    # ── payroll officer: the whole company ────────────────────────────

    def test_payroll_officer_sees_every_advance(self):
        resp = self._client_as(self.officer_user).get(reverse("advances-list"))
        self.assertTrue(resp.context["can_see_all_advances"])
        self.assertTrue(resp.context["can_manage_advances"])
        ids = {a.id for a in resp.context["advances"]}
        self.assertEqual(ids, {self.my_advance.id, self.someone_elses.id})
        self.assertContains(resp, "New Advance")

    def test_payroll_officer_can_open_anyones_advance(self):
        resp = self._client_as(self.officer_user).get(
            reverse("advance-detail", args=[self.someone_elses.id])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["can_manage_advances"])

    # ── a login with no employee record has nothing to show ───────────

    def test_bare_account_without_an_employee_record_is_refused(self):
        bare = User.objects.create_user(username="adv_bare", password="pass12345")
        bare.groups.add(Group.objects.get(name="Employee"))
        self.assertEqual(
            self._client_as(bare).get(reverse("advances-list")).status_code, 403
        )
