"""
The weekly off can now be set on a shift roster entry, and it is the
roster's answer that counts for those dates.

Why it belongs on the roster: a rotating crew's off day moves with the
shift. Employee.week_off_day is a standing tick -- one day, for ever --
which cannot say "Wednesday while you are on nights this fortnight, Sunday
when you rotate back". The shift roster already wins over the employee for
night duty (NightShiftResolver), and weekly off now follows the same rule:

    1. the roster entry covering the date
    2. the employee's own Weekly Off Day
    3. the company's weekend setting

The part that matters most is that all three readers agree. A weekly off is
a credited free day, so if the attendance register treats Wednesday as an
off day while payroll still counts it as a working day the employee was not
present for, the same Wednesday is credited on one screen and docked as
leave on the payslip. models.week_off_weekday() /
week_off_dates_in_range() are the single resolver all of them use, and the
tests below check the register, the payroll day-count and the leave count
on the same roster.

Run with:
    python manage.py test website.tests.test_roster_week_off
"""
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils.timezone import now

from website.models import (
    Attendance,
    Company,
    Employee,
    PayrollSettings,
    ShiftAssignment,
    attendance_rule_cache,
    week_off_weekday,
)
from website.services import get_attendance_summary

# A full Mon-Sun week well clear of today, inside one calendar month.
WEEK_MON = date(2026, 6, 1)
WEEK_WED = date(2026, 6, 3)
WEEK_SUN = date(2026, 6, 7)


def make_employee(company, code, first_name, **extra):
    fields = dict(
        company=company, salutation="Mr", first_name=first_name, last_name="Doe",
        father_name="Father", gender="Male", blood_group="O+",
        date_of_birth=date(1990, 1, 1), place_of_birth="City",
        personal_email=f"{code}@test.com".lower(), present_address="Addr",
        permanent_address="Addr", personal_mobile="1234567890", employee_code=code,
        designation="Dev", department="IT", date_of_joining=date(2020, 1, 1),
        location="City", pan_no="ABCDE1234F", aadhar_no="123456789012",
        name_as_per_bank=first_name, salary_account_number="1234567890",
        ifsc_code="TEST0001234", emergency_contact_name1="Jane",
        emergency_contact_relation1="Spouse", emergency_contact_mobile1="0987654321",
        status="Active", force_password_change=False,
    )
    fields.update(extra)
    return Employee.objects.create(**fields)


class RosterWeekOffResolutionTest(TestCase):
    """Which day wins, and when."""

    def setUp(self):
        self.company = Company.objects.create(
            short_name="RWO", name="Roster Week Off Co", phone="1",
            email="rwo@test.com", address="Addr",
        )
        PayrollSettings.objects.create(company=self.company, weekend_days="sun")
        self.employee = make_employee(self.company, "RWO001", "Rotating")

    def _roster(self, off_day, start=WEEK_MON, end=WEEK_SUN, **extra):
        return ShiftAssignment.objects.create(
            employee=self.employee, shift_name="Night", start_date=start,
            end_date=end, week_off_day=off_day, **extra,
        )

    def test_the_roster_decides_for_the_dates_it_covers(self):
        self._roster(off_day=2)  # Wednesday
        with attendance_rule_cache():
            self.assertEqual(week_off_weekday(self.employee, WEEK_WED), 2)

    def test_the_roster_beats_the_employees_own_day(self):
        self.employee.week_off_day = 6  # Sunday, standing
        self.employee.save(update_fields=["week_off_day"])
        self._roster(off_day=2)
        with attendance_rule_cache():
            self.assertEqual(week_off_weekday(self.employee, WEEK_WED), 2)

    def test_outside_the_roster_the_employees_own_day_applies_again(self):
        self.employee.week_off_day = 6
        self.employee.save(update_fields=["week_off_day"])
        self._roster(off_day=2)
        after = WEEK_SUN + timedelta(days=3)
        with attendance_rule_cache():
            self.assertEqual(week_off_weekday(self.employee, after), 6)

    def test_a_roster_entry_with_no_weekly_off_set_does_not_override(self):
        self.employee.week_off_day = 6
        self.employee.save(update_fields=["week_off_day"])
        self._roster(off_day=None)
        with attendance_rule_cache():
            self.assertEqual(week_off_weekday(self.employee, WEEK_WED), 6)

    def test_with_nothing_set_the_company_rule_is_left_to_decide(self):
        with attendance_rule_cache():
            self.assertIsNone(week_off_weekday(self.employee, WEEK_WED))

    def test_a_manually_archived_entry_is_ignored(self):
        """is_active=False is this app's soft delete -- somebody decided the
        entry was wrong, so it must stop counting."""
        self._roster(off_day=2, is_active=False)
        with attendance_rule_cache():
            self.assertIsNone(week_off_weekday(self.employee, WEEK_WED))

    def test_an_auto_archived_entry_still_counts(self):
        """The nightly tidy-up archives entries whose dates have gone by.
        That is not a decision about correctness, and recalculating those
        dates later has to reach the same answer -- the same rule the
        night-shift resolver follows."""
        self._roster(off_day=2, is_active=False, auto_archived=True)
        with attendance_rule_cache():
            self.assertEqual(week_off_weekday(self.employee, WEEK_WED), 2)


