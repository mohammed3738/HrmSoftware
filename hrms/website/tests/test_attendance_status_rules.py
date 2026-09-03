"""
Regression tests for configurable attendance status thresholds.

The Present / Late Present / Half Day / Absent cut-offs used to be
hardcoded in Attendance.calculate_status() as a 9-hour day with 70% and 50%
multipliers. They now come from PayrollSettings so a company can change its
own policy, and the shipped defaults must reproduce the old behaviour
exactly -- otherwise every existing attendance record silently reclassifies
the next time it is recalculated.

Run with: python manage.py test website.tests.test_attendance_status_rules
"""
from datetime import date, time
from decimal import Decimal

from django.contrib.auth.models import User, Group
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.urls import reverse

from website.models import Attendance, Company, Employee, PayrollSettings

WORK_DAY = date(2026, 6, 1)  # a Monday


def make_employee(company, code="ASR001"):
    return Employee.objects.create(
        company=company, salutation="Mr", first_name="Hours", last_name="Worked",
        father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
        place_of_birth="City", personal_email=f"{code}@test.com", present_address="Addr",
        permanent_address="Addr", personal_mobile="1234567890", employee_code=code,
        designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), location="City",
        pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Hours",
        salary_account_number="1234567890", ifsc_code="TEST0001234",
        emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
        emergency_contact_mobile1="0987654321", status="Active", force_password_change=False,
    )


class AttendanceStatusRuleTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="ASR", name="Status Rules Co", phone="1", email="asr@test.com", address="Addr",
        )
        self.settings = PayrollSettings.objects.create(company=self.company)
        self.employee = make_employee(self.company)

    def status_after_working(self, hours):
        """Punch in at 09:00 and leave after `hours`, then let
        calculate_status() classify the day."""
        in_time = time(9, 0)
        minutes_from_midnight = int(round(9 * 60 + hours * 60))
        out_time = time((minutes_from_midnight // 60) % 24, minutes_from_midnight % 60)
        # Recreated rather than updated: update_or_create() saves with a
        # limited update_fields, which would drop the status/count that
        # calculate_status() recomputes.
        Attendance.objects.filter(employee=self.employee, date=WORK_DAY).delete()
        attendance = Attendance.objects.create(
            employee=self.employee, date=WORK_DAY, in_time=in_time, out_time=out_time,
        )
        attendance.refresh_from_db()
        return attendance.status, attendance.count

    # ── the defaults must not change anyone's history ─────────────────

    def test_defaults_match_the_previously_hardcoded_rules(self):
        self.assertEqual(self.settings.full_day_hours, Decimal("9.00"))
        self.assertEqual(self.settings.late_present_min_hours, Decimal("6.30"))
        self.assertEqual(self.settings.half_day_min_hours, Decimal("4.50"))
        self.assertEqual(self.settings.half_day_count, Decimal("0.50"))

    def test_default_ladder_classifies_the_same_way_it_used_to(self):
        # 9h day, 15min grace -> Present from 8.75h; Late Present from 6.3h;
        # Half Day from 4.5h; Absent below that.
        self.assertEqual(self.status_after_working(9)[0], "Present")
        self.assertEqual(self.status_after_working(8.8)[0], "Present")     # inside grace
        self.assertEqual(self.status_after_working(7)[0], "Late Present")
        self.assertEqual(self.status_after_working(6.5)[0], "Late Present")
        self.assertEqual(self.status_after_working(5)[0], "Half Day")
        self.assertEqual(self.status_after_working(4)[0], "Absent")

    def test_default_counts_are_unchanged(self):
        self.assertEqual(self.status_after_working(9)[1], Decimal("1.00"))
        self.assertEqual(self.status_after_working(7)[1], Decimal("1.00"))
        self.assertEqual(self.status_after_working(5)[1], Decimal("0.50"))
        self.assertEqual(self.status_after_working(4)[1], Decimal("0.00"))

    # ── the point of the feature: policy actually changes behaviour ────

    def test_shortening_the_working_day_makes_the_same_hours_a_full_day(self):
        # 7 hours is Late Present on a 9-hour day...
        self.assertEqual(self.status_after_working(7)[0], "Late Present")
        # ...and a full Present day once the company moves to 7 hours.
        self.settings.full_day_hours = Decimal("7.00")
        self.settings.late_present_min_hours = Decimal("5.00")
        self.settings.half_day_min_hours = Decimal("3.50")
        self.settings.save()
        self.assertEqual(self.status_after_working(7)[0], "Present")

    def test_raising_the_half_day_floor_turns_short_days_absent(self):
        self.assertEqual(self.status_after_working(5)[0], "Half Day")
        self.settings.half_day_min_hours = Decimal("6.00")
        self.settings.save()
        self.assertEqual(self.status_after_working(5)[0], "Absent")

    def test_half_day_credit_is_configurable(self):
        self.settings.half_day_count = Decimal("0.75")
        self.settings.save()
        status, count = self.status_after_working(5)
        self.assertEqual(status, "Half Day")
        self.assertEqual(count, Decimal("0.75"))

    def test_lateness_is_measured_against_the_configured_day_not_a_fixed_nine(self):
        """calculate_lateness() used to assume a 9-hour duty regardless of
        the company's actual working day."""
        self.settings.full_day_hours = Decimal("8.00")
        self.settings.late_present_min_hours = Decimal("6.00")
        self.settings.half_day_min_hours = Decimal("4.00")
        self.settings.save()

        attendance = Attendance.objects.create(
            employee=self.employee, date=WORK_DAY, in_time=time(9, 0), out_time=time(17, 0),
        )
        # Worked exactly the 8-hour day, so nothing is owed.
        self.assertEqual(attendance.late, 0)
        self.assertEqual(attendance.status, "Present")

    def test_recalculation_applies_a_new_policy_to_existing_rows(self):
        attendance = Attendance.objects.create(
            employee=self.employee, date=WORK_DAY, in_time=time(9, 0), out_time=time(16, 0),
        )
        self.assertEqual(attendance.status, "Late Present")  # 7h on a 9h day

        self.settings.full_day_hours = Decimal("7.00")
        self.settings.late_present_min_hours = Decimal("5.00")
        self.settings.half_day_min_hours = Decimal("3.50")
        self.settings.save()

        attendance.save()  # what "Recalculate Attendance" does
        attendance.refresh_from_db()
        self.assertEqual(attendance.status, "Present")

    def test_a_manual_override_still_wins_over_any_policy(self):
        attendance = Attendance.objects.create(
            employee=self.employee, date=WORK_DAY, in_time=time(9, 0), out_time=time(11, 0),
        )
        self.assertEqual(attendance.status, "Absent")

        attendance.status_overridden = True
        attendance.status = "Present"
        attendance.count = Decimal("1.00")
        attendance.save()

        self.settings.half_day_min_hours = Decimal("1.00")
        self.settings.save()
        attendance.save()
        attendance.refresh_from_db()
        self.assertEqual(attendance.status, "Present")

    # ── guards ────────────────────────────────────────────────────────

    def test_out_of_order_thresholds_are_rejected(self):
        self.settings.half_day_min_hours = Decimal("8.00")
        self.settings.late_present_min_hours = Decimal("6.30")
        with self.assertRaises(ValidationError):
            self.settings.clean()

    def test_late_present_above_a_full_day_is_rejected(self):
        self.settings.late_present_min_hours = Decimal("10.00")
        with self.assertRaises(ValidationError):
            self.settings.clean()


class SaveAttendanceRulesTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="SAR", name="Save Rules Co", phone="1", email="sar@test.com", address="Addr",
        )
        PayrollSettings.objects.create(company=self.company)
        self.admin = User.objects.create_user(username="sar_admin", password="pass12345")
        self.admin.groups.add(Group.objects.get(name="Admin"))
        self.client = Client()
        self.client.force_login(self.admin, backend="django.contrib.auth.backends.ModelBackend")

    def _post(self, **overrides):
        payload = {"company_id": self.company.id}
        payload.update(overrides)
        return self.client.post(reverse("save-payroll-settings"), payload)

    def test_saving_new_thresholds_persists_them(self):
        resp = self._post(
            full_day_hours="8", late_present_min_hours="6", half_day_min_hours="4", half_day_count="0.5",
        )
        self.assertEqual(resp.status_code, 200)
        settings = PayrollSettings.objects.get(company=self.company)
        self.assertEqual(settings.full_day_hours, Decimal("8"))
        self.assertEqual(settings.half_day_min_hours, Decimal("4"))

    def test_out_of_order_thresholds_are_refused_with_a_readable_error(self):
        resp = self._post(full_day_hours="9", late_present_min_hours="3", half_day_min_hours="7")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])

        settings = PayrollSettings.objects.get(company=self.company)
        self.assertEqual(settings.half_day_min_hours, Decimal("4.50"))  # untouched

    def test_non_numeric_input_is_refused(self):
        resp = self._post(full_day_hours="nine")
        self.assertEqual(resp.status_code, 400)

    def test_a_save_that_omits_the_rules_leaves_them_alone(self):
        """Other settings tabs post to the same endpoint; a partial save
        must not reset a company's attendance policy to the defaults."""
        settings = PayrollSettings.objects.get(company=self.company)
        settings.full_day_hours = Decimal("7.50")
        settings.late_present_min_hours = Decimal("5.00")
        settings.half_day_min_hours = Decimal("3.00")
        settings.save()

        resp = self._post(grace_period_minutes="20")
        self.assertEqual(resp.status_code, 200)

        settings.refresh_from_db()
        self.assertEqual(settings.full_day_hours, Decimal("7.50"))
        self.assertEqual(settings.grace_period_minutes, 20)
