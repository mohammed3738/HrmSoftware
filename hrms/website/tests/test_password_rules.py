"""The on-screen password checklist must say what the server enforces.

The change-password and reset-password pages list the rules and turn each
one green as the password satisfies it. The failure worth guarding against
is not a broken animation -- it is the checklist drifting away from the
policy: all green on a password the server then refuses, or a rule quietly
missing from the list so the user has no idea why their password was
rejected.

So the list is derived from settings.AUTH_PASSWORD_VALIDATORS rather than
written into the template, and these tests check the derivation in both
directions: every configured validator this module knows about appears,
and nothing appears that is not configured.

Run with: python manage.py test website.tests.test_password_rules
"""
from datetime import date

from django.contrib.auth.tokens import default_token_generator
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode

from website.models import Company, Employee
from website.utils.password_rules import password_rules

LENGTH = "django.contrib.auth.password_validation.MinimumLengthValidator"
NUMERIC = "django.contrib.auth.password_validation.NumericPasswordValidator"
COMMON = "django.contrib.auth.password_validation.CommonPasswordValidator"
SIMILARITY = ("django.contrib.auth.password_validation."
              "UserAttributeSimilarityValidator")


def ids(rules):
    return [rule["id"] for rule in rules]


def by_id(rules, rule_id):
    return next(rule for rule in rules if rule["id"] == rule_id)


class PasswordRulesDerivationTest(TestCase):
    def test_the_shipped_policy_produces_the_expected_checklist(self):
        # Mirrors settings.py as shipped: length, common, numeric, no
        # similarity check -- plus the confirm-field rule, which is the
        # form's own and always last.
        self.assertEqual(
            ids(password_rules()),
            ["min_length", "not_common", "not_numeric", "match"],
        )

    @override_settings(AUTH_PASSWORD_VALIDATORS=[
        {"NAME": LENGTH, "OPTIONS": {"min_length": 12}},
    ])
    def test_the_length_shown_follows_the_configured_minimum(self):
        rule = by_id(password_rules(), "min_length")
        self.assertEqual(rule["min_length"], 12)
        self.assertEqual(rule["label"], "At least 12 characters")

    @override_settings(AUTH_PASSWORD_VALIDATORS=[{"NAME": LENGTH}])
    def test_a_length_validator_with_no_options_uses_djangos_own_default(self):
        self.assertEqual(by_id(password_rules(), "min_length")["min_length"], 8)

    @override_settings(AUTH_PASSWORD_VALIDATORS=[])
    def test_switching_every_validator_off_leaves_only_the_confirm_rule(self):
        self.assertEqual(ids(password_rules()), ["match"])

    @override_settings(AUTH_PASSWORD_VALIDATORS=[{"NAME": SIMILARITY}])
    def test_the_similarity_rule_is_listed_when_it_is_switched_back_on(self):
        rule = by_id(password_rules(), "not_similar")
        self.assertIn("similar", rule["label"].lower())
        self.assertEqual(rule["mode"], "server")

    @override_settings(AUTH_PASSWORD_VALIDATORS=[
        {"NAME": "website.tests.test_password_rules.NotAValidator"},
    ])
    def test_an_unrecognised_validator_is_skipped_rather_than_mislabelled(self):
        """Inventing a label for a validator this module has never seen
        would be a guess shown to the user as fact."""
        self.assertEqual(ids(password_rules()), ["match"])

    # -- which rules the browser can judge --------------------------------

    def test_only_the_arithmetic_rules_are_marked_live(self):
        """A rule marked "live" has to be decidable from the two password
        boxes alone. The common-password list and the name-similarity
        check are not, and marking either one live would mean showing a
        green tick for a password the server is about to refuse."""
        modes = {rule["id"]: rule["mode"] for rule in password_rules()}
        self.assertEqual(modes["min_length"], "live")
        self.assertEqual(modes["not_numeric"], "live")
        self.assertEqual(modes["match"], "live")
        self.assertEqual(modes["not_common"], "server")


class PasswordRulesOnThePagesTest(TestCase):
    """The rules reach the templates, on both pages that set a password."""

    def setUp(self):
        self.client = Client()
        self.company = Company.objects.create(
            short_name="PRU", name="Rules Co", phone="1",
            email="pru@test.com", address="Addr",
        )

    def make_employee(self, code="PRU001"):
        return Employee.objects.create(
            company=self.company, salutation="Mr", first_name="Asha",
            last_name="Verma", father_name="Father", gender="Female",
            blood_group="O+", date_of_birth=date(1990, 1, 1), place_of_birth="Pune",
            personal_email=f"{code}@example.test", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890",
            employee_code=code, designation="Operator", department="Production",
            date_of_joining=date(2020, 1, 1), location="Pune",
            pan_no="ABCDE1234F", aadhar_no="123456789012",
            name_as_per_bank="Asha Verma", salary_account_number="1234567890",
            ifsc_code="TEST0001234", emergency_contact_name1="Spouse",
            emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
        )

    def test_the_change_password_page_shows_the_checklist(self):
        employee = self.make_employee()
        self.client.login(username=employee.user.username, password="Temp@123")
        resp = self.client.get(reverse("change-password"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "At least 8 characters")
        self.assertContains(resp, "Not only numbers")
        self.assertContains(resp, "Both passwords match")
        # The JSON the browser reads, and the script that reads it.
        self.assertContains(resp, 'id="password-rules-data"')
        self.assertContains(resp, "password-rules.js")

    def test_the_change_password_page_has_a_show_password_button_per_field(self):
        employee = self.make_employee(code="PRU002")
        self.client.login(username=employee.user.username, password="Temp@123")
        resp = self.client.get(reverse("change-password"))
        body = resp.content.decode()
        for field in ("id_old_password", "id_new_password1", "id_new_password2"):
            self.assertIn(f'data-password-toggle="{field}"', body,
                          f"no show/hide button for {field}")

    @override_settings(AUTH_PASSWORD_VALIDATORS=[
        {"NAME": LENGTH, "OPTIONS": {"min_length": 10}},
    ])
    def test_the_page_follows_a_changed_minimum(self):
        employee = self.make_employee(code="PRU003")
        self.client.login(username=employee.user.username, password="Temp@123")
        resp = self.client.get(reverse("change-password"))
        self.assertContains(resp, "At least 10 characters")
        self.assertNotContains(resp, "At least 8 characters")

    def test_the_reset_password_page_shows_the_same_checklist(self):
        employee = self.make_employee(code="PRU004")
        uid = urlsafe_base64_encode(str(employee.user.pk).encode())
        token = default_token_generator.make_token(employee.user)

        resp = self.client.get(
            reverse("password_reset_confirm", kwargs={"uidb64": uid, "token": token}),
            follow=True,
        )
        self.assertTrue(resp.context["validlink"])
        self.assertContains(resp, "At least 8 characters")
        self.assertContains(resp, 'data-password-toggle="id_new_password1"')
        self.assertContains(resp, 'data-password-toggle="id_new_password2"')


class NotAValidator:
    """Stand-in for a validator password_rules() has no label for."""

    def validate(self, password, user=None):
        return None
