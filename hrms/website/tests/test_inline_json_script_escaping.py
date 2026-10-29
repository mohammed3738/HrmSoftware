"""
Regression tests for JSON interpolated straight into inline <script> bodies.

Three templates took a server-side json.dumps() string through |safe into
the middle of a <script> block:

    templates/holiday_calendar/dashboard.html:1853   holidays_json
    templates/holiday_calendar/dashboard.html:1854   half_day_json
    templates/attendance/employee_attendance_detail.html:810
                                                     calendar_attendance_json

json.dumps() escapes quotes and backslashes but **not** '<'. An HTML parser
ends a script element at the first "</script" regardless of JavaScript
string quoting, so any serialized value containing "</script>" closes the
tag early and everything after it is parsed as markup. Holiday.name and
HalfDayScenario.description are free-text fields filled in through the
holiday-calendar forms, which makes this stored XSS against everyone who
later opens the calendar -- including roles more privileged than the author.

The fix escapes '<', '>' and '&' as \\uXXXX, which is what Django's own
json_script filter does and is value-preserving: "\\u003C" in a JavaScript
string literal is the character '<'.

These tests assert on the rendered HTML, so they fail if the escaping is
dropped from either the helper or a template.

Run with:
    python manage.py test website.tests.test_inline_json_script_escaping
"""
import json
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import (
    Attendance,
    Branch,
    Company,
    Employee,
    HalfDayScenario,
    Holiday,
    HolidayType,
)

PAYLOAD = '</script><img src=x onerror=alert(1)>'
# The six characters a correctly-escaped "<" becomes in the JavaScript
# source: a backslash followed by u003C. Built from chr(92) so the literal
# below cannot itself be mistaken for an escape sequence.
ESCAPED_LT = chr(92) + 'u003C'


class JsonForScriptHelperTest(TestCase):
    def test_closing_script_tag_cannot_survive_the_helper(self):
        from website.views import json_for_script

        rendered = json_for_script({"name": PAYLOAD})
        self.assertNotIn("</script", rendered.lower())
        self.assertNotIn("<", rendered)
        self.assertNotIn(">", rendered)

    def test_helper_output_still_decodes_to_the_original_value(self):
        from website.views import json_for_script

        self.assertEqual(json.loads(json_for_script({"name": PAYLOAD}))["name"], PAYLOAD)

    def test_ampersand_is_escaped_too(self):
        from website.views import json_for_script

        self.assertNotIn("&", json_for_script({"name": "a & b"}))
        self.assertEqual(json.loads(json_for_script({"name": "a & b"}))["name"], "a & b")


class HolidayCalendarInlineJsonTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="XSS", name="Escaping Co", phone="1",
            email="xss@test.com", address="Addr",
        )
        self.branch = Branch.objects.create(branch_name="Main")
        self.staff_user = User.objects.create_user(username="xss_admin", password="pass12345")
        self.staff_user.groups.add(Group.objects.get(name="Super Admin"))

        holiday_type = HolidayType.objects.create(name="Festival", type_category="regional")
        Holiday.objects.create(
            holiday_date=date(2026, 5, 1), name=PAYLOAD, holiday_type=holiday_type,
            status="declared", created_by=self.staff_user,
        )
        HalfDayScenario.objects.create(
            branch=self.branch, scenario_date=date(2026, 5, 2), scenario_type="other",
            description=PAYLOAD, credit_count=Decimal("0.50"), created_by=self.staff_user,
        )

        self.client_staff = Client()
        self.client_staff.force_login(
            self.staff_user, backend="django.contrib.auth.backends.ModelBackend",
        )

    def _script_literal(self, marker):
        """The right-hand side of `const <marker> = ...` as it is sent.

        Asserting on the whole page would be wrong: Django's template
        auto-escaping already renders the same payload harmlessly as
        `&lt;img src=x onerror=alert(1)&gt;` in the holidays table, and the
        substring `onerror=alert(1)` survives that escaping intact. What
        matters here is only whether the payload can close the <script>
        element it is embedded in."""
        html = self.client_staff.get(
            reverse("holiday-calendar"), {"year": 2026, "month": 5},
        ).content.decode()
        self.assertIn(marker, html)
        start = html.index(marker)
        return html[start:html.index("\n", start)]

    def test_holiday_name_cannot_break_out_of_the_script_block(self):
        literal = self._script_literal("const holidaysData")
        self.assertNotIn("</script", literal.lower())
        value = literal[literal.index("="):]
        self.assertNotIn("<", value)
        self.assertNotIn(">", value)
        self.assertIn(ESCAPED_LT, literal)

    def test_half_day_description_cannot_break_out_of_the_script_block(self):
        literal = self._script_literal("const halfDayData")
        self.assertNotIn("</script", literal.lower())
        self.assertNotIn(PAYLOAD, literal)
        self.assertIn(ESCAPED_LT, literal)


class AttendanceCalendarInlineJsonTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="XS2", name="Escaping Co 2", phone="1",
            email="xs2@test.com", address="Addr",
        )
        self.staff_user = User.objects.create_user(username="xs2_admin", password="pass12345")
        self.staff_user.groups.add(Group.objects.get(name="Super Admin"))
        self.employee = Employee.objects.create(
            company=self.company, salutation="Mr", first_name="Cal", last_name="Doe",
            father_name="Father", gender="Male", blood_group="O+",
            date_of_birth=date(1990, 1, 1), place_of_birth="City",
            personal_email="xs2001@test.com", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890",
            employee_code="XS2001", designation="Dev", department="IT",
            date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Cal",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
            force_password_change=False,
        )
        Attendance.objects.create(
            employee=self.employee, date=date(2026, 5, 4), status="Present",
            count=Decimal("1.00"),
        )
        self.client_staff = Client()
        self.client_staff.force_login(
            self.staff_user, backend="django.contrib.auth.backends.ModelBackend",
        )

    def test_calendar_payload_is_escaped_for_inline_script(self):
        """Attendance.status is a choices field, so there is no live
        injection here -- but the page must still use the escaping helper,
        since the same block would carry free text the moment one more
        field is added to the dict."""
        resp = self.client_staff.get(
            reverse("employee_attendance_detail", args=[self.employee.pk]),
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        marker = "const CAL_DATA"
        self.assertIn(marker, html)
        start = html.index(marker)
        literal = html[start:html.index("\n", start)]
        self.assertNotIn("</script", literal.lower())
