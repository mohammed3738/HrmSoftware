"""
Regression tests for religious/optional holidays scoped to a manually
selected set of employees (e.g. Eid for Muslim employees, Ganesh Chaturthi
for Hindu employees) instead of applying to everyone.
Run with: python manage.py test website.tests.test_holiday_employee_scoping
"""
from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from website.models import (
    Company, Employee, Attendance, Holiday, HolidayType, Branch,
)


class HolidayEmployeeScopingTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Test Co")
        # Holiday matching only runs for employees with a branch assigned
        # (Attendance.calculate_status() guards STEP 1/2 with `if branch:`).
        self.branch = Branch.objects.create(branch_name="Main Branch")

        def make_employee(code, first_name):
            return Employee.objects.create(
                company=self.company, branch=self.branch,
                salutation="Mr", first_name=first_name, last_name="Doe",
                father_name="Robert Doe", gender="Male", blood_group="O+",
                date_of_birth=date(1990, 1, 1), place_of_birth="Test City",
                personal_email=f"{code}@test.com", present_address="123 Test St",
                permanent_address="123 Test St", personal_mobile="1234567890",
                employee_code=code, designation="Developer", department="IT",
                date_of_joining=date(2020, 1, 1), location="Test Location",
                pan_no="ABCDE1234F", aadhar_no="123456789012",
                name_as_per_bank=first_name, salary_account_number="1234567890",
                ifsc_code="TEST0001234", emergency_contact_name1="Jane Doe",
                emergency_contact_relation1="Spouse", emergency_contact_mobile1="0987654321",
                status="Active",
            )

        self.selected_employee = make_employee("EMP001", "Selected")
        self.other_employee = make_employee("EMP002", "Other")

        self.user = User.objects.create_superuser("admin", "admin@test.com", "pass12345")
        self.htype = HolidayType.objects.create(name="Religious", type_category="other")

        self.client = Client()
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def test_holiday_scoped_to_specific_employees_only_applies_to_them(self):
        eid = date(2026, 8, 20)  # a Thursday, not a weekend, so status would otherwise be Absent/Present
        holiday = Holiday.objects.create(
            holiday_date=eid, name="Eid", holiday_type=self.htype,
            created_by=self.user, applies_to_all_employees=False,
        )
        holiday.specific_employees.add(self.selected_employee)

        # Selected employee didn't come in (observing the holiday) -> should
        # be marked "Holiday", not "Absent".
        att_selected = Attendance.objects.create(employee=self.selected_employee, date=eid)
        self.assertEqual(att_selected.status, "Holiday")
        self.assertTrue(att_selected.is_holiday)
        self.assertEqual(att_selected.holiday_id, holiday.id)

        # Other employee is NOT in the specific list -> it's a normal working
        # day for them; no in/out time means Absent, not Holiday.
        att_other = Attendance.objects.create(employee=self.other_employee, date=eid)
        self.assertEqual(att_other.status, "Absent")
        self.assertFalse(att_other.is_holiday)

        # And if the other employee actually worked that day, it should
        # compute as a normal Present day (they're not on this holiday).
        att_other.in_time = time(9, 0)
        att_other.out_time = time(18, 0)
        att_other.save()
        self.assertEqual(att_other.status, "Present")

    def test_holiday_applies_to_all_employees_by_default(self):
        diwali = date(2026, 8, 21)
        Holiday.objects.create(
            holiday_date=diwali, name="Diwali", holiday_type=self.htype, created_by=self.user,
        )  # applies_to_all_employees defaults to True

        att1 = Attendance.objects.create(employee=self.selected_employee, date=diwali)
        att2 = Attendance.objects.create(employee=self.other_employee, date=diwali)
        self.assertEqual(att1.status, "Holiday")
        self.assertEqual(att2.status, "Holiday")

    def test_add_holiday_view_persists_specific_employees(self):
        resp = self.client.post(reverse("add-holiday"), {
            "holiday_date": "2026-09-15",
            "name": "Ganesh Chaturthi",
            "holiday_type": self.htype.id,
            "status": "declared",
            "description": "",
            "applies_to_all_employees": "",  # unchecked -> not sent by a real browser
            "specific_employees": [self.selected_employee.id],
        })
        self.assertEqual(resp.status_code, 302)

        holiday = Holiday.objects.get(name="Ganesh Chaturthi")
        self.assertFalse(holiday.applies_to_all_employees)
        self.assertEqual(list(holiday.specific_employees.values_list("id", flat=True)), [self.selected_employee.id])

    def test_api_get_holiday_reports_specific_employees(self):
        holiday = Holiday.objects.create(
            holiday_date=date(2026, 9, 20), name="Eid al-Adha", holiday_type=self.htype,
            created_by=self.user, applies_to_all_employees=False,
        )
        holiday.specific_employees.add(self.selected_employee)

        resp = self.client.get(reverse("api-holiday", args=[holiday.id]))
        data = resp.json()
        self.assertFalse(data["applies_to_all_employees"])
        self.assertEqual(len(data["specific_employees"]), 1)
        self.assertEqual(data["specific_employees"][0]["id"], self.selected_employee.id)
