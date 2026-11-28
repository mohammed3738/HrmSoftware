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

        def make_employee(code, week_off_days=""):
            return Employee.objects.create(
                company=self.company, week_off_days=week_off_days,
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
        self.night_employee = make_employee("EMP001", week_off_days="5")
        # Regular employee: no override, follows the company default (Sunday).
        self.day_employee = make_employee("EMP002", week_off_days="")

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


class MultipleWeekOffDaysTest(EmployeeWeekOffTest):
    """Weekly off can be more than one day: Sat + Sun, or Fri + Sat."""

    FRI, SAT, SUN, MON = date(2026, 8, 21), date(2026, 8, 22), date(2026, 8, 23), date(2026, 8, 24)

    def test_friday_and_saturday_off(self):
        emp = self.night_employee
        emp.week_off_days = "4,5"
        emp.save()
        status = {d: Attendance.objects.create(employee=emp, date=d).status
                  for d in (self.FRI, self.SAT, self.SUN, self.MON)}
        self.assertEqual(status[self.FRI], "Weekend")
        self.assertEqual(status[self.SAT], "Weekend")
        self.assertEqual(status[self.SUN], "Absent")   # a working day for them
        self.assertEqual(status[self.MON], "Absent")

    def test_payroll_counts_both_days_as_week_off(self):
        from website.models import week_off_dates_in_range
        emp = self.day_employee
        emp.week_off_days = "5,6"
        emp.save()
        off = week_off_dates_in_range(emp, self.FRI, self.MON, sunday_only=True)
        self.assertEqual(off, {self.SAT, self.SUN})

    def test_display_and_parsing(self):
        from website.models import describe_week_off_days, parse_week_off_days
        self.assertEqual(parse_week_off_days("6, 5"), frozenset({5, 6}))
        self.assertIsNone(parse_week_off_days(""))
        self.assertEqual(describe_week_off_days("5,6"), "Saturday, Sunday")
        self.night_employee.week_off_days = "4,5"
        self.assertEqual(self.night_employee.get_week_off_days_display(), "Friday, Saturday")


class WeekOffDaysFormTest(EmployeeWeekOffTest):
    def form(self, days, instance=None):
        from django.forms.models import model_to_dict
        from website.forms import EmployeeForm
        instance = instance or self.day_employee
        data = {k: v for k, v in model_to_dict(instance).items() if v is not None and k != "photo"}
        data["week_off_days"] = days
        f = EmployeeForm(data=data, instance=instance)
        f.is_valid()
        return f

    def test_ticked_days_are_stored_in_order(self):
        f = self.form(["6", "5"])
        self.assertNotIn("week_off_days", f.errors)
        self.assertEqual(f.cleaned_data["week_off_days"], "5,6")

    def test_none_ticked_means_company_default(self):
        self.assertEqual(self.form([]).cleaned_data["week_off_days"], "")
        self.assertEqual(self.form([""]).cleaned_data["week_off_days"], "")    # blank entry, not an error
        self.assertEqual(self.form("4,5").cleaned_data["week_off_days"], "4,5")  # stored text form

    def test_all_seven_is_refused(self):
        self.assertIn("week_off_days", self.form([str(d) for d in range(7)]).errors)

    def test_unchanged_days_are_not_reported_as_a_change(self):
        emp = self.night_employee
        emp.week_off_days = "5,6"
        emp.save()
        self.assertNotIn("week_off_days", self.form(["5", "6"], instance=emp).changed_data)

    def test_edit_form_shows_saved_days_ticked(self):
        from website.forms import EmployeeForm
        emp = self.night_employee
        emp.week_off_days = "4,5"
        emp.save()
        html = str(EmployeeForm(instance=emp)["week_off_days"])
        self.assertEqual(html.count("checked"), 2)
