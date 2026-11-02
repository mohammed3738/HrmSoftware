"""Send one test email, to check the mail configuration.

Forgot Password is the only thing the application sends mail for, and
Django's PasswordResetView deliberately reports success whether or not the
message went out -- so a wrong App Password or a blocked port looks
exactly like a working reset from the outside. The only honest way to find
out is to send something and look.

    python manage.py send_test_email you@example.com

Prints the settings in use (never the password), sends, and says what came
back. Nothing in the database is touched and no account is involved.
"""
import socket
import smtplib

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send one test email to check EMAIL_HOST and friends."

    def add_arguments(self, parser):
        parser.add_argument(
            "recipient",
            help="Address to send the test message to.",
        )
        parser.add_argument(
            "--subject",
            default="HRMS test email",
            help="Subject line to use (default: 'HRMS test email').",
        )

    def handle(self, *args, **options):
        recipient = options["recipient"]
        if "@" not in recipient:
            raise CommandError(f"{recipient!r} is not an email address.")

        host = settings.EMAIL_HOST or "(not set)"
        sender = settings.DEFAULT_FROM_EMAIL
        self.stdout.write("Sending with:")
        self.stdout.write(f"  EMAIL_BACKEND      {settings.EMAIL_BACKEND}")
        self.stdout.write(f"  EMAIL_HOST         {host}")
        self.stdout.write(f"  EMAIL_PORT         {settings.EMAIL_PORT}")
        self.stdout.write(f"  EMAIL_USE_TLS      {settings.EMAIL_USE_TLS}")
        self.stdout.write(f"  EMAIL_USE_SSL      {settings.EMAIL_USE_SSL}")
        self.stdout.write(f"  EMAIL_HOST_USER    {settings.EMAIL_HOST_USER or '(not set)'}")
        # Say whether a password is present, never what it is.
        self.stdout.write(
            "  EMAIL_HOST_PASSWORD "
            + ("set" if settings.EMAIL_HOST_PASSWORD else "(not set)")
        )
        self.stdout.write(f"  DEFAULT_FROM_EMAIL {sender}")
        self.stdout.write(f"  -> {recipient}\n")

        message = EmailMessage(
            subject=options["subject"],
            body=(
                "This is a test message from HRMS.\n\n"
                "If you are reading it, the Forgot Password link on the login "
                "page can reach employees.\n"
            ),
            from_email=sender,
            to=[recipient],
        )

        try:
            # fail_silently stays off on purpose: the whole point is to see
            # the error.
            sent = message.send(fail_silently=False)
        except smtplib.SMTPAuthenticationError as exc:
            raise CommandError(
                "The mail server refused the username or password.\n"
                "With Gmail this is almost always the password: it needs a "
                "16-character App Password (Google Account -> Security -> "
                "2-Step Verification -> App passwords), not the account's "
                "normal password, and 2-Step Verification has to be on "
                f"first.\nServer said: {exc}"
            )
        except (socket.timeout, TimeoutError):
            raise CommandError(
                f"Timed out after {settings.EMAIL_TIMEOUT}s connecting to "
                f"{host}:{settings.EMAIL_PORT}. Usually a firewall blocking "
                "outbound SMTP, or the wrong port -- 587 goes with "
                "EMAIL_USE_TLS=true, 465 with EMAIL_USE_SSL=true."
            )
        except OSError as exc:
            raise CommandError(
                f"Could not reach {host}:{settings.EMAIL_PORT}: {exc}"
            )
        except ImproperlyConfigured as exc:
            # website.mail.UnconfiguredEmailBackend, i.e. DEBUG off and no
            # EMAIL_HOST. Its message already says what to set, so pass it
            # through as a clean error rather than a traceback.
            raise CommandError(str(exc))

        if not sent:
            raise CommandError(
                "The backend reported that nothing was sent, without raising. "
                "Check EMAIL_BACKEND above."
            )

        if settings.EMAIL_BACKEND.endswith("console.EmailBackend"):
            self.stdout.write(self.style.WARNING(
                "\nPrinted above instead of sent: EMAIL_BACKEND is the console "
                "backend, which is what you get with EMAIL_HOST unset and "
                "DEBUG on. Set EMAIL_HOST to send for real."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\nSent. Check {recipient}, including its spam folder."
            ))
