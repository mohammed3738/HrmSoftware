"""
Site password policy: a name or surname IS allowed as a password.

Django ships UserAttributeSimilarityValidator on by default, and it is what
produced "new_password2: The password is too similar to the first name." on
the change-password form. The policy here is deliberately the other way --
staff set passwords from their own names -- so that validator is off unless
PASSWORD_FORBID_USER_ATTRIBUTES is set.

Two things worth pinning beyond the headline:

* the list used to be declared TWICE in settings.py, with the second copy
  silently winning, so an edit to the first one did nothing. These tests
  read settings.AUTH_PASSWORD_VALIDATORS as Django resolved it, which is
  the copy that actually applies.
* relaxing the name rule must not quietly relax the rest. A 3-character
  password, "password" and an all-digit password are still refused.

Run with: python manage.py test website.tests.test_password_policy
"""
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import (
    get_default_password_validators,
    validate_password,
)
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse


def _validator_names():
    return {type(v).__name__ for v in get_default_password_validators()}


class PasswordPolicyTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="rkulkarni", email="rahul@test.com", password="Initial@12345",
            first_name="Rahul", last_name="Kulkarni",
        )

    # ── the headline ─────────────────────────────────────────────────────

    def test_a_password_built_from_the_users_own_name_is_accepted(self):
        for candidate in ("RahulKulkarni", "rahul.kulkarni", "Kulkarni1988"):
            with self.subTest(candidate=candidate):
                validate_password(candidate, self.user)  # must not raise

    def test_the_user_attribute_similarity_validator_is_not_enabled(self):
        self.assertNotIn("UserAttributeSimilarityValidator", _validator_names())

    def test_the_change_password_form_accepts_the_users_surname(self):
        client = Client()
        self.assertTrue(client.login(username="rkulkarni", password="Initial@12345"))
        resp = client.post(reverse("change-password"), {
            "old_password": "Initial@12345",
            "new_password1": "KulkarniRahul",
            "new_password2": "KulkarniRahul",
        })
        self.assertEqual(resp.status_code, 302, "the name-based password was rejected")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("KulkarniRahul"))

    # ── and the check can be put back ────────────────────────────────────

    @override_settings(AUTH_PASSWORD_VALIDATORS=[
        {"NAME": "django.contrib.auth.password_validation."
                 "UserAttributeSimilarityValidator"},
    ])
    def test_the_similarity_check_still_works_when_switched_back_on(self):
        with self.assertRaises(ValidationError):
            validate_password("Rahul", self.user)

    # ── the rest of the policy is unchanged ──────────────────────────────

    def test_a_short_password_is_still_refused(self):
        with self.assertRaises(ValidationError):
            validate_password("Ram", self.user)

    def test_a_common_password_is_still_refused(self):
        with self.assertRaises(ValidationError):
            validate_password("password", self.user)

    def test_an_all_numeric_password_is_still_refused(self):
        with self.assertRaises(ValidationError):
            validate_password("19880304", self.user)

    def test_the_remaining_validators_are_all_present(self):
        self.assertEqual(
            _validator_names(),
            {"MinimumLengthValidator", "CommonPasswordValidator",
             "NumericPasswordValidator"},
        )
