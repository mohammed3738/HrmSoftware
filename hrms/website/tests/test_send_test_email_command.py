"""`manage.py send_test_email` -- the way to find out whether Forgot
Password can actually reach anybody.

It exists because PasswordResetView reports success whether or not the
message went out, so a wrong App Password looks identical to a working
reset. What is worth pinning is not that it can send -- Django's own
tests cover that -- but what it does when sending fails, since that is the
whole reason somebody runs it:

* an SMTP rejection has to come back as the App Password advice, not a
  traceback the reader has to interpret;
* a console backend must not be reported as "Sent", or the command would
  confirm a configuration that sends nothing;
* the password must never be printed.

Run with: python manage.py test website.tests.test_send_test_email_command
"""
import smtplib
from io import StringIO
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings


def run(*args, **options):
    out = StringIO()
    call_command("send_test_email", *args, stdout=out, stderr=out, **options)
    return out.getvalue()


class SendTestEmailCommandTest(SimpleTestCase):
    def test_it_sends_one_message_to_the_given_address(self):
        output = run("someone@example.test")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["someone@example.test"])
        self.assertIn("Sent", output)

    def test_it_refuses_something_that_is_not_an_address(self):
        with self.assertRaises(CommandError):
            run("not-an-address")
        self.assertEqual(len(mail.outbox), 0)

    # -- what it prints ---------------------------------------------------

    @override_settings(
        EMAIL_HOST="smtp.gmail.com",
        EMAIL_HOST_USER="hr@example.test",
        EMAIL_HOST_PASSWORD="abcdefghijklmnop",
    )
    def test_it_never_prints_the_password(self):
        output = run("someone@example.test")
        self.assertNotIn("abcdefghijklmnop", output)
        self.assertIn("smtp.gmail.com", output)
        self.assertIn("hr@example.test", output)
        self.assertIn("set", output)  # says one is present, not what it is

    @override_settings(EMAIL_HOST_PASSWORD="")
    def test_it_says_when_no_password_is_configured(self):
        self.assertIn("(not set)", run("someone@example.test"))

    # -- what it does when sending fails ----------------------------------

    def test_a_rejected_login_is_reported_as_the_app_password_problem(self):
        """Gmail answers a normal account password with an authentication
        error, which is the single most likely way this is misconfigured."""
        failure = smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")
        with mock.patch("django.core.mail.EmailMessage.send", side_effect=failure):
            with self.assertRaises(CommandError) as caught:
                run("someone@example.test")
        message = str(caught.exception)
        self.assertIn("App Password", message)
        self.assertIn("2-Step Verification", message)

    def test_a_blocked_port_is_reported_as_a_timeout_with_the_port_advice(self):
        with mock.patch("django.core.mail.EmailMessage.send", side_effect=TimeoutError):
            with self.assertRaises(CommandError) as caught:
                run("someone@example.test")
        message = str(caught.exception)
        self.assertIn("Timed out", message)
        self.assertIn("587", message)

    @override_settings(
        EMAIL_BACKEND="website.mail.UnconfiguredEmailBackend", EMAIL_HOST="")
    def test_no_mail_server_at_all_is_a_clean_message_not_a_traceback(self):
        """Somebody runs this command precisely because something is wrong;
        answering with a stack trace makes them read Django's internals to
        find out that EMAIL_HOST is unset."""
        with self.assertRaises(CommandError) as caught:
            run("someone@example.test")
        self.assertIn("EMAIL_HOST", str(caught.exception))

    def test_a_backend_that_silently_sends_nothing_is_not_called_success(self):
        with mock.patch("django.core.mail.EmailMessage.send", return_value=0):
            with self.assertRaises(CommandError) as caught:
                run("someone@example.test")
        self.assertIn("nothing was sent", str(caught.exception))

    # -- the console backend is not "sent" --------------------------------

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_the_console_backend_is_reported_as_printed_not_sent(self):
        """Otherwise the command would confirm a configuration that mails
        nobody."""
        with mock.patch("django.core.mail.EmailMessage.send", return_value=1):
            output = run("someone@example.test")
        self.assertIn("instead of sent", output)
        self.assertNotIn("Check someone@example.test", output)
