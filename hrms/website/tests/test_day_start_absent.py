"""
Start of day: every active employee gets a row for today -- Absent on a
working day (Weekend / Holiday otherwise) -- and a punch from the biometric
sync, an Excel upload or field duty then turns it Present / Late / Half Day
by the usual in/out rules. If the punch machine reported nothing for a
finished day, the untouched start-of-day Absent rows are released again so
a device outage can't cost anybody pay.

Run with: python manage.py test website.tests.test_day_start_absent
"""
from datetime import date, time, timedelta
from unittest import mock

from django.test import TestCase

from website.models import Attendance, Company, Employee, PayrollSettings
from website.services import biometric_sync

WEDNESDAY = date(2026, 11, 18)
SUNDAY = date(2026, 11, 22)


class DayStartAbsentTest(TestCase):
    def setUp(self):
        company = Company.objects.create(short_name="DSA", name="Day Start Co", phone="1", email="d@t.com", address="A")
        PayrollSettings.objects.create(company=company, weekend_days="sun")

        def emp(code, **kw):
            kw.setdefault("date_of_joining", date(2020, 1, 1))
            kw.setdefault("status", "Active")
            return Employee.objects.create(company=company, first_name=code, last_name="X", employee_code=code, **kw)

        self.ann = emp("DS1")
        self.bob = emp("DS2")
        self.newbie = emp("DS3", date_of_joining=WEDNESDAY + timedelta(days=5))
        self.gone = emp("DS4", status="Left")

    def _row(self, employee, day=WEDNESDAY):
        return Attendance.objects.filter(employee=employee, date=day).first()

    def test_working_day_marks_everyone_absent(self):
        counters = biometric_sync.mark_day_start(WEDNESDAY)
        self.assertEqual(counters["absent_created"], 2)
        for e in (self.ann, self.bob):
            row = self._row(e)
            self.assertEqual(row.status, "Absent")
            self.assertTrue(row.auto_absent)
        self.assertIsNone(self._row(self.newbie))  # not joined yet
        self.assertIsNone(self._row(self.gone))    # has left

    def test_weekend_is_marked_weekend_not_absent(self):
        biometric_sync.mark_day_start(SUNDAY)
        row = self._row(self.ann, SUNDAY)
        self.assertEqual(row.status, "Weekend")
        self.assertFalse(row.auto_absent)

    def test_existing_row_is_left_alone(self):
        Attendance.objects.create(employee=self.ann, date=WEDNESDAY, in_time=time(9), out_time=time(18))
        biometric_sync.mark_day_start(WEDNESDAY)
        row = self._row(self.ann)
        self.assertEqual(row.in_time, time(9))
        self.assertFalse(row.auto_absent)

    def test_running_twice_is_harmless(self):
        biometric_sync.mark_day_start(WEDNESDAY)
        self.assertEqual(biometric_sync.mark_day_start(WEDNESDAY)["absent_created"], 0)
        self.assertEqual(Attendance.objects.filter(date=WEDNESDAY).count(), 2)

    def test_biometric_punch_turns_absent_into_present(self):
        biometric_sync.mark_day_start(WEDNESDAY)
        with mock.patch.object(biometric_sync, "future_punch_cutoff", return_value=WEDNESDAY + timedelta(days=1)):
            biometric_sync.ingest([
                {"device_user_id": "DS1", "employee_code": "DS1", "punch_date": WEDNESDAY.isoformat(), "punch_time": "09:00:00"},
                {"device_user_id": "DS1", "employee_code": "DS1", "punch_date": WEDNESDAY.isoformat(), "punch_time": "18:30:00"},
            ])
        row = self._row(self.ann)
        self.assertEqual((row.in_time, row.out_time), (time(9), time(18, 30)))
        self.assertNotEqual(row.status, "Absent")
        self.assertEqual(self._row(self.bob).status, "Absent")  # no punch, still absent

    def test_excel_style_save_applies_in_out_rule(self):
        biometric_sync.mark_day_start(WEDNESDAY)
        row = self._row(self.bob)
        row.in_time, row.out_time = time(9), time(14)  # 5h: Half Day (needs 4.5h); what the upload does, then save()
        row.save()
        row.refresh_from_db()
        self.assertIn(row.status, {"Half Day", "Present (Half-Day)"})

    def test_outage_day_placeholders_are_released(self):
        biometric_sync.mark_day_start(WEDNESDAY)
        with mock.patch("django.utils.timezone.localdate", return_value=WEDNESDAY + timedelta(days=1)):
            released = biometric_sync.release_unreported_day_start_absences()
        self.assertEqual(released, 2)  # the machine reported nothing that day
        self.assertIsNone(self._row(self.ann))

    def test_reported_day_placeholders_are_kept(self):
        biometric_sync.mark_day_start(WEDNESDAY)
        with mock.patch.object(biometric_sync, "future_punch_cutoff", return_value=WEDNESDAY + timedelta(days=1)):
            biometric_sync.ingest([
                {"device_user_id": "DS1", "employee_code": "DS1", "punch_date": WEDNESDAY.isoformat(), "punch_time": "09:00:00"},
            ])
        with mock.patch("django.utils.timezone.localdate", return_value=WEDNESDAY + timedelta(days=1)):
            self.assertEqual(biometric_sync.release_unreported_day_start_absences(), 0)
        self.assertEqual(self._row(self.bob).status, "Absent")  # a real absence: the machine was working

    def test_manual_absence_is_never_released(self):
        Attendance.objects.create(employee=self.ann, date=WEDNESDAY)  # recorded absence, not auto
        with mock.patch("django.utils.timezone.localdate", return_value=WEDNESDAY + timedelta(days=1)):
            biometric_sync.release_unreported_day_start_absences()
        self.assertIsNotNone(self._row(self.ann))

    def test_task_runs(self):
        from website.tasks import mark_day_start_task
        with mock.patch("django.utils.timezone.localdate", return_value=WEDNESDAY):
            result = mark_day_start_task()
        self.assertEqual(result["absent_created"], 2)
