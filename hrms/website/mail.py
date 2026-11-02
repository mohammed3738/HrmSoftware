"""Mail backend used when no mail server has been configured.

The Forgot Password flow is the one thing here that sends mail. Django's
default backend is SMTP on localhost:25, so on a server with no local mail
daemon `send_mail` raises a connection error deep inside the request --
and `PasswordResetView` deliberately reports success either way, so that
an attacker cannot use the form to discover which addresses exist. The two
together mean an employee is told "check your email" for a message that
was never sent, and nothing in the UI ever says otherwise.

This backend makes that case loud instead: it raises immediately, with the
name of the setting that is missing. settings.py selects it only when
EMAIL_HOST is unset and DEBUG is off, i.e. a real deployment that nobody
finished configuring.
"""
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend


class UnconfiguredEmailBackend(BaseEmailBackend):
    MESSAGE = (
        "This site cannot send email: EMAIL_HOST is not set. The Forgot "
        "Password link on the login page needs it. Set EMAIL_HOST, "
        "EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD and "
        "DEFAULT_FROM_EMAIL in the environment, or set EMAIL_BACKEND "
        "explicitly to choose a different backend."
    )

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if self.fail_silently:
            return 0
        raise ImproperlyConfigured(self.MESSAGE)
