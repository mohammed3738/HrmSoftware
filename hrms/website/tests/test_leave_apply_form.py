"""
The leave apply form no longer asks for a leave type.

Run with: python manage.py test website.tests.test_leave_apply_form
"""
from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from website.forms import LeaveApplicationForm
from website.models import Company, Employee, LeaveApplication, LeaveBalance
from website.views import leave_apply_view


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

    def test_balance_month_uses_period_end_across_new_year(self):
        self.employee.user = User.objects.get(username="lv_admin")
        self.employee.save(update_fields=["user"])
        december = LeaveBalance.objects.create(employee=self.employee, period_from_date=date(2026, 11, 27),
                                               period_to_date=date(2026, 12, 26))
        january = LeaveBalance.objects.create(employee=self.employee, period_from_date=date(2026, 12, 27),
                                              period_to_date=date(2027, 1, 26))
        for today, periods in [(date(2026, 11, 30), []), (date(2026, 12, 31), [december]),
                               (date(2027, 1, 1), [january, december])]:
            with self.subTest(today=today), patch("website.views.timezone.localdate", return_value=today):
                request = RequestFactory().get(reverse("leave_apply"))
                request.user = self.employee.user
                response = leave_apply_view(request)
                for row in (december, january):
                    self.assertContains(response, f'data-balance-period="{row.pk}"', count=int(row in periods))
                if periods:
                    self.assertContains(response, f'data-balance-period="{periods[0].pk}">')

    def test_apply_without_leave_type(self):
        self.client.post(reverse("leave_apply"), {
            "employee": self.employee.pk, "start_date": "2026-11-02", "end_date": "2026-11-03", "reason": "Trip",
        })
        leave = LeaveApplication.objects.get()
        self.assertEqual((leave.leave_type, leave.start_date, leave.status), ("", date(2026, 11, 2), "Pending"))

    def test_reversed_dates_redisplay_reason_and_field_error(self):
        response = self.client.post(reverse("leave_apply"), {
            "employee": self.employee.pk, "start_date": "2026-11-03", "end_date": "2026-11-02", "reason": "Travel",
        })
        self.assertIn("end_date", response.context["form"].errors)
        self.assertContains(response, "Travel")
        self.assertFalse(LeaveApplication.objects.exists())

    def test_leave_type_search_keeps_status_and_query_on_next_page(self):
        rows = [LeaveApplication(employee=self.employee, start_date=date(2026, 11, 2),
                                 end_date=date(2026, 11, 2), reason="Day off", leave_type="CL")
                for _ in range(9)]
        LeaveApplication.objects.bulk_create(rows)
        response = self.client.get(reverse("leave_apply"), {"status": "Pending", "search": "casual leave"})
        self.assertEqual(response.context["leaves"].paginator.count, 9)
        self.assertContains(response, 'href="?status=Pending&amp;search=casual+leave&amp;page=2"')
