"""
The employee form says why it didn't save -- including problems in the
Previous Employment and KYC tabs -- and every page shows Django messages
(saved / sent for approval / errors), which base2.html used to drop.

Run with: python manage.py test website.tests.test_employee_form_errors
"""
from datetime import date, timedelta

from django.contrib.auth.models import Group, User
from django.forms.models import model_to_dict
from django.test import Client, TestCase
from django.urls import reverse

from website.forms import AttachmentFormSet, PreviousEmploymentFormSet
from website.models import Company, Employee, EmployeeChangeRequest


class EmployeeFormErrorsTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Err Co", short_name="ERR", address="A")
        self.emp = Employee.objects.create(company=self.company, first_name="Err", last_name="One",
                                           employee_code="ERR1", status="Active")
        Employee.objects.create(company=self.company, first_name="Taken", last_name="Code",
                                employee_code="TAKEN", status="Active")
        self.admin = self._client("Admin")
        self.hr = self._client("HR")

    def _client(self, role):
        user = User.objects.create_user(username=f"err_{role}", password="pass12345")
        user.groups.add(Group.objects.get(name=role))
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return client

    def _data(self, emp=None, **changes):
        emp = emp or Employee.objects.get(pk=self.emp.pk)
        data = {k: v for k, v in model_to_dict(emp).items() if v is not None and k != "photo"}
        for fs in (PreviousEmploymentFormSet(instance=emp), AttachmentFormSet(instance=emp)):
            for name in ("TOTAL_FORMS", "INITIAL_FORMS", "MIN_NUM_FORMS", "MAX_NUM_FORMS"):
                data[f"{fs.prefix}-{name}"] = fs.management_form[name].value()
        data.update(changes)
        return data

    def test_duplicate_code_is_reported_in_the_form(self):
        resp = self.admin.post(reverse("employee_edit", args=[self.emp.pk]), self._data(employee_code="TAKEN"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "The employee was not saved. Please fix:")
        self.assertContains(resp, "Employee Code")
        self.assertContains(resp, "The employee was not saved. Please fix the problems listed in the form.")

    def test_previous_employment_row_errors_are_listed_and_tab_flagged(self):
        prefix = PreviousEmploymentFormSet(instance=self.emp).prefix
        resp = self.admin.post(reverse("employee_edit", args=[self.emp.pk]), self._data(**{
            f"{prefix}-TOTAL_FORMS": 1, f"{prefix}-0-employer_name": "Old Co",
        }))
        errors = resp.context["form_errors"]
        self.assertTrue(any(e["tab"] == "previous-employment" and "row 1" in e["field"] for e in errors), errors)
        self.assertIn("previous-employment", resp.context["error_tabs"])
        self.assertContains(resp, 'showTab("previous-employment")')

    def test_successful_save_message_is_shown(self):
        resp = self.admin.post(reverse("employee_edit", args=[self.emp.pk]), self._data(designation="Lead"), follow=True)
        self.assertContains(resp, "Employee updated successfully!")
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.designation, "Lead")

    def test_hr_is_told_the_edit_went_for_approval(self):
        Employee.objects.filter(pk=self.emp.pk).update(onboarding_started_at=date.today() - timedelta(days=30))
        resp = self.hr.post(reverse("employee_edit", args=[self.emp.pk]), self._data(designation="Lead"), follow=True)
        self.assertContains(resp, "were sent for approval")
        self.assertTrue(EmployeeChangeRequest.objects.filter(employee=self.emp).exists())

    def test_messages_show_once_on_pages_that_used_to_print_their_own(self):
        from django.contrib.messages import get_messages  # noqa: F401
        session = self.admin.session
        session.save()
        # Trigger a message, then load the holiday dashboard.
        self.admin.post(reverse("add-holiday"), {"holiday_date": "", "name": "", "branch_scope": "selected"})
        page = self.admin.get(reverse("holiday-calendar")).content.decode()
        self.assertEqual(page.count("Select at least one branch"), 1)
