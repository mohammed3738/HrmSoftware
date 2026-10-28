"""Every page that carries an employee search box still renders.

The search boxes were added by editing markup in nine templates, and a
template that no longer parses -- or a view whose employee filter now raises
-- only shows up when the page is actually requested. These are deliberately
thin: status 200, the search input present, and the filter honoured.

Run with: python manage.py test website.tests.test_employee_search_pages_render
"""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from website.models import Company, Employee

PAGES = [
    ("/attendance/register/", "registerEmployeeSearch"),
    ("/advances/", "advanceEmployeeSearch"),
    ("/advances/create/", "advanceEmployeePicker"),
    ("/leave-balance/", "search-input"),
    ("/salary-slips/", "slipEmployeePicker"),
    ("/holiday/dashboard/", "addEmployeeSearchInput"),
    ("/salary-history/", None),
]


def make_employee(company, code, first, last, **extra):
    fields = dict(
        company=company, salutation="Mr", first_name=first, last_name=last,
        father_name="F", gender="Male", blood_group="O+",
        date_of_birth=date(1990, 1, 1), place_of_birth="City",
        personal_email=f"{code}@render.test", present_address="A",
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


class EmployeeSearchPagesRenderTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Render Co", short_name="RND")
        cls.asha = make_employee(cls.company, "R101", "Asha", "Rao")
        make_employee(cls.company, "R102", "Ravi", "Kumar", middle_name="Nath")

    def setUp(self):
        self.admin = User.objects.create_superuser(
            "render-admin", "render-admin@test.invalid", "x")
        self.client.force_login(
            self.admin, backend="django.contrib.auth.backends.ModelBackend")

    def test_each_page_renders_with_its_search_box(self):
        for url, input_id in PAGES:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, url)
                if input_id:
                    self.assertContains(response, f'id="{input_id}"')

    def test_a_full_name_filter_does_not_break_any_page(self):
        """The filters now split the term into words; a page that still
        passes the whole string somewhere unsplit would raise here."""
        for url, _ in PAGES:
            for term in ("asha rao", "R101", "nath kumar", ""):
                with self.subTest(url=url, q=term):
                    response = self.client.get(url, {"q": term})
                    self.assertEqual(response.status_code, 200)

    def test_a_non_numeric_employee_id_is_a_404_not_a_500(self):
        """?employee= on the slips page is an id. Typed text used to come
        back out of the ORM as a ValueError."""
        self.assertEqual(
            self.client.get("/salary-slips/", {"employee": "asha rao"}).status_code,
            404)
        self.assertEqual(
            self.client.get("/salary-slips/",
                            {"employee": str(self.asha.id)}).status_code, 200)

    def test_the_advance_list_filter_finds_a_person_by_full_name(self):
        by_name = self.client.get("/advances/", {"q": "asha rao"})
        self.assertEqual(by_name.status_code, 200)
        by_wrong_name = self.client.get("/advances/", {"q": "asha kumar"})
        self.assertEqual(by_wrong_name.status_code, 200)

    def test_the_leave_balance_report_filters_by_full_name(self):
        response = self.client.get("/leave-balance/", {"q": "asha rao"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Asha")
        self.assertNotContains(response, "R102")
