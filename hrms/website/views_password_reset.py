"""Forgot Password, reached from the link on the login page.

Django's four-step reset flow (ask for the address -> mail a signed link ->
set a new password -> done) is used as-is; what is here is the glue this
application needs on top of it.

Two things are not Django defaults and are the reason this module exists:

* `force_password_change` has to be cleared when a reset completes. Every
  auto-provisioned login starts with the shared temporary password and
  `force_password_change=True`, and ForcePasswordChangeMiddleware bounces
  such a user to the change-password page on every request. An employee
  who never signed in, used Forgot Password and set a real password would
  still be told to change it again -- with an old password they do not
  have. `change_password` already clears the flag; so does this.

* `Employee.status == "Left"` must not be able to reset. That is already
  true, but only indirectly: the Employee signal sets `user.is_active =
  False` on leaving, and Django's PasswordResetForm only mails active
  users. `test_password_reset.py` pins it so the two stay connected.

The address is never confirmed or denied on screen -- the "check your
email" page is shown whether or not the address belongs to an account.
That is Django's behaviour and it is deliberate: the form would otherwise
tell an unauthenticated visitor which of their guesses are real accounts.
"""
from django.conf import settings
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy

from website.utils.password_rules import password_rules


def reset_timeout_hours():
    """PASSWORD_RESET_TIMEOUT in whole hours, for the pages and the email.

    Both say how long the link lasts, and saying it in seconds would be
    useless to the reader. Rounded up, so a 90-minute timeout never reads
    as "1 hour" to someone who then waits.
    """
    seconds = settings.PASSWORD_RESET_TIMEOUT
    return max(1, -(-seconds // 3600))


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "auth/password_reset_form.html"
    email_template_name = "auth/password_reset_email.txt"
    subject_template_name = "auth/password_reset_subject.txt"
    success_url = reverse_lazy("password-reset-done")

    @property
    def extra_email_context(self):
        """Read by Django's form_valid and passed to the email template,
        which says how long the link lasts. A property rather than a class
        attribute so a changed PASSWORD_RESET_TIMEOUT is picked up without
        a reimport."""
        return {"reset_timeout_hours": reset_timeout_hours()}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Shown on the form so a developer on a machine with no mail server
        # knows where the link went, instead of waiting for an email that
        # was printed to the console. Never shown on a real deployment.
        context["email_goes_to_console"] = (
            settings.EMAIL_BACKEND.endswith("console.EmailBackend"))
        return context


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "auth/password_reset_done.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["reset_timeout_hours"] = reset_timeout_hours()
        return context


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "auth/password_reset_confirm.html"
    success_url = reverse_lazy("password-reset-complete")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Drives the live checklist on the page, read off the configured
        # validators so it cannot promise what the server will refuse.
        context["password_rules"] = password_rules()
        context["reset_timeout_hours"] = reset_timeout_hours()
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        # super() has saved the new password; self.user is the account.
        employee = getattr(self.user, "employee_profile", None)
        if employee is not None and employee.force_password_change:
            employee.force_password_change = False
            employee.save(update_fields=["force_password_change"])
        return response


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "auth/password_reset_complete.html"
