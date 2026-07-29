"""
Regression tests for the "Late Attendance Review" page: listing Late Present
days and manually converting them (Full Day / Half Day / Holiday) for
payroll forgiveness, with the override surviving future recalculation.
Run with: python manage.py test website.tests.test_late_attendance_review
"""
from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from website.models import Company, Employee, Attendance, PayrollSettings, PayrollRun


class LateAttendanceReviewTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Test Co")
        PayrollSettings.objects.create(company=self.company, grace_period_minutes=0)
        self.employee = Employee.objects.create(
            company=self.company,
            salutation="Mr", first_name="John", last_name="Doe",
            father_name="Robert Doe", gender="Male", blood_group="O+",
            date_of_birth=date(1990, 1, 1), place_of_birth="Test City",
            personal_email="john@test.com", present_address="123 Test St",
            permanent_address="123 Test St", personal_mobile="1234567890",
            employee_code="EMP001", designation="Developer", department="IT",
            date_of_joining=date(2020, 1, 1), location="Test Location",
            pan_no="ABCDE1234F", aadhar_no="123456789012",
            name_as_per_bank="John Doe", salary_account_number="1234567890",
            ifsc_code="TEST0001234", emergency_contact_name1="Jane Doe",
            emergency_contact_relation1="Spouse", emergency_contact_mobile1="0987654321",
            status="Active",
        )
        # Mon-Wed, Aug 2026 — 8h50m worked (10 min short of 9h), grace=0 => Late Present
        self.late_rows = [
            Attendance.objects.create(
                employee=self.employee, date=date(2026, 8, 3).replace(day=d),
                in_time=time(9, 0), out_time=time(17, 50),
            )
            for d in (3, 4, 5)
        ]
        for r in self.late_rows:
            r.refresh_from_db()
            self.assertEqual(r.status, "Late Present")

        self.user = User.objects.create_superuser("admin", "admin@test.com", "pass12345")
        self.client = Client()
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def test_page_lists_late_records_for_current_and_selected_month(self):
        resp = self.client.get(reverse("late_attendance_review"), {"year": "2026", "month": "8"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["records"]), 3)
        self.assertEqual(resp.context["late_counts"][self.employee.id], 3)

    def test_first_load_with_no_filters_shows_all_late_records(self):
        """Regression test: the page must not silently default to filtering
        by the current calendar month — that previously hid all data
        whenever "today" fell in a different month than the late records
        (e.g. test data in August while the server's current month is July),
        while the dropdown still rendered as if 'All Months' was selected."""
        resp = self.client.get(reverse("late_attendance_review"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["records"]), 3)

    def test_converting_to_full_day_persists_and_survives_recalculation(self):
        target = self.late_rows[0]
        resp = self.client.post(reverse("override_attendance_status"), {
            "attendance_id": target.id, "new_status": "Present",
        })
        data = resp.json()
        self.assertTrue(data["success"], data)
        self.assertEqual(data["status"], "Present")

        target.refresh_from_db()
        self.assertEqual(target.status, "Present")
        self.assertEqual(target.count, 1)
        self.assertTrue(target.status_overridden)

        # It should no longer show up in the late-review list
        resp = self.client.get(reverse("late_attendance_review"), {"year": "2026", "month": "8"})
        self.assertEqual(len(resp.context["records"]), 2)

        # Recalculating attendance must NOT undo the manual override
        resp = self.client.post(reverse("recalculate_attendance_init"), {
            "date_from": "2026-08-01", "date_to": "2026-08-31",
        })
        total = resp.json()["total"]
        offset = 0
        while True:
            resp = self.client.post(reverse("recalculate_attendance_chunk"), {
                "offset": offset, "date_from": "2026-08-01", "date_to": "2026-08-31",
            })
            n = resp.json()["processed_in_chunk"]
            if n == 0:
                break
            offset += n

        target.refresh_from_db()
        self.assertEqual(target.status, "Present")  # still forgiven, not reverted to Late Present

    def test_converting_to_half_day_and_holiday(self):
        half_day_target, holiday_target = self.late_rows[1], self.late_rows[2]

        resp = self.client.post(reverse("override_attendance_status"), {
            "attendance_id": half_day_target.id, "new_status": "Half Day",
        })
        self.assertEqual(resp.json()["status"], "Half Day")
        half_day_target.refresh_from_db()
        self.assertEqual(str(half_day_target.count), "0.50")
        self.assertTrue(half_day_target.is_half_day)

        resp = self.client.post(reverse("override_attendance_status"), {
            "attendance_id": holiday_target.id, "new_status": "Holiday",
        })
        self.assertEqual(resp.json()["status"], "Holiday")
        holiday_target.refresh_from_db()
        self.assertTrue(holiday_target.is_holiday)

    def test_revert_to_late_present_clears_override(self):
        target = self.late_rows[0]
        self.client.post(reverse("override_attendance_status"), {
            "attendance_id": target.id, "new_status": "Present",
        })
        target.refresh_from_db()
        self.assertTrue(target.status_overridden)

        self.client.post(reverse("override_attendance_status"), {
            "attendance_id": target.id, "new_status": "Late Present",
        })
        target.refresh_from_db()
        self.assertFalse(target.status_overridden)
        self.assertEqual(target.status, "Late Present")

    def test_override_blocked_when_payroll_finalized(self):
        PayrollRun.objects.create(
            company=self.company, month=date(2026, 8, 1),
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 31),
            status=PayrollRun.STATUS_FINALIZED,
        )
        target = self.late_rows[0]
        resp = self.client.post(reverse("override_attendance_status"), {
            "attendance_id": target.id, "new_status": "Present",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])
        target.refresh_from_db()
        self.assertEqual(target.status, "Late Present")
        self.assertFalse(target.status_overridden)

    def test_employee_search_matches_full_name(self):
        """Regression test: searching 'John Doe' (first + last name combined,
        as the autocomplete fills in, or as a manager might just type) must
        match — previously only a substring of first_name OR last_name
        individually could match, so a full-name search returned nothing."""
        resp = self.client.get(reverse("late_attendance_review"), {"employee": "John Doe"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["records"]), 3)

        resp = self.client.get(reverse("late_attendance_review"), {"employee": "John"})
        self.assertEqual(len(resp.context["records"]), 3)

        resp = self.client.get(reverse("late_attendance_review"), {"employee": "EMP001"})
        self.assertEqual(len(resp.context["records"]), 3)

        resp = self.client.get(reverse("late_attendance_review"), {"employee": "Nobody"})
        self.assertEqual(len(resp.context["records"]), 0)

    def test_requires_login(self):
        anon_client = Client()
        resp = anon_client.get(reverse("late_attendance_review"))
        self.assertNotEqual(resp.status_code, 200)
