"""
Regression tests for Holiday.backfill_attendance(): when attendance for a
holiday was never uploaded (nobody expected to punch in), employees should
still get a proper 'Holiday' Attendance row instead of appearing as missing
or (via the daily upload job) Absent.
Run with: python manage.py test website.tests.test_holiday_backfill_attendance
"""
from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase

from website.models import (
    Company, Employee, Attendance, Holiday, HolidayType, HolidayCalendar,
    Branch, PayrollSettings,
)


class HolidayBackfillAttendanceTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Test Co")
        self.branch = Branch.objects.create(branch_name="Main Branch")
        self.other_branch = Branch.objects.create(branch_name="Other Branch")
        self.user = User.objects.create_superuser("admin", "admin@test.com", "pass12345")
        self.htype = HolidayType.objects.create(name="National", type_category="national")

        self._code_seq = 0

        def make_employee(first_name, branch=None, status="Active",
                           date_of_joining=date(2020, 1, 1)):
            self._code_seq += 1
            code = f"EMP{self._code_seq:03d}"
            return Employee.objects.create(
                company=self.company, branch=branch or self.branch,
                salutation="Mr", first_name=first_name, last_name="Doe",
                father_name="Robert Doe", gender="Male", blood_group="O+",
                date_of_birth=date(1990, 1, 1), place_of_birth="Test City",
                personal_email=f"{code}@test.com", present_address="123 Test St",
                permanent_address="123 Test St", personal_mobile="1234567890",
                employee_code=code, designation="Developer", department="IT",
                date_of_joining=date_of_joining, location="Test Location",
                pan_no="ABCDE1234F", aadhar_no="123456789012",
                name_as_per_bank=first_name, salary_account_number="1234567890",
                ifsc_code="TEST0001234", emergency_contact_name1="Jane Doe",
                emergency_contact_relation1="Spouse", emergency_contact_mobile1="0987654321",
                status=status,
            )

        self.make_employee = make_employee

    def test_backfill_creates_holiday_attendance_for_missing_records(self):
        emp1 = self.make_employee("One")
        emp2 = self.make_employee("Two")
        diwali = date(2026, 9, 1)  # a Tuesday
        holiday = Holiday.objects.create(
            holiday_date=diwali, name="Diwali", holiday_type=self.htype, created_by=self.user,
        )

        created = holiday.backfill_attendance()

        self.assertEqual(created, 2)
        att1 = Attendance.objects.get(employee=emp1, date=diwali)
        att2 = Attendance.objects.get(employee=emp2, date=diwali)
        self.assertEqual(att1.status, "Holiday")
        self.assertEqual(att2.status, "Holiday")

    def test_backfill_does_not_overwrite_existing_attendance(self):
        emp1 = self.make_employee("One")
        diwali = date(2026, 9, 1)
        holiday = Holiday.objects.create(
            holiday_date=diwali, name="Diwali", holiday_type=self.htype, created_by=self.user,
        )

        # This employee actually worked that day (or has a correction) --
        # backfill must never clobber it.
        existing = Attendance.objects.create(
            employee=emp1, date=diwali, in_time=time(9, 0), out_time=time(18, 0),
        )
        existing.refresh_from_db()
        original_status = existing.status

        created = holiday.backfill_attendance()

        self.assertEqual(created, 0)
        existing.refresh_from_db()
        self.assertEqual(existing.in_time, time(9, 0))
        self.assertEqual(existing.out_time, time(18, 0))
        self.assertEqual(existing.status, original_status)

    def test_backfill_excludes_inactive_employees(self):
        self.make_employee("Left", status="Inactive")
        diwali = date(2026, 9, 1)
        holiday = Holiday.objects.create(
            holiday_date=diwali, name="Diwali", holiday_type=self.htype, created_by=self.user,
        )

        created = holiday.backfill_attendance()

        self.assertEqual(created, 0)
        self.assertEqual(Attendance.objects.filter(date=diwali).count(), 0)

    def test_backfill_excludes_employees_hired_after_holiday(self):
        self.make_employee("Future", date_of_joining=date(2026, 12, 1))
        diwali = date(2026, 9, 1)
        holiday = Holiday.objects.create(
            holiday_date=diwali, name="Diwali", holiday_type=self.htype, created_by=self.user,
        )

        created = holiday.backfill_attendance()

        self.assertEqual(created, 0)
        self.assertEqual(Attendance.objects.filter(date=diwali).count(), 0)

    def test_backfill_respects_specific_employees_scoping(self):
        selected = self.make_employee("Selected")
        other = self.make_employee("Other")
        eid = date(2026, 9, 3)
        holiday = Holiday.objects.create(
            holiday_date=eid, name="Eid", holiday_type=self.htype,
            created_by=self.user, applies_to_all_employees=False,
        )
        holiday.specific_employees.add(selected)

        created = holiday.backfill_attendance()

        self.assertEqual(created, 1)
        self.assertTrue(Attendance.objects.filter(employee=selected, date=eid).exists())
        self.assertFalse(Attendance.objects.filter(employee=other, date=eid).exists())

    def test_backfill_respects_branch_specific_holiday_scoping(self):
        PayrollSettings.objects.create(company=self.company, branch_specific_holidays=True)

        emp_main = self.make_employee("Main", branch=self.branch)
        emp_other = self.make_employee("Other", branch=self.other_branch)

        calendar = HolidayCalendar.objects.create(
            branch=self.branch, year=2026, name="Main Branch 2026", created_by=self.user,
        )
        regional_day = date(2026, 9, 5)
        holiday = Holiday.objects.create(
            holiday_date=regional_day, name="Regional Festival", holiday_type=self.htype,
            created_by=self.user, holiday_calendar=calendar, is_national=False,
        )

        created = holiday.backfill_attendance()

        self.assertEqual(created, 1)
        self.assertTrue(Attendance.objects.filter(employee=emp_main, date=regional_day).exists())
        self.assertFalse(Attendance.objects.filter(employee=emp_other, date=regional_day).exists())

    def test_backfill_ignores_branch_scoping_when_setting_disabled(self):
        PayrollSettings.objects.create(company=self.company, branch_specific_holidays=False)

        emp_main = self.make_employee("Main", branch=self.branch)
        emp_other = self.make_employee("Other", branch=self.other_branch)

        calendar = HolidayCalendar.objects.create(
            branch=self.branch, year=2026, name="Main Branch 2026", created_by=self.user,
        )
        regional_day = date(2026, 9, 5)
        holiday = Holiday.objects.create(
            holiday_date=regional_day, name="Regional Festival", holiday_type=self.htype,
            created_by=self.user, holiday_calendar=calendar, is_national=False,
        )

        created = holiday.backfill_attendance()

        self.assertEqual(created, 2)
        self.assertTrue(Attendance.objects.filter(employee=emp_main, date=regional_day).exists())
        self.assertTrue(Attendance.objects.filter(employee=emp_other, date=regional_day).exists())