class RosterWeekOffAttendanceTest(TestCase):
    """What the register shows."""

    def setUp(self):
        self.company = Company.objects.create(
            short_name="RW2", name="Roster Week Off Co 2", phone="1",
            email="rw2@test.com", address="Addr",
        )
        PayrollSettings.objects.create(company=self.company, weekend_days="sun")
        self.employee = make_employee(self.company, "RW2001", "Rotating")
        ShiftAssignment.objects.create(
            employee=self.employee, shift_name="Night", start_date=WEEK_MON,
            end_date=WEEK_SUN, week_off_day=2,  # Wednesday
        )

    def _attendance(self, day, worked=False):
        with attendance_rule_cache():
            return Attendance.objects.create(
                employee=self.employee, date=day,
                in_time=time(9, 0) if worked else None,
                out_time=time(18, 0) if worked else None,
            )

    def test_the_rostered_off_day_is_a_weekly_off_not_an_absence(self):
        row = self._attendance(WEEK_WED)
        self.assertEqual(row.status, "Weekend")
        self.assertEqual(row.count, Decimal("0.00"))

    def test_the_company_weekend_is_an_ordinary_working_day_while_rostered(self):
        """The roster names ONE day. Sunday is no longer the off day for
        these dates, so an unworked Sunday is an absence."""
        row = self._attendance(WEEK_SUN)
        self.assertEqual(row.status, "Absent")

    def test_working_the_rostered_off_day_still_reads_as_the_off_day(self):
        """Unworked or worked, the day is the weekly off until somebody
        overrides it -- the same as any other weekend."""
        row = self._attendance(WEEK_WED, worked=True)
        self.assertEqual(row.status, "Weekend")

    def test_an_ordinary_day_is_unaffected(self):
        row = self._attendance(WEEK_MON, worked=True)
        self.assertEqual(row.status, "Present")
        self.assertEqual(row.count, Decimal("1.00"))


class RosterWeekOffPayrollTest(TestCase):
    """What payroll counts -- the half that makes it a pay question."""

    def setUp(self):
        self.company = Company.objects.create(
            short_name="RW3", name="Roster Week Off Co 3", phone="1",
            email="rw3@test.com", address="Addr",
        )
        self.settings = PayrollSettings.objects.create(
            company=self.company, weekend_days="sun")
        self.employee = make_employee(self.company, "RW3001", "Rotating")

    def _work_the_week(self, skip=()):
        """Punch every day of the week except `skip`."""
        with attendance_rule_cache():
            day = WEEK_MON
            while day <= WEEK_SUN:
                if day not in skip:
                    Attendance.objects.create(
                        employee=self.employee, date=day,
                        in_time=time(9, 0), out_time=time(18, 30))
                day += timedelta(days=1)

    def test_a_rostered_off_day_is_credited_not_docked(self):
        ShiftAssignment.objects.create(
            employee=self.employee, shift_name="Night", start_date=WEEK_MON,
            end_date=WEEK_SUN, week_off_day=2,  # Wednesday
        )
        # Works Mon, Tue, Thu, Fri, Sat; off on Wednesday; Sunday is now an
        # ordinary working day under this roster, and is worked too.
        self._work_the_week(skip=(WEEK_WED,))

        summary = get_attendance_summary(self.employee, WEEK_MON, WEEK_SUN, self.settings)
        self.assertEqual(summary["total_days"], 7)
        # 6 worked days + the credited Wednesday = 7.
        self.assertEqual(summary["present_days"], Decimal("7.00"))
        self.assertEqual(
            summary["leave_taken"], Decimal("0.00"),
            "the rostered weekly off was docked as leave",
        )

    def test_without_a_roster_the_company_weekend_still_applies(self):
        self._work_the_week(skip=(WEEK_SUN,))
        summary = get_attendance_summary(self.employee, WEEK_MON, WEEK_SUN, self.settings)
        self.assertEqual(summary["present_days"], Decimal("7.00"))
        self.assertEqual(summary["leave_taken"], Decimal("0.00"))

    def test_a_genuine_absence_is_still_counted(self):
        ShiftAssignment.objects.create(
            employee=self.employee, shift_name="Night", start_date=WEEK_MON,
            end_date=WEEK_SUN, week_off_day=2,
        )
        # Off on Wednesday as rostered, but also absent on Thursday.
        thursday = WEEK_MON + timedelta(days=3)
        self._work_the_week(skip=(WEEK_WED,))
        Attendance.objects.filter(employee=self.employee, date=thursday).delete()
        with attendance_rule_cache():
            Attendance.objects.create(employee=self.employee, date=thursday)

        summary = get_attendance_summary(self.employee, WEEK_MON, WEEK_SUN, self.settings)
        self.assertEqual(summary["leave_taken"], Decimal("1.00"))


