"""
While the day runs, an employee who has punched in shows Present, even
with no out-punch yet or only a short span so far. Once the day is over,
finalize_finished_days() sets the real status from hours worked.

Run with: python manage.py test website.tests.test_attendance_day_in_progress
"""
import datetime
from datetime import date, time, timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from website.models import Attendance, Company, Employee, PayrollRun, PayrollSettings
from website.services.biometric_sync import finalize_finished_days

TZ = timezone.get_current_timezone()


def at(day, hh, mm=0):
    """Pretend the local clock reads `day hh:mm`."""
    return mock.patch(
        "django.utils.timezone.now",
        return_value=datetime.datetime.combine(day, time(hh, mm), tzinfo=TZ),
    )


def weekday_before(d):
    d -= timedelta(days=1)
    while d.weekday() == 6:
        d -= timedelta(days=1)
    return d


class AttendanceDayInProgressTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(short_name="DIP", name="Day Co", phone="1", email="d@t.com", address="A")
        PayrollSettings.objects.create(company=self.company, from_date=27, to_date=26, weekend_days="sun")
        self.emp = Employee.objects.create(company=self.company, first_name="Naz", last_name="M", employee_code="DIP1",
                                           date_of_joining=date(2020, 1, 1), status="Active")
        # A working weekday in the past, used as "today" by the fake clock.
        self.day = weekday_before(date.today())
        self.next_day = self.day + timedelta(days=1)

    def make(self, in_time, out_time=None):
        return Attendance.objects.create(employee=self.emp, date=self.day, in_time=in_time, out_time=out_time)

    def test_punched_in_without_out_is_present_during_the_day(self):
        with at(self.day, 11):
            row = self.make(time(9, 30))
        self.assertEqual((row.status, row.count), ("Present", Decimal("1.00")))

    def test_short_span_so_far_is_present_during_the_day(self):
        with at(self.day, 13):
            row = self.make(time(9, 30), time(12, 45))   # 3h15 so far -- would be Absent
        self.assertEqual(row.status, "Present")

    def test_no_punch_is_still_absent(self):
        with at(self.day, 11):
            row = self.make(None)
        self.assertEqual(row.status, "Absent")

    def test_day_end_sets_status_from_hours(self):
        with at(self.day, 17):
            half = self.make(time(9, 0), time(14, 0))         # 5h -> Half Day
        self.assertEqual(half.status, "Present")

        with at(self.next_day, 0, 20):
            finalize_finished_days()
        half.refresh_from_db()
        self.assertEqual((half.status, half.count), ("Half Day", Decimal("0.50")))

    def test_day_end_with_no_out_punch_is_absent(self):
        with at(self.day, 10):
            row = self.make(time(9, 30))
        self.assertEqual(row.status, "Present")
        with at(self.next_day, 0, 20):
            finalize_finished_days()
        row.refresh_from_db()
        self.assertEqual(row.status, "Absent")

    def test_full_day_stays_present_after_day_end(self):
        with at(self.day, 19):
            row = self.make(time(9, 0), time(18, 5))
        with at(self.next_day, 0, 20):
            finalize_finished_days()
        row.refresh_from_db()
        self.assertEqual(row.status, "Present")

    def test_night_shift_stays_present_until_out_window_closes(self):
        with at(self.day, 22):
            row = self.make(time(21, 0))
        self.assertEqual(row.status, "Present")
        with at(self.next_day, 6):           # out-punch not in yet, window open until 12:00
            finalize_finished_days()
        row.refresh_from_db()
        self.assertEqual(row.status, "Present")
        with at(self.next_day, 13):          # window closed, still no out-punch
            finalize_finished_days()
        row.refresh_from_db()
        self.assertEqual(row.status, "Absent")

    def test_manual_override_is_left_alone(self):
        with at(self.day, 10):
            row = self.make(time(9, 30))
        Attendance.objects.filter(pk=row.pk).update(status="Present", status_overridden=True)
        with at(self.next_day, 0, 20):
            finalize_finished_days()
        row.refresh_from_db()
        self.assertEqual(row.status, "Present")

    def test_payroll_locked_day_is_left_alone(self):
        with at(self.day, 10):
            row = self.make(time(9, 30))
        PayrollRun.objects.create(company=self.company, month=self.day.replace(day=1), start_date=self.day,
                                  end_date=self.day, status=PayrollRun.STATUS_FINALIZED)
        with at(self.next_day, 0, 20):
            finalize_finished_days()
        row.refresh_from_db()
        self.assertEqual(row.status, "Present")
