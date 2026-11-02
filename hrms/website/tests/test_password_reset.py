"""Forgot Password, from the link on the login page to a working sign-in.

Covers the whole flow rather than each view, because the parts that can
break are the joins: the link on the login page, the address lookup, the
signed token, and what the reset leaves behind on the Employee record.

Three behaviours here are specific to this application and are the reason
these tests exist rather than trusting Django's own:

* an employee who has never signed in has force_password_change=True and
  the shared temporary password. Finishing a reset has to clear that flag,
  or ForcePasswordChangeMiddleware sends them straight back to the
  change-password page and asks for a current password they do not have.
* an employee whose status is "Left" must not be able to reset. That holds
  through two separate pieces -- the signal deactivates the user, and
  Django's form only mails active users -- so it is worth pinning.
* the form must not reveal whether an address has an account.

Run with: python manage.py test website.tests.test_password_reset
"""
import re
from datetime import date

from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from website.models import Company, Employee


class PasswordResetFlowTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.company = Company.objects.create(
            short_name="PWR", name="Password Reset Co", phone="1",
            email="pwr@test.com", address="Addr",
        )
        self.employee = self.make_employee("PWR001", "rahul@example.test")
        self.user = self.employee.user
        mail.outbox = []

    def make_employee(self, code, email, status="Active"):
        return Employee.objects.create(
            company=self.company, salutation="Mr", first_name="Rahul",
            last_name="Kulkarni", father_name="Father", gender="Male",
            blood_group="O+", date_of_birth=date(1990, 1, 1), place_of_birth="Pune",
            personal_email=email, present_address="Addr", permanent_address="Addr",
            personal_mobile="1234567890", employee_code=code,
            designation="Operator", department="Production",
            date_of_joining=date(2020, 1, 1), location="Pune",
            pan_no="ABCDE1234F", aadhar_no="123456789012",
            name_as_per_bank="Rahul Kulkarni", salary_account_number="1234567890",
            ifsc_code="TEST0001234", emergency_contact_name1="Spouse",
            emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status=status,
        )

    def reset_link_from_outbox(self):
        """The /reset/<uid>/<token>/ path out of the mailed message."""
        self.assertEqual(len(mail.outbox), 1, "no reset email was sent")
        match = re.search(r"/reset/[^/\s]+/[^/\s]+/", mail.outbox[0].body)
        self.assertIsNotNone(match, "no reset link in the email body")
        return match.group(0)

    # -- the way in -------------------------------------------------------

    def test_the_login_page_links_to_forgot_password(self):
        resp = self.client.get(reverse("login"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse("password-reset"))
        self.assertContains(resp, "Forgot password?")

    def test_the_forgot_password_page_opens_without_signing_in(self):
        resp = self.client.get(reverse("password-reset"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Send reset link")

    # -- end to end -------------------------------------------------------

    def test_an_employee_can_reset_and_then_sign_in(self):
        resp = self.client.post(reverse("password-reset"), {"email": "rahul@example.test"})
        self.assertRedirects(resp, reverse("password-reset-done"))

        link = self.reset_link_from_outbox()
        # The emailed URL redirects to the form at .../set-password/, which
        # is where the token lives for the duration of the POST.
        resp = self.client.get(link, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Set a new password")

        resp = self.client.post(resp.request["PATH_INFO"], {
            "new_password1": "KulkarniRahul",
            "new_password2": "KulkarniRahul",
        })
        self.assertRedirects(resp, reverse("password-reset-complete"))

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("KulkarniRahul"))
        self.assertTrue(
            self.client.login(username="PWR001", password="KulkarniRahul"),
            "the new password does not work on the login page",
        )

    def test_the_mailed_link_cannot_be_used_twice(self):
        self.client.post(reverse("password-reset"), {"email": "rahul@example.test"})
        link = self.reset_link_from_outbox()

        resp = self.client.get(link, follow=True)
        self.client.post(resp.request["PATH_INFO"], {
            "new_password1": "KulkarniRahul", "new_password2": "KulkarniRahul",
        })

        # Same link again: the token no longer matches the changed password
        # hash, so the form is refused rather than silently reusable.
        resp = self.client.get(link, follow=True)
        self.assertFalse(resp.context["validlink"])
        self.assertContains(resp, "This link no longer works")

    # -- what the reset has to clear --------------------------------------

    def test_finishing_a_reset_clears_force_password_change(self):
        """Otherwise the employee is bounced to change-password and asked
        for a current password they never had."""
        self.employee.refresh_from_db()
        self.assertTrue(
            self.employee.force_password_change,
            "precondition: an auto-provisioned login starts with the flag set",
        )

        self.client.post(reverse("password-reset"), {"email": "rahul@example.test"})
        link = self.reset_link_from_outbox()
        resp = self.client.get(link, follow=True)
        self.client.post(resp.request["PATH_INFO"], {
            "new_password1": "KulkarniRahul", "new_password2": "KulkarniRahul",
        })

        self.employee.refresh_from_db()
        self.assertFalse(self.employee.force_password_change)

        # And the proof that it mattered: a dashboard request is no longer
        # redirected to the change-password page.
        self.client.login(username="PWR001", password="KulkarniRahul")
        resp = self.client.get(reverse("employee-dashboard"))
        self.assertNotEqual(
            resp.status_code, 302,
            "still being forced to the change-password page after a reset",
        )

    # -- who cannot reset -------------------------------------------------

    def test_an_employee_who_has_left_gets_no_reset_email(self):
        left = self.make_employee("PWR002", "gone@example.test")
        left.status = "Left"
        left.save()
        left.user.refresh_from_db()
        self.assertFalse(left.user.is_active, "precondition: the login is deactivated")

        resp = self.client.post(reverse("password-reset"), {"email": "gone@example.test"})
        self.assertRedirects(resp, reverse("password-reset-done"))
        self.assertEqual(len(mail.outbox), 0, "a former employee was mailed a reset link")

    # -- and what it does not give away -----------------------------------

    def test_an_unknown_address_looks_exactly_like_a_known_one(self):
        """The page must not become a way to test which addresses exist."""
        known = self.client.post(reverse("password-reset"), {"email": "rahul@example.test"})
        known_page = self.client.get(reverse("password-reset-done")).content
        mail.outbox = []
        unknown = self.client.post(reverse("password-reset"), {"email": "nobody@example.test"})
        unknown_page = self.client.get(reverse("password-reset-done")).content

        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known["Location"], unknown["Location"])
        self.assertEqual(known_page, unknown_page)
        self.assertEqual(len(mail.outbox), 0)

    # -- the email itself -------------------------------------------------

    @override_settings(PASSWORD_RESET_TIMEOUT=60 * 60 * 4)
    def test_the_email_says_who_it_is_for_and_how_long_it_lasts(self):
        self.client.post(reverse("password-reset"), {"email": "rahul@example.test"})
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertIn("Reset your HRMS password", message.subject)
        self.assertIn("PWR001", message.body)
        self.assertIn("4 hours", message.body)
        self.assertEqual(message.to, ["rahul@example.test"])


class UnconfiguredEmailBackendTest(TestCase):
    """A deployment with no EMAIL_HOST must fail loudly, not silently.

    PasswordResetView reports success whether or not mail went out, so a
    broken mail configuration would otherwise leave an employee waiting
    for a message that was never sent, with nothing anywhere saying so.
    """

    @override_settings(EMAIL_BACKEND="website.mail.UnconfiguredEmailBackend")
    def test_sending_raises_and_names_the_missing_setting(self):
        from django.core.exceptions import ImproperlyConfigured

        with self.assertRaises(ImproperlyConfigured) as caught:
            mail.send_mail("subject", "body", "from@test.com", ["to@test.com"])
        self.assertIn("EMAIL_HOST", str(caught.exception))
