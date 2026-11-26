"""Employee list: each row carries today's shift (day / night) for the
Shift filter -- today's Shift Roster entry first, else the employee's own
Night shift setting, the same rule the biometric sync uses."""
from datetime import date, time

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from website.models import Company, Employee, ShiftAssignment


class EmployeeListShiftFilterTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(short_name="SF", name="Shift Co", phone="1", email="s@t.com", address="A")
        def emp(code, **kw):
            return Employee.objects.create(company=self.company, first_name=code, last_name="X", employee_code=code,
                                           date_of_joining=date(2020, 1, 1), status="Active", **kw)
        self.day = emp("SF1")
        self.night = emp("SF2", is_night_shift=True)
        self.rostered = emp("SF3")
        self.rostered_day = emp("SF4", is_night_shift=True)
        today = timezone.localdate()
        ShiftAssignment.objects.create(employee=self.rostered, shift_name="Night", start_date=today,
                                       end_date=today, is_night_shift=True, is_active=True)
        ShiftAssignment.objects.create(employee=self.rostered_day, shift_name="General", start_date=today,
                                       end_date=today, shift_start_time=time(9), shift_end_time=time(18),
                                       is_active=True)
        self.client = Client()
        self.client.force_login(User.objects.create_superuser("sf_su", "su@t.com", "pass12345"),
                                backend="django.contrib.auth.backends.ModelBackend")

    def test_rows_carry_todays_shift(self):
        resp = self.client.get(reverse("employee_list"))
        shifts = {r["code"]: r["shift"] for r in resp.context["employees"]}
        self.assertEqual(shifts, {"SF1": "day", "SF2": "night", "SF3": "night", "SF4": "day"})
        self.assertContains(resp, 'id="shiftFilter"')
        self.assertContains(resp, '<option value="night">Night shift</option>', html=True)
