"""
Regression tests for the Shift Roster feature: HR schedules who's on which
shift (day/night/rotational) for a date range, without it affecting the
actual (flexible, check-in-time-based) attendance calculation.
Run with: python manage.py test website.tests.test_shift_roster
"""
from datetime import date, time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from website.models import Company, Employee, ShiftAssignment, PayrollSettings


class ShiftRosterTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Test Co")

        def make_employee(code, first_name):
            return Employee.objects.create(
                company=self.company,
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

        self.emp1 = make_employee("EMP001", "Alice")
        self.emp2 = make_employee("EMP002", "Bob")

        self.user = User.objects.create_superuser("admin", "admin@test.com", "pass12345")
        self.client = Client()
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def test_bulk_assign_shift_to_multiple_employees(self):
        resp = self.client.post(reverse("add_shift_assignment"), {
            "employee_ids": [self.emp1.id, self.emp2.id],
            "shift_name": "Night Shift",
            "start_date": "2026-08-24",
            "end_date": "2026-08-30",
            "shift_start_time": "22:00",
            "shift_end_time": "07:00",
            "notes": "Week 1 rotation",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"], data)
        self.assertEqual(len(data["created"]), 2)
        self.assertEqual(data["failed"], [])

        assignments = ShiftAssignment.objects.filter(shift_name="Night Shift")
        self.assertEqual(assignments.count(), 2)
        self.assertEqual(set(assignments.values_list("employee_id", flat=True)), {self.emp1.id, self.emp2.id})

    def test_overlapping_assignment_for_same_employee_is_rejected(self):
        ShiftAssignment.objects.create(
            employee=self.emp1, shift_name="Day Shift",
            start_date=date(2026, 8, 24), end_date=date(2026, 8, 30),
        )
        resp = self.client.post(reverse("add_shift_assignment"), {
            "employee_ids": [self.emp1.id],
            "shift_name": "Night Shift",
            "start_date": "2026-08-27",  # overlaps the Day Shift assignment above
            "end_date": "2026-09-02",
        })
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["created"], [])
        self.assertEqual(len(data["failed"]), 1)
        self.assertIn("overlapping", data["failed"][0]["error"])

        # Only the original assignment exists — the overlapping one was rejected.
        self.assertEqual(ShiftAssignment.objects.filter(employee=self.emp1).count(), 1)

    def test_rotation_pattern_non_overlapping_assignments_succeed(self):
        """The exact scenario described: employee does day shift one week,
        night shift the next — two back-to-back, non-overlapping entries."""
        resp1 = self.client.post(reverse("add_shift_assignment"), {
            "employee_ids": [self.emp1.id],
            "shift_name": "Day Shift", "start_date": "2026-08-24", "end_date": "2026-08-30",
        })
        resp2 = self.client.post(reverse("add_shift_assignment"), {
            "employee_ids": [self.emp1.id],
            "shift_name": "Night Shift", "start_date": "2026-08-31", "end_date": "2026-09-06",
        })
        self.assertEqual(len(resp1.json()["created"]), 1)
        self.assertEqual(len(resp2.json()["created"]), 1)
        self.assertEqual(ShiftAssignment.objects.filter(employee=self.emp1).count(), 2)

    def test_roster_list_filters_by_employee_and_shift_name(self):
        ShiftAssignment.objects.create(
            employee=self.emp1, shift_name="Night Shift",
            start_date=date(2026, 8, 24), end_date=date(2026, 8, 30),
        )
        ShiftAssignment.objects.create(
            employee=self.emp2, shift_name="Day Shift",
            start_date=date(2026, 8, 24), end_date=date(2026, 8, 30),
        )

        resp = self.client.get(reverse("shift_roster_list"), {"shift_name": "Night Shift"})
        rows = list(resp.context["assignments"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].employee_id, self.emp1.id)

        resp = self.client.get(reverse("shift_roster_list"), {"employee": "Bob"})
        rows = list(resp.context["assignments"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].employee_id, self.emp2.id)

    def test_edit_and_delete_assignment(self):
        assignment = ShiftAssignment.objects.create(
            employee=self.emp1, shift_name="Day Shift",
            start_date=date(2026, 8, 24), end_date=date(2026, 8, 30),
        )

        resp = self.client.post(reverse("edit_shift_assignment", args=[assignment.id]), {
            "shift_name": "Night Shift", "start_date": "2026-08-24", "end_date": "2026-08-30",
            "shift_start_time": "22:00", "shift_end_time": "07:00", "notes": "Changed to nights",
        })
        self.assertTrue(resp.json()["success"])
        assignment.refresh_from_db()
        self.assertEqual(assignment.shift_name, "Night Shift")
        self.assertEqual(assignment.notes, "Changed to nights")

        # "Delete" is a soft delete (archive, is_active=False) -- the row is
        # kept, not destroyed, consistent with the rest of the app's
        # archive/restore pattern.
        resp = self.client.post(reverse("delete_shift_assignment", args=[assignment.id]))
        self.assertTrue(resp.json()["success"])
        assignment.refresh_from_db()
        self.assertFalse(assignment.is_active)
        self.assertTrue(ShiftAssignment.objects.filter(id=assignment.id).exists())

    def test_api_get_shift_assignment_for_edit_prefill(self):
        assignment = ShiftAssignment.objects.create(
            employee=self.emp1, shift_name="Night Shift",
            start_date=date(2026, 8, 24), end_date=date(2026, 8, 30),
            shift_start_time=time(22, 0), shift_end_time=time(7, 0),
        )
        resp = self.client.get(reverse("api_get_shift_assignment", args=[assignment.id]))
        data = resp.json()
        self.assertEqual(data["shift_name"], "Night Shift")
        self.assertEqual(data["start_date"], "2026-08-24")
        self.assertEqual(data["shift_start_time"], "22:00")

    def test_does_not_affect_attendance_calculation(self):
        """A shift roster entry is purely informational — the attendance
        model must still compute status from actual check-in/out time
        (flexible, not tied to the assigned shift)."""
        from website.models import Attendance
        ShiftAssignment.objects.create(
            employee=self.emp1, shift_name="Night Shift",
            start_date=date(2026, 8, 24), end_date=date(2026, 8, 30),
            shift_start_time=time(22, 0), shift_end_time=time(7, 0),
        )
        # Employee actually checks in at 22:00 and out at 07:10 next day (overnight, 9h10m worked).
        att = Attendance.objects.create(
            employee=self.emp1, date=date(2026, 8, 25),
            in_time=time(22, 0), out_time=time(7, 10),
        )
        self.assertEqual(att.status, "Present")

    def test_requires_manager_group(self):
        plain_user = User.objects.create_user("plain", "plain@test.com", "pass12345")
        client = Client()
        client.force_login(plain_user, backend="django.contrib.auth.backends.ModelBackend")

        resp = client.post(reverse("add_shift_assignment"), {
            "employee_ids": [self.emp1.id], "shift_name": "Night Shift",
            "start_date": "2026-08-24", "end_date": "2026-08-30",
        })
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(ShiftAssignment.objects.count(), 0)


class ShiftRosterDateWindowTest(TestCase):
    """When a company has a payroll cycle configured, shift dates must fall
    between today and the end of the current payroll period — not in the
    past, and not beyond the period that's currently running."""

    def setUp(self):
        self.company = Company.objects.create(name="Window Co", short_name="WINCO")
        # No custom from_date/to_date -> get_payroll_period_for_date() falls
        # back to the calendar month containing today.
        PayrollSettings.objects.create(company=self.company)

        self.employee = Employee.objects.create(
            company=self.company,
            salutation="Mr", first_name="Carl", last_name="Doe",
            father_name="Robert Doe", gender="Male", blood_group="O+",
            date_of_birth=date(1990, 1, 1), place_of_birth="Test City",
            personal_email="carl@test.com", present_address="123 Test St",
            permanent_address="123 Test St", personal_mobile="1234567890",
            employee_code="EMP003", designation="Developer", department="IT",
            date_of_joining=date(2020, 1, 1), location="Test Location",
            pan_no="ABCDE1234F", aadhar_no="123456789012",
            name_as_per_bank="Carl", salary_account_number="1234567890",
            ifsc_code="TEST0001234", emergency_contact_name1="Jane Doe",
            emergency_contact_relation1="Spouse", emergency_contact_mobile1="0987654321",
            status="Active",
        )

        self.user = User.objects.create_superuser("windowadmin", "wa@test.com", "pass12345")
        self.client = Client()
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def test_start_date_before_today_is_rejected(self):
        yesterday = date.today() - timedelta(days=1)
        resp = self.client.post(reverse("add_shift_assignment"), {
            "employee_ids": [self.employee.id], "shift_name": "Night Shift",
            "start_date": yesterday.isoformat(),
            "end_date": (date.today() + timedelta(days=1)).isoformat(),
        })
        data = resp.json()
        self.assertEqual(data["created"], [])
        self.assertEqual(len(data["failed"]), 1)
        self.assertIn("before today", data["failed"][0]["error"])
        self.assertEqual(ShiftAssignment.objects.count(), 0)

    def test_end_date_beyond_current_period_is_rejected(self):
        far_future = date.today() + timedelta(days=90)  # guaranteed outside the current calendar month
        resp = self.client.post(reverse("add_shift_assignment"), {
            "employee_ids": [self.employee.id], "shift_name": "Night Shift",
            "start_date": date.today().isoformat(),
            "end_date": far_future.isoformat(),
        })
        data = resp.json()
        self.assertEqual(data["created"], [])
        self.assertEqual(len(data["failed"]), 1)
        self.assertIn("current payroll period", data["failed"][0]["error"])
        self.assertEqual(ShiftAssignment.objects.count(), 0)

    def test_dates_within_current_period_succeed(self):
        resp = self.client.post(reverse("add_shift_assignment"), {
            "employee_ids": [self.employee.id], "shift_name": "Night Shift",
            "start_date": date.today().isoformat(),
            "end_date": date.today().isoformat(),
        })
        data = resp.json()
        self.assertEqual(len(data["created"]), 1)
        self.assertEqual(data["failed"], [])

    def test_edit_also_enforces_the_window(self):
        assignment = ShiftAssignment.objects.create(
            employee=self.employee, shift_name="Day Shift",
            start_date=date.today(), end_date=date.today(),
        )
        far_future = date.today() + timedelta(days=90)
        resp = self.client.post(reverse("edit_shift_assignment", args=[assignment.id]), {
            "shift_name": "Day Shift",
            "start_date": date.today().isoformat(),
            "end_date": far_future.isoformat(),
        })
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])
        assignment.refresh_from_db()
        self.assertEqual(assignment.end_date, date.today())  # unchanged

    def test_no_payroll_settings_does_not_block(self):
        """A company with no PayrollSettings row at all -> no window
        constraint, matching the original ShiftRosterTest suite's behavior."""
        no_settings_company = Company.objects.create(name="No Settings Co", short_name="NOSET")
        employee = Employee.objects.create(
            company=no_settings_company,
            salutation="Mr", first_name="Dana", last_name="Doe",
            father_name="Robert Doe", gender="Male", blood_group="O+",
            date_of_birth=date(1990, 1, 1), place_of_birth="Test City",
            personal_email="dana@test.com", present_address="123 Test St",
            permanent_address="123 Test St", personal_mobile="1234567890",
            employee_code="EMP004", designation="Developer", department="IT",
            date_of_joining=date(2020, 1, 1), location="Test Location",
            pan_no="ABCDE1234F", aadhar_no="123456789012",
            name_as_per_bank="Dana", salary_account_number="1234567890",
            ifsc_code="TEST0001234", emergency_contact_name1="Jane Doe",
            emergency_contact_relation1="Spouse", emergency_contact_mobile1="0987654321",
            status="Active",
        )
        resp = self.client.post(reverse("add_shift_assignment"), {
            "employee_ids": [employee.id], "shift_name": "Night Shift",
            "start_date": "2020-01-01", "end_date": "2020-01-07",  # far in the past, no constraint applies
        })
        data = resp.json()
        self.assertEqual(len(data["created"]), 1)
