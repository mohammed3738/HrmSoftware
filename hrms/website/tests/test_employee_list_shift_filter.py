"""Employee list: each row carries today's shift (day / night) for the
Shift filter -- today's Shift Roster entry first, else the employee's own
shift timings (night when they cross midnight). The profile's Night shift
tick is not used."""
from datetime import date, time, timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from website.models import Company, Employee, ShiftAssignment

NINE_TO_SIX = dict(shift_start_time=time(9), shift_end_time=time(18))
ELEVEN_TO_SIX = dict(shift_start_time=time(23), shift_end_time=time(6))


class EmployeeListShiftFilterTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(short_name="SF", name="Shift Co", phone="1", email="s@t.com", address="A")
        self.today = timezone.localdate()
        self.client = Client()
        self.client.force_login(User.objects.create_superuser("sf_su", "su@t.com", "pass12345"),
                                backend="django.contrib.auth.backends.ModelBackend")

    def emp(self, code, **kw):
        return Employee.objects.create(company=self.company, first_name=code, last_name="X", employee_code=code,
                                       date_of_joining=date(2020, 1, 1), status="Active", **kw)

    def roster(self, employee, start, end, **kw):
        ShiftAssignment.objects.create(employee=employee, shift_name="Rota", start_date=start, end_date=end,
                                       is_active=True, **kw)

    def shifts(self):
        resp = self.client.get(reverse("employee_list"))
        return {r["code"]: r["shift"] for r in resp.context["employees"]}

    def test_shift_timings_decide_without_a_roster(self):
        self.emp("DAY", **NINE_TO_SIX)
        self.emp("NIGHT", **ELEVEN_TO_SIX)
        self.emp("TICK_ONLY", is_night_shift=True, **NINE_TO_SIX)   # tick ignored, 9-6 is day
        self.assertEqual(self.shifts(), {"DAY": "day", "NIGHT": "night", "TICK_ONLY": "day"})

    def test_night_roster_overrides_day_timings_then_expires(self):
        e = self.emp("ROT", **NINE_TO_SIX)
        self.roster(e, self.today, self.today, **ELEVEN_TO_SIX)
        self.assertEqual(self.shifts(), {"ROT": "night"})
        ShiftAssignment.objects.all().delete()
        self.roster(e, self.today - timedelta(days=7), self.today - timedelta(days=1), **ELEVEN_TO_SIX)
        self.assertEqual(self.shifts(), {"ROT": "day"})                 # roster over -> timings again

    def test_day_roster_overrides_night_timings(self):
        e = self.emp("ROT2", **ELEVEN_TO_SIX)
        self.roster(e, self.today, self.today, **NINE_TO_SIX)
        self.assertEqual(self.shifts(), {"ROT2": "day"})

    def test_filter_is_on_the_page(self):
        self.emp("ANY")
        resp = self.client.get(reverse("employee_list"))
        self.assertContains(resp, 'id="shiftFilter"')
        self.assertContains(resp, '<option value="night">Night shift</option>', html=True)
