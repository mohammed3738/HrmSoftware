"""
Regression tests for `manage.py sync_biometric_attendance --dry-run`.

The dry run's promise is in its docstring: "what it prints is what would
happen". Once a real run could also mark days Absent, the preview stopped
keeping that promise in two different ways, and the second one was only
visible by actually running it:

1. It printed nothing about absences at all, because it only walks days
   that HAVE punches -- and the whole point of the absence pass is the days
   that do not.

2. Once it did list them, it listed people who had punched. A real run
   derives punch times first and only then looks for absences, so a day
   that gets an in-time is never an absence candidate. In a dry run no row
   has been written yet, so every employee looked like they had no
   attendance for the day, including the ones whose punches were being
   printed two lines above.

Both are the same underlying risk: a preview that over-reports absences
would have HR chasing people who were at work.

The test runs the preview and then the real sync over the same data and
requires them to agree, which is the property that actually matters and
cannot be faked by restating the implementation.

Run with:
    python manage.py test website.tests.test_sync_dry_run_preview
"""
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils.timezone import now

from website.models import Attendance, Company, PayrollSettings
from website.services import biometric_sync
from website.tests.test_biometric_sync import make_employee, punch


def _recent_weekday(days_back=2):
    day = now().date() - timedelta(days=days_back)
    while day.weekday() == 6:          # company weekend below is Sunday-only
        day -= timedelta(days=1)
    return day


DAY = _recent_weekday()


class SyncDryRunPreviewTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="DRY", name="Dry Run Co", phone="1",
            email="dry@test.com", address="Addr",
        )
        PayrollSettings.objects.create(company=self.company, weekend_days="sun")
        self.punctual = make_employee(self.company, "DRY001")
        self.missing = make_employee(self.company, "DRY002")

        biometric_sync.store_punches([
            punch("DRY001", DAY, "09:05:00"),
            punch("DRY001", DAY, "18:10:00"),
        ])

    def _dry_run(self):
        out = StringIO()
        call_command("sync_biometric_attendance", "--dry-run", "--days", "4", stdout=out)
        return out.getvalue()

    def test_the_preview_names_the_employee_who_did_not_punch(self):
        output = self._dry_run()
        self.assertIn("Would mark Absent", output)
        self.assertIn("DRY002", output)

    def test_the_preview_does_not_name_the_employee_who_did_punch(self):
        """The bug this pins: a dry run has written nothing, so without
        accounting for the punch pass the employee being shown as Present
        two lines earlier was also listed as a would-be absence."""
        output = self._dry_run()
        absent_section = output[output.index("Would mark Absent"):]
        self.assertNotIn("DRY001", absent_section)

    def test_the_dry_run_writes_nothing(self):
        self._dry_run()
        self.assertFalse(Attendance.objects.exists())

    def test_the_real_run_does_exactly_what_the_preview_said(self):
        preview = self._dry_run()
        absent_section = preview[preview.index("Would mark Absent"):]
        previewed_absent = {
            code for code in ("DRY001", "DRY002") if code in absent_section
        }

        call_command("sync_biometric_attendance", "--days", "4", stdout=StringIO())

        actually_absent = {
            row.employee.employee_code
            for row in Attendance.objects.select_related("employee").filter(status="Absent")
        }
        self.assertEqual(previewed_absent, actually_absent)
        self.assertEqual(actually_absent, {"DRY002"})

        # ...and the one who punched got their times, not an absence.
        present = Attendance.objects.get(employee=self.punctual, date=DAY)
        self.assertEqual(present.status, "Present")

    def test_a_range_with_no_matched_punches_previews_no_absences(self):
        Attendance.objects.all().delete()
        biometric_sync.BiometricPunch.objects.all().delete()
        output = self._dry_run()
        self.assertNotIn("Would mark Absent", output)
