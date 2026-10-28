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

    # ── name or code, whatever gets typed ───────────────────────────────
    def test_a_full_name_finds_the_person(self):
        """The one that was broken: "asha rao" matched nobody, because no
        single name column holds both words."""
        self.assertEqual([e["code"] for e in self.search("asha rao")], ["101"])

    def test_the_words_may_come_in_any_order(self):
        self.assertEqual([e["code"] for e in self.search("rao asha")], ["101"])

    def test_extra_spaces_do_not_matter(self):
        self.assertEqual([e["code"] for e in self.search("  asha   rao ")], ["101"])

    def test_a_middle_name_is_searchable_and_shown(self):
        make_employee(self.acme, "104", "Raj", "Sharma", middle_name="Kumar")
        rows = self.search("kumar sharma")
        self.assertEqual([e["code"] for e in rows], ["104"])
        self.assertEqual(rows[0]["name"], "Raj Kumar Sharma")

    def test_a_single_word_still_matches_a_code(self):
        self.assertEqual([e["code"] for e in self.search("102")], ["102"])

    def test_a_full_name_does_not_leak_everyone_with_a_matching_word(self):
        """Every word has to land, so one shared word is not a match."""
        make_employee(self.acme, "105", "Asha", "Mehta")
        self.assertEqual(sorted(e["code"] for e in self.search("asha rao")), ["101"])

    def test_a_name_search_does_not_duplicate_rows(self):
        """Filtering word by word joins the same row more than once if the
        joins are not folded together."""
        make_employee(self.acme, "106", "Asha", "Asha")
        codes = [e["code"] for e in self.search("asha asha")]
        self.assertEqual(sorted(codes), sorted(set(codes)))
        self.assertIn("106", codes)

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
        for rel in ("attendance/today.html", "attendance/shift_roster.html",
                    "attendance/employee_attendance_detail.html",
                    "attendance/late_attendance_review.html",
                    "holiday_calendar/dashboard.html"):
            with self.subTest(template=rel):
                self.assertNotIn("ajax/employees/search", self.template(rel),
                                 "this page should go through the shared helper")

    def test_the_converted_pages_still_wire_their_pickers(self):
        self.assertIn("wireEmployeeAutocomplete(", self.template("attendance/today.html"))
        roster = self.template("attendance/shift_roster.html")
        self.assertEqual(roster.count("wireEmployeeAutocomplete("), 2,
                         "the roster has a filter picker and a modal picker")
        self.assertEqual(roster.count("let selectedShiftEmployees"), 1)

    def test_every_employee_search_box_offers_suggestions(self):
        """A box labelled "name or code" that gives no suggestions is the
        thing this was meant to end. Each of these pages has one, and each
        one has to be wired and have a dropdown to render into."""
        for rel, input_id, dropdown_id in (
            ("attendance/today.html", "employeeSearch", "employeeDropdown"),
            ("attendance/late_attendance_review.html", "employeeSearch",
             "employeeDropdown"),
            ("attendance/employee_attendance_detail.html", "employeeSearch",
             "employeeDropdown"),
            ("attendance/attendance_register.html", "registerEmployeeSearch",
             "registerEmployeeSearchDropdown"),
            ("advances/advance_list.html", "advanceEmployeeSearch",
             "advanceEmployeeSearchDropdown"),
            ("leave_balance/leave_balance_report.html", "search-input",
             "search-inputDropdown"),
            ("holiday_calendar/dashboard.html", "addEmployeeSearchInput",
             "addEmployeeSearchDropdown"),
            ("holiday_calendar/dashboard.html", "editEmployeeSearchInput",
             "editEmployeeSearchDropdown"),
        ):
            with self.subTest(template=rel, input=input_id):
                source = self.template(rel)
                self.assertIn(f'id="{input_id}"', source)
                self.assertIn(f'id="{dropdown_id}"', source)
                self.assertIn("wireEmployeeAutocomplete", source,
                              "not wired to the shared helper")

    def test_every_employee_select_has_a_type_ahead_driving_it(self):
        """These keep their <select> -- it is what gets submitted and what
        the pages' change handlers hang off -- and gain a search box."""
        for rel, input_id, select_id in (
            ("advances/advance_create.html", "advanceEmployeePicker", "id_employee"),
            ("payroll/salary_slips_list.html", "slipEmployeePicker", "slipEmployeeSelect"),
            ("salary/create_salary4.html", "salaryEmployeePicker", "employeeSelect"),
            ("salary_increment/create_increment.html", "incrementEmployeePicker",
             "employeeSelect"),
        ):
            with self.subTest(template=rel):
                source = self.template(rel)
                self.assertIn(f'id="{input_id}"', source)
                self.assertIn(f'id="{input_id}Dropdown"', source)
                self.assertIn(
                    f'wireEmployeeSelectSearch("{input_id}", '
                    f'"{input_id}Dropdown", "{select_id}")', source)
                self.assertIn(f'id="{select_id}"', source)

    def test_the_client_side_row_filters_are_wired_and_word_wise(self):
        """These three filter rows that are already on the page -- a server
        type-ahead would be a regression there -- but they still have to
        search by name or code, and a multi-word name has to work."""
        for rel, input_id in (
            ("payroll/run_detail.html", "empSearch"),
            ("settings/roles_permissions_hub.html", "userSearch"),
            ("salary_increment/create_increment.html", "searchBox"),
        ):
            with self.subTest(template=rel):
                source = self.template(rel)
                self.assertIn(f'id="{input_id}"', source)
                self.assertIn(input_id, source.split("<script", 1)[-1],
                              "the box has no handler -- typing does nothing")
                self.assertIn(r"split(/\s+/)", source,
                              "the filter is not word-wise")

    def test_the_increment_rows_carry_what_their_filter_searches(self):
        source = self.template("salary_increment/create_increment.html")
        self.assertIn('class="increment-row"', source)
        self.assertIn("employee_code|lower", source)
        self.assertIn("middle_name|lower", source)
        self.assertIn('data-status=', source)

    def test_the_helper_exposes_both_entry_points(self):
        path = os.path.join(str(dj_settings.BASE_DIR), "static", "js",
                            "employee_autocomplete.js")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn("window.wireEmployeeSelectSearch", source)
        # The select-driven picker must only offer options the form has.
        self.assertIn("opts.filter", source)
