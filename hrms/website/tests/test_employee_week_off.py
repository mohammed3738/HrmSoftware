"""
Regression tests for per-employee weekly-off day override — e.g. night-shift
employees whose off day is Saturday instead of the company's usual Sunday.
Run with: python manage.py test website.tests.test_employee_week_off
"""
from datetime import date, time

from django.test import TestCase

from website.models import Company, Employee, Attendance, PayrollSettings


class EmployeeWeekOffTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Test Co")
        PayrollSettings.objects.create(company=self.company, weekend_days="sun")

        def make_employee(code, week_off_day=None):
            return Employee.objects.create(
                company=self.company, week_off_day=week_off_day,
                salutation="Mr", first_name=code, last_name="Doe",
                father_name="Robert Doe", gender="Male", blood_group="O+",
                date_of_birth=date(1990, 1, 1), place_of_birth="Test City",
                personal_email=f"{code}@test.com", present_address="123 Test St",
                permanent_address="123 Test St", personal_mobile="1234567890",
                employee_code=code, designation="Developer", department="IT",
                date_of_joining=date(2020, 1, 1), location="Test Location",
                pan_no="ABCDE1234F", aadhar_no="123456789012",
                name_as_per_bank=code, salary_account_number="1234567890",
                ifsc_code="TEST0001234", emergency_contact_name1="Jane Doe",
                emergency_contact_relation1="Spouse", emergency_contact_mobile1="0987654321",
                status="Active",
            )

        # Night-shift employee: Saturday off instead of Sunday.
        self.night_employee = make_employee("EMP001", week_off_day=5)
        # Regular employee: no override, follows the company default (Sunday).
        self.day_employee = make_employee("EMP002", week_off_day=None)

    def test_employee_with_override_gets_saturday_as_weekend(self):
        saturday = date(2026, 8, 22)  # confirmed Saturday
        att = Attendance.objects.create(employee=self.night_employee, date=saturday)
        self.assertEqual(att.status, "Weekend")

    def test_employee_with_override_is_not_off_on_sunday(self):
        sunday = date(2026, 8, 23)
        # No punch on a working Sunday -> Absent, not Weekend, since this
        # employee's off day is Saturday, not Sunday.
        att = Attendance.objects.create(employee=self.night_employee, date=sunday)
        self.assertEqual(att.status, "Absent")

        # And if they actually worked that Sunday, it's a normal Present day.
        att.in_time = time(22, 0)
        att.out_time = time(7, 10)
        att.save()
        self.assertEqual(att.status, "Present")

    def test_employee_without_override_still_uses_company_default_sunday(self):
        sunday = date(2026, 8, 23)
        saturday = date(2026, 8, 22)

        att_sunday = Attendance.objects.create(employee=self.day_employee, date=sunday)
        self.assertEqual(att_sunday.status, "Weekend")

        att_saturday = Attendance.objects.create(employee=self.day_employee, date=saturday)
        self.assertNotEqual(att_saturday.status, "Weekend")  # Saturday is a normal working day for them
