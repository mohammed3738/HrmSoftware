"""
The leave apply form no longer asks for a leave type.

Run with: python manage.py test website.tests.test_leave_apply_form
"""
from datetime import date

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from website.forms import LeaveApplicationForm
from website.models import Company, Employee, LeaveApplication


class LeaveApplyFormTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Leave Co", short_name="LVC", address="A")
        self.employee = Employee.objects.create(
            company=self.company, first_name="Lea", last_name="Ve", employee_code="LV001", status="Active",
        )
        admin = User.objects.create_superuser("lv_admin", "lv@test.com", "pass12345")
        self.client = Client()
        self.client.force_login(admin, backend="django.contrib.auth.backends.ModelBackend")

    def test_form_has_no_leave_type(self):
        self.assertNotIn("leave_type", LeaveApplicationForm().fields)
        resp = self.client.get(reverse("leave_apply"))
        self.assertNotContains(resp, 'name="leave_type"')

    def test_apply_without_leave_type(self):
        self.client.post(reverse("leave_apply"), {
            "employee": self.employee.pk, "start_date": "2026-11-02", "end_date": "2026-11-03", "reason": "Trip",
        })
        leave = LeaveApplication.objects.get()
        self.assertEqual((leave.leave_type, leave.start_date, leave.status), ("", date(2026, 11, 2), "Pending"))
