"""The shared employee type-ahead behind every employee picker.

The endpoint is now used from a dozen pages, so its scoping and shape are
worth pinning here rather than trusting each caller.

Run with: python manage.py test website.tests.test_employee_search_autocomplete
"""
import json
import os
from datetime import date

from django.conf import settings as dj_settings
from django.contrib.auth.models import Group, User
from django.test import Client, TestCase

from website.models import Company, Employee

URL = "/ajax/employees/search/"


def make_employee(company, code, first="Test", last="Person", **extra):
    fields = dict(
        company=company, salutation="Mr", first_name=first, last_name=last,
        father_name="F", gender="Male", blood_group="O+",
        date_of_birth=date(1990, 1, 1), place_of_birth="City",
        personal_email=f"{code}@test.com".lower(), present_address="A",
        permanent_address="A", personal_mobile="1234567890", employee_code=code,
        designation="Dev", department="IT", date_of_joining=date(2020, 1, 1),
        location="City", pan_no="ABCDE1234F", aadhar_no="123456789012",
        name_as_per_bank=first, salary_account_number="1",
        ifsc_code="TEST0001234", emergency_contact_name1="J",
        emergency_contact_relation1="Spouse",
        emergency_contact_mobile1="0987654321", status="Active",
        force_password_change=False,
    )
    fields.update(extra)
    return Employee.objects.create(**fields)


class EmployeeSearchEndpointTest(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name="Acme", short_name="ACM")
        self.other = Company.objects.create(name="Other Co", short_name="OTH")

        self.asha = make_employee(self.acme, "101", "Asha", "Rao")
        self.ravi = make_employee(self.acme, "102", "Ravi", "Kumar")
        self.left = make_employee(self.acme, "103", "Gone", "Away", status="Left")
        self.outsider = make_employee(self.other, "901", "Asha", "Stranger")

        self.admin = User.objects.create_user("search-admin", password="x", is_staff=True)
        self.client.force_login(self.admin,
                               backend="django.contrib.auth.backends.ModelBackend")

    def search(self, query, client=None):
        response = (client or self.client).get(URL, {"q": query})
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content)

    # ── shape ───────────────────────────────────────────────────────────
    def test_matches_on_first_name_last_name_and_code(self):
        self.assertEqual([r["code"] for r in self.search("Asha")], ["101", "901"])
        self.assertEqual([r["code"] for r in self.search("Kumar")], ["102"])
        self.assertEqual([r["code"] for r in self.search("102")], ["102"])

    def test_each_row_carries_what_the_dropdown_renders(self):
        row = self.search("Asha")[0]
        self.assertEqual(
            set(row), {"id", "name", "code", "department", "status"})
        self.assertEqual(row["name"], "Asha Rao")
        self.assertEqual(row["department"], "IT")

    def test_an_employee_with_no_name_does_not_render_blank(self):
        make_employee(self.acme, "104", first="", last="")
        row = [r for r in self.search("104")][0]
        self.assertEqual(row["name"], "(no name)")

    # ── the empty query ─────────────────────────────────────────────────
    def test_an_empty_query_returns_nothing(self):
        """It used to match everything -- icontains="" -- and hand back the
        first ten employees in the database to anybody who asked."""
        self.assertEqual(self.search(""), [])
        self.assertEqual(self.search("   "), [])

    # ── company scoping ─────────────────────────────────────────────────
    def test_a_user_without_global_access_sees_only_their_own_company(self):
        employee_group, _ = Group.objects.get_or_create(name="Employee")
        user = User.objects.create_user("acme-staff", password="x")
        user.groups.add(employee_group)
        self.asha.user = user
        self.asha.save()
        # Linking a user re-arms force_password_change, and
        # ForcePasswordChangeMiddleware then redirects every request to the
        # change-password page -- including this one.
        Employee.objects.filter(pk=self.asha.pk).update(force_password_change=False)

        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        codes = [r["code"] for r in self.search("Asha", client=client)]
        self.assertEqual(codes, ["101"],
                         "the other company's Asha must not be suggested")

    def test_an_admin_sees_every_company(self):
        self.assertEqual([r["code"] for r in self.search("Asha")], ["101", "901"])

    # ── ordering ────────────────────────────────────────────────────────
    def test_active_employees_come_before_people_who_have_left(self):
        make_employee(self.acme, "100", "Gone", "Earlier", status="Left")
        rows = self.search("Gone")
        self.assertEqual([r["status"] for r in rows], ["Left", "Left"])
        rows = self.search("o")
        statuses = [r["status"] for r in rows]
        self.assertEqual(statuses, sorted(statuses, key=lambda s: s != "Active"),
                         "Active first, so nobody picks a leaver by accident")

    def test_a_leaver_is_still_findable(self):
        """Their old attendance and payroll are still looked at."""
        self.assertEqual([r["code"] for r in self.search("Gone")], ["103"])

    def test_login_is_required(self):
        response = Client().get(URL, {"q": "Asha"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.url)


class SharedAutocompleteWiringTest(TestCase):
    """One implementation, loaded once. There used to be two inline copies of
    the same fetch-and-render code -- in attendance/today.html and
    attendance/shift_roster.html -- which is how they drifted apart."""

    def template(self, rel):
        for directory in dj_settings.TEMPLATES[0]["DIRS"]:
            candidate = os.path.join(str(directory), *rel.split("/"))
            if os.path.exists(candidate):
                with open(candidate, encoding="utf-8") as handle:
                    return handle.read()
        self.fail(f"{rel} not found in TEMPLATES DIRS")

    def test_the_shared_script_exists_and_defines_the_helper(self):
        path = os.path.join(str(dj_settings.BASE_DIR), "static", "js",
                            "employee_autocomplete.js")
        self.assertTrue(os.path.exists(path), path)
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn("window.wireEmployeeAutocomplete", source)

    def test_base_template_loads_it_for_every_page(self):
        self.assertIn("js/employee_autocomplete.js", self.template("base2.html"))

    def test_no_page_still_calls_the_search_endpoint_by_hand(self):
        for rel in ("attendance/today.html", "attendance/shift_roster.html"):
            with self.subTest(template=rel):
                self.assertNotIn("ajax/employees/search", self.template(rel),
                                 "this page should go through the shared helper")

    def test_the_converted_pages_still_wire_their_pickers(self):
        self.assertIn("wireEmployeeAutocomplete(", self.template("attendance/today.html"))
        roster = self.template("attendance/shift_roster.html")
        self.assertEqual(roster.count("wireEmployeeAutocomplete("), 2,
                         "the roster has a filter picker and a modal picker")
        self.assertEqual(roster.count("let selectedShiftEmployees"), 1)