class RosterWeekOffFormTest(TestCase):
    """The field reaches the roster through the page HR actually uses."""

    def setUp(self):
        self.company = Company.objects.create(
            short_name="RW4", name="Roster Week Off Co 4", phone="1",
            email="rw4@test.com", address="Addr",
        )
        PayrollSettings.objects.create(company=self.company)
        self.employee = make_employee(self.company, "RW4001", "Rotating")
        self.admin = User.objects.create_superuser(
            "rw4_admin", "rw4@test.com", "pass12345")
        self.client_admin = Client()
        self.client_admin.force_login(
            self.admin, backend="django.contrib.auth.backends.ModelBackend")
        # add_shift_assignment refuses a range that leaves the current
        # payroll period, and the period ends at the month end here. A
        # single-day assignment is always inside it, whatever day the suite
        # happens to run on.
        self.start = now().date()
        self.end = self.start

    def _assign(self, **extra):
        # add_shift_assignment refuses dates outside today..end of the
        # current payroll period, so these are relative to today rather
        # than the fixed week the calculation tests use.
        payload = {
            "employee_ids": [self.employee.id], "shift_name": "Night Shift",
            "start_date": self.start.isoformat(), "end_date": self.end.isoformat(),
        }
        payload.update(extra)
        return self.client_admin.post(reverse("add_shift_assignment"), payload)

    def test_the_weekly_off_is_saved_with_the_assignment(self):
        resp = self._assign(week_off_day="2")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["failed"], [], "the assignment was rejected")
        assignment = ShiftAssignment.objects.get(employee=self.employee)
        self.assertEqual(assignment.week_off_day, 2)

    def test_leaving_it_blank_stores_nothing(self):
        self._assign(week_off_day="")
        self.assertIsNone(ShiftAssignment.objects.get(employee=self.employee).week_off_day)

    def test_omitting_it_entirely_stores_nothing(self):
        self._assign()
        self.assertIsNone(ShiftAssignment.objects.get(employee=self.employee).week_off_day)

    def test_a_nonsense_value_is_rejected_with_a_message(self):
        resp = self._assign(week_off_day="Funday")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("day of the week", resp.json()["error"])
        self.assertFalse(ShiftAssignment.objects.exists())

    def test_an_out_of_range_day_is_rejected(self):
        resp = self._assign(week_off_day="9")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(ShiftAssignment.objects.exists())

    def test_the_api_reports_it_so_the_edit_modal_can_prefill(self):
        self._assign(week_off_day="5")
        assignment = ShiftAssignment.objects.get(employee=self.employee)
        payload = self.client_admin.get(
            reverse("api_get_shift_assignment", args=[assignment.pk])).json()
        self.assertEqual(payload["week_off_day"], 5)
        self.assertEqual(payload["week_off_display"], "Saturday")

    def test_editing_can_clear_the_weekly_off_again(self):
        self._assign(week_off_day="5")
        assignment = ShiftAssignment.objects.get(employee=self.employee)
        resp = self.client_admin.post(
            reverse("edit_shift_assignment", args=[assignment.pk]), {
                "shift_name": "Night Shift",
                "start_date": self.start.isoformat(),
                "end_date": self.end.isoformat(),
                "week_off_day": "",
            })
        self.assertEqual(resp.status_code, 200)
        assignment.refresh_from_db()
        self.assertIsNone(assignment.week_off_day)
