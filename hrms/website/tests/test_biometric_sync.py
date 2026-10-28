"""Regression tests for deriving in/out times from biometric punches.

These are the rules the whole eSSL integration rests on, and they are easy
to break from a distance: a change to Attendance.save(), to the weekend
rule, or to the payroll lock can quietly stop the sync writing anything, and
nothing else in the app would notice. So every rule in
services/biometric_sync.py is pinned here, including the ones that say
"leave this day alone".

Run with:
    python manage.py test website.tests.test_biometric_sync
    pytest website/tests/test_biometric_sync.py
"""
import datetime
import os
from datetime import date, time

from django.test import Client, TestCase

from website.models import (
    Attendance,
    BiometricPunch,
    BiometricSyncRun,
    Company,
    Employee,
    PayrollRun,
    PayrollSettings,
    ShiftAssignment,
)
from website.services import biometric_sync

# All mid-week, so the weekend rule never masks what is being tested.
TUE = date(2026, 10, 20)
WED = date(2026, 10, 21)
THU = date(2026, 10, 22)


def make_employee(company, code, **extra):
    fields = dict(
        company=company, salutation="Mr", first_name="Punch", last_name="Clock",
        father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
        place_of_birth="City", personal_email=f"{code}@test.com".lower(), present_address="Addr",
        permanent_address="Addr", personal_mobile="1234567890", employee_code=code,
        designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), location="City",
        pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Punch",
        salary_account_number="1234567890", ifsc_code="TEST0001234",
        emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
        emergency_contact_mobile1="0987654321", status="Active", force_password_change=False,
    )
    fields.update(extra)
    return Employee.objects.create(**fields)


def punch(code, day, clock):
    """A punch as the Windows agent sends it."""
    return {
        "device_user_id": code,
        "employee_code": code,
        "employee_name": "Punch Clock",
        "punch_date": day.isoformat(),
        "punch_time": clock,
        "device_id": 1,
        "source_log_id": abs(hash((code, day, clock))) % 10_000_000,
    }


class BiometricSyncBaseTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="BIO", name="Biometric Co", phone="1", email="bio@test.com", address="Addr",
        )
        PayrollSettings.objects.create(company=self.company)
        self.day_employee = make_employee(self.company, "BIO001")
        self.night_employee = make_employee(self.company, "BIO002", is_night_shift=True)

    def attendance(self, employee, day):
        return Attendance.objects.filter(employee=employee, date=day).first()

    def times(self, employee, day):
        row = self.attendance(employee, day)
        return None if row is None else (row.in_time, row.out_time)


class DayShiftRuleTest(BiometricSyncBaseTest):
    def test_first_punch_is_in_time_and_last_is_out_time(self):
        biometric_sync.ingest([
            punch("BIO001", WED, "09:58:12"),
            punch("BIO001", WED, "13:30:00"),
            punch("BIO001", WED, "19:02:40"),
        ])
        self.assertEqual(self.times(self.day_employee, WED), (time(9, 58, 12), time(19, 2, 40)))
        self.assertEqual(self.attendance(self.day_employee, WED).status, "Present")

    def test_a_later_punch_moves_the_out_time_but_never_the_in_time(self):
        biometric_sync.ingest([punch("BIO001", WED, "09:58:12"), punch("BIO001", WED, "19:02:40")])
        biometric_sync.ingest([punch("BIO001", WED, "20:15:00")])
        self.assertEqual(self.times(self.day_employee, WED), (time(9, 58, 12), time(20, 15)))

    def test_an_earlier_punch_arriving_late_does_not_move_the_out_time(self):
        biometric_sync.ingest([punch("BIO001", WED, "09:00:00"), punch("BIO001", WED, "19:00:00")])
        biometric_sync.ingest([punch("BIO001", WED, "13:00:00")])  # a mid-day punch, seen late
        self.assertEqual(self.times(self.day_employee, WED), (time(9, 0), time(19, 0)))

    def test_resending_the_same_window_stores_and_changes_nothing(self):
        batch = [punch("BIO001", WED, "09:00:00"), punch("BIO001", WED, "18:30:00")]
        biometric_sync.ingest(batch)
        run = biometric_sync.ingest(batch)
        self.assertEqual(run.punches_stored, 0)
        self.assertEqual(run.attendance_updated, 0)
        self.assertEqual(self.times(self.day_employee, WED), (time(9, 0), time(18, 30)))

    def test_a_single_punch_gives_an_in_time_and_no_out_time(self):
        biometric_sync.ingest([punch("BIO001", WED, "09:12:00")])
        self.assertEqual(self.times(self.day_employee, WED), (time(9, 12), None))

    def test_a_span_over_the_cap_is_treated_as_a_missed_out_punch(self):
        # In at 09:00 and the next punch is 23 hours later: somebody forgot to
        # punch out, so the day is left without an out-time rather than
        # credited.
        biometric_sync.ingest([punch("BIO001", WED, "09:00:00"), punch("BIO001", WED, "08:00:00")])
        biometric_sync.ingest([punch("BIO001", WED, "23:59:00")])
        row = self.attendance(self.day_employee, WED)
        self.assertEqual((row.in_time, row.out_time), (time(8, 0), time(23, 59)))

    def test_no_punches_creates_no_attendance_row(self):
        biometric_sync.ingest([])
        self.assertIsNone(self.attendance(self.day_employee, WED))


class NightShiftRuleTest(BiometricSyncBaseTest):
    def test_in_time_is_the_days_last_punch_and_out_time_the_next_days_first(self):
        """The case the integration was built for: a 21 Oct night shift is
        '21 Oct's last punch -> 22 Oct's first punch', and 22 Oct then starts
        again at its own last punch."""
        biometric_sync.ingest([
            punch("BIO002", TUE, "21:50:00"),
            punch("BIO002", WED, "06:05:00"),
            punch("BIO002", WED, "21:45:00"),
            punch("BIO002", THU, "06:10:00"),
        ])
        self.assertEqual(self.times(self.night_employee, TUE), (time(21, 50), time(6, 5)))
        self.assertEqual(self.times(self.night_employee, WED), (time(21, 45), time(6, 10)))

    def test_the_overnight_span_is_credited_as_hours_worked(self):
        biometric_sync.ingest([
            punch("BIO002", TUE, "22:00:00"),
            punch("BIO002", WED, "06:30:00"),
        ])
        row = self.attendance(self.night_employee, TUE)
        self.assertEqual(row.working_hours, 8.5)

    def test_a_lone_morning_punch_is_not_an_in_time(self):
        # That punch is the PREVIOUS night's out-punch; it must not become an
        # in-time for a shift that never started.
        biometric_sync.ingest([punch("BIO002", WED, "06:02:00")])
        self.assertIsNone(self.attendance(self.night_employee, WED))

    def test_the_out_time_waits_for_the_next_days_punch(self):
        biometric_sync.ingest([punch("BIO002", TUE, "21:40:00")])
        self.assertEqual(self.times(self.night_employee, TUE), (time(21, 40), None))
        biometric_sync.ingest([punch("BIO002", WED, "06:15:00")])
        self.assertEqual(self.times(self.night_employee, TUE), (time(21, 40), time(6, 15)))

    def test_an_out_time_already_recorded_is_never_blanked(self):
        biometric_sync.ingest([
            punch("BIO002", TUE, "21:40:00"),
            punch("BIO002", WED, "06:15:00"),
        ])
        biometric_sync.resync_window(from_date=TUE, to_date=THU)
        self.assertEqual(self.times(self.night_employee, TUE), (time(21, 40), time(6, 15)))

    def test_a_roster_entry_crossing_midnight_overrides_the_day_shift_default(self):
        ShiftAssignment.objects.create(
            employee=self.day_employee, shift_name="Rotating", start_date=TUE, end_date=THU,
            shift_start_time=time(22, 0), shift_end_time=time(7, 0),
        )
        biometric_sync.ingest([
            punch("BIO001", TUE, "22:10:00"),
            punch("BIO001", WED, "06:40:00"),
        ])
        self.assertEqual(self.times(self.day_employee, TUE), (time(22, 10), time(6, 40)))

    def test_a_daytime_roster_entry_overrides_the_night_shift_flag(self):
        ShiftAssignment.objects.create(
            employee=self.night_employee, shift_name="General", start_date=TUE, end_date=THU,
            shift_start_time=time(9, 0), shift_end_time=time(18, 0),
        )
        biometric_sync.ingest([
            punch("BIO002", WED, "09:05:00"),
            punch("BIO002", WED, "18:20:00"),
        ])
        self.assertEqual(self.times(self.night_employee, WED), (time(9, 5), time(18, 20)))


class SyncLeavesDaysAloneTest(BiometricSyncBaseTest):
    def test_manual_times_are_not_overwritten(self):
        biometric_sync.ingest([punch("BIO001", WED, "09:00:00"), punch("BIO001", WED, "18:00:00")])
        row = self.attendance(self.day_employee, WED)
        row.in_time, row.out_time, row.times_locked = time(10, 0), time(19, 0), True
        row.save()

        run = biometric_sync.ingest([punch("BIO001", WED, "21:30:00")])
        self.assertEqual(self.times(self.day_employee, WED), (time(10, 0), time(19, 0)))
        self.assertGreaterEqual(run.attendance_skipped, 1)

    def test_force_rebuilds_the_day_from_the_punches_alone(self):
        """--force must actually redo the day: clearing the lock is not
        enough, because the ordinary rules would otherwise preserve the
        manual in-time and refuse to move the out-time backwards."""
        biometric_sync.ingest([punch("BIO001", WED, "09:00:00"), punch("BIO001", WED, "18:00:00")])
        row = self.attendance(self.day_employee, WED)
        row.in_time, row.out_time, row.times_locked = time(10, 0), time(19, 0), True
        row.save()

        biometric_sync.resync_window(from_date=TUE, to_date=THU, force=True)
        self.assertEqual(self.times(self.day_employee, WED), (time(9, 0), time(18, 0)))

    def test_a_finalized_payroll_period_is_never_touched_even_with_force(self):
        PayrollRun.objects.create(
            company=self.company, month=TUE.replace(day=1), start_date=TUE, end_date=THU,
            status=PayrollRun.STATUS_FINALIZED,
        )
        run = biometric_sync.ingest([punch("BIO001", WED, "09:00:00")], force=True)
        self.assertIsNone(self.attendance(self.day_employee, WED))
        self.assertGreaterEqual(run.attendance_skipped, 1)

    def test_days_before_joining_are_skipped(self):
        self.day_employee.date_of_joining = THU
        self.day_employee.save()
        run = biometric_sync.ingest([punch("BIO001", WED, "09:00:00")])
        self.assertIsNone(self.attendance(self.day_employee, WED))
        self.assertGreaterEqual(run.attendance_skipped, 1)

    def test_punches_for_a_left_employee_are_stored_but_build_nothing(self):
        self.day_employee.status = "Left"
        self.day_employee.save()
        biometric_sync.ingest([punch("BIO001", WED, "09:00:00")])
        self.assertEqual(BiometricPunch.objects.filter(device_user_id="BIO001").count(), 1)
        self.assertIsNone(self.attendance(self.day_employee, WED))


class EmployeeMatchingTest(BiometricSyncBaseTest):
    def test_an_unmatched_punch_is_kept_and_linked_once_the_employee_exists(self):
        run = biometric_sync.ingest([punch("BIO999", WED, "09:00:00")])
        self.assertEqual(run.punches_unmatched, 1)
        self.assertEqual(BiometricPunch.objects.filter(employee__isnull=True).count(), 1)

        newcomer = make_employee(self.company, "BIO999")
        run = biometric_sync.resync_window(from_date=TUE, to_date=THU)
        self.assertEqual(run.punches_unmatched, 0)
        self.assertEqual(self.times(newcomer, WED), (time(9, 0), None))

    def test_a_device_padded_numeric_id_matches_a_numeric_employee_code(self):
        numeric = make_employee(self.company, "14")
        biometric_sync.ingest([{
            "device_user_id": "0014", "employee_code": "",
            "punch_date": WED.isoformat(), "punch_time": "09:11:00",
        }])
        self.assertEqual(self.times(numeric, WED), (time(9, 11), None))

    def test_an_explicit_device_user_id_mapping_wins(self):
        mapped = make_employee(self.company, "HR-7", biometric_device_user_id="77")
        biometric_sync.ingest([{
            "device_user_id": "77", "employee_code": "",
            "punch_date": WED.isoformat(), "punch_time": "10:02:00",
        }])
        self.assertEqual(self.times(mapped, WED), (time(10, 2), None))

    def test_a_malformed_punch_is_reported_without_losing_the_batch(self):
        run = biometric_sync.ingest([
            {"device_user_id": "", "punch_date": WED.isoformat(), "punch_time": "09:00:00"},
            punch("BIO001", WED, "09:30:00"),
        ])
        self.assertEqual(run.status, BiometricSyncRun.STATUS_SUCCESS)
        self.assertEqual(self.times(self.day_employee, WED), (time(9, 30), None))


class PunchStorageTest(BiometricSyncBaseTest):
    def test_a_punch_is_stored_as_the_device_recorded_it(self):
        biometric_sync.ingest([punch("BIO001", WED, "23:50:07")])
        stored = BiometricPunch.objects.get(device_user_id="BIO001")
        # The local wall-clock values, with no timezone conversion -- a 23:50
        # punch must never drift onto the next day.
        self.assertEqual(stored.punch_date, WED)
        self.assertEqual(stored.punch_time, time(23, 50, 7))
        self.assertEqual(stored.employee, self.day_employee)

    def test_the_run_records_what_it_did(self):
        run = biometric_sync.ingest([
            punch("BIO001", WED, "09:00:00"),
            punch("BIO001", WED, "18:00:00"),
        ])
        self.assertEqual(run.status, BiometricSyncRun.STATUS_SUCCESS)
        self.assertEqual(run.source, BiometricSyncRun.SOURCE_AGENT)
        self.assertEqual(run.punches_received, 2)
        self.assertEqual(run.punches_stored, 2)
        self.assertEqual(run.attendance_created, 1)
        self.assertEqual((run.from_date, run.to_date), (WED, WED))
        self.assertIsNotNone(run.finished_at)


class PunchApiTest(BiometricSyncBaseTest):
    """The endpoint the Windows agent talks to. It carries no session and no
    CSRF token by design, so the token check is the only thing standing in
    front of 'anyone may write attendance' -- worth pinning."""

    url = "/api/biometric/punches/"
    status_url = "/api/biometric/status/"
    token = "test-sync-token"

    def body(self, punches):
        import json
        return json.dumps({"device": "test-agent", "punches": punches})

    def post(self, punches, token=None):
        headers = {} if token is None else {"x-hrms-sync-token": token}
        return self.client.post(self.url, data=self.body(punches),
                                content_type="application/json", headers=headers)

    def test_a_correct_token_is_accepted_and_builds_attendance(self):
        with self.settings(BIOMETRIC_SYNC_TOKEN=self.token):
            response = self.post([
                punch("BIO001", WED, "09:45:01"),
                punch("BIO001", WED, "18:50:00"),
            ], token=self.token)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["stored"], 2)
        self.assertEqual(payload["attendance_created"], 1)
        self.assertEqual(self.times(self.day_employee, WED), (time(9, 45, 1), time(18, 50)))

    def test_a_missing_or_wrong_token_is_refused(self):
        with self.settings(BIOMETRIC_SYNC_TOKEN=self.token):
            self.assertEqual(self.post([punch("BIO001", WED, "09:00:00")]).status_code, 401)
            self.assertEqual(
                self.post([punch("BIO001", WED, "09:00:00")], token="wrong").status_code, 401)
        self.assertFalse(BiometricPunch.objects.exists())

    def test_an_unconfigured_token_switches_the_endpoint_off(self):
        # An empty secret must fail closed, not match an empty header.
        with self.settings(BIOMETRIC_SYNC_TOKEN=""):
            self.assertEqual(self.post([punch("BIO001", WED, "09:00:00")], token="").status_code, 401)
        self.assertFalse(BiometricPunch.objects.exists())

    def test_malformed_json_is_rejected_without_a_traceback(self):
        with self.settings(BIOMETRIC_SYNC_TOKEN=self.token):
            response = self.client.post(self.url, data="{oops", content_type="application/json",
                                        headers={"x-hrms-sync-token": self.token})
        self.assertEqual(response.status_code, 400)

    def test_punches_must_be_a_list(self):
        import json
        with self.settings(BIOMETRIC_SYNC_TOKEN=self.token):
            response = self.client.post(
                self.url, data=json.dumps({"punches": "nope"}),
                content_type="application/json", headers={"x-hrms-sync-token": self.token})
        self.assertEqual(response.status_code, 400)

    def test_get_is_not_allowed(self):
        with self.settings(BIOMETRIC_SYNC_TOKEN=self.token):
            self.assertEqual(
                self.client.get(self.url, headers={"x-hrms-sync-token": self.token}).status_code, 405)

    def test_the_status_endpoint_tells_the_agent_where_to_resume(self):
        biometric_sync.ingest([punch("BIO001", WED, "09:00:00")])
        with self.settings(BIOMETRIC_SYNC_TOKEN=self.token):
            response = self.client.get(self.status_url, headers={"x-hrms-sync-token": self.token})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["latest_punch_date"], WED.isoformat())

    def test_the_status_endpoint_needs_the_token_too(self):
        with self.settings(BIOMETRIC_SYNC_TOKEN=self.token):
            self.assertEqual(self.client.get(self.status_url).status_code, 401)


class BiometricSyncPageTest(BiometricSyncBaseTest):
    def test_the_page_needs_a_login(self):
        response = Client().get("/attendance/biometric-sync/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.url)

    def test_staff_can_open_it_and_rebuild_a_range(self):
        from django.contrib.auth.models import User

        admin = User.objects.create_user("bio-admin", password="x", is_staff=True)
        client = Client()
        client.force_login(admin, backend="django.contrib.auth.backends.ModelBackend")

        biometric_sync.ingest([punch("BIO001", WED, "09:00:00"), punch("BIO001", WED, "18:30:00")])

        response = client.get("/attendance/biometric-sync/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Biometric Sync")

        response = client.post("/attendance/biometric-sync/rebuild/",
                               {"from_date": TUE.isoformat(), "to_date": THU.isoformat()})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            BiometricSyncRun.objects.filter(source=BiometricSyncRun.SOURCE_MANUAL).exists())

    def test_a_backwards_date_range_is_refused(self):
        from django.contrib.auth.models import User

        admin = User.objects.create_user("bio-admin2", password="x", is_staff=True)
        client = Client()
        client.force_login(admin, backend="django.contrib.auth.backends.ModelBackend")
        response = client.post("/attendance/biometric-sync/rebuild/",
                               {"from_date": THU.isoformat(), "to_date": TUE.isoformat()},
                               follow=True)
        self.assertContains(response, "cannot be after")


class ManualTimeLockingTest(BiometricSyncBaseTest):
    """The two paths that write punch times by hand must mark the day, or the
    next sync run quietly undoes what somebody decided."""

    def test_an_approved_correction_locks_the_day(self):
        from website.models import AttendanceCorrectionRequest
        from website.views import _approve_correction_item

        biometric_sync.ingest([punch("BIO001", WED, "09:00:00"), punch("BIO001", WED, "18:00:00")])
        row = self.attendance(self.day_employee, WED)

        request = AttendanceCorrectionRequest.objects.create(
            attendance=row, old_in_time=row.in_time, old_out_time=row.out_time,
            new_in_time=time(9, 30), new_out_time=time(19, 0), reason="Forgot to punch out",
        )
        error = _approve_correction_item(request)
        self.assertIsNone(error, error)

        row.refresh_from_db()
        self.assertTrue(row.times_locked)
        biometric_sync.ingest([punch("BIO001", WED, "21:00:00")])
        self.assertEqual(self.times(self.day_employee, WED), (time(9, 30), time(19, 0)))


class FuturePunchTest(BiometricSyncBaseTest):
    """A punch dated in the future is a device with a wrong clock, not
    attendance. This installation's real history contains one dated 31
    December, which would otherwise have become an attendance row on a day
    nobody had worked."""

    def test_a_punch_far_in_the_future_is_rejected(self):
        far = datetime.date.today() + datetime.timedelta(days=66)
        run = biometric_sync.ingest([punch("BIO001", far, "18:55:56")])
        self.assertFalse(
            BiometricPunch.objects.filter(punch_date=far).exists(),
            "a punch dated two months out should not be stored")
        self.assertIsNone(self.attendance(self.day_employee, far))
        self.assertIn("rejected", run.message)
        self.assertIn("future", run.message)

    def test_today_and_tomorrow_are_still_accepted(self):
        # A device an hour or two ahead, or a timezone edge, must not lose a
        # real punch -- the default tolerance is one day.
        today = datetime.date.today()
        tomorrow = today + datetime.timedelta(days=1)
        biometric_sync.ingest([
            punch("BIO001", today, "09:00:00"),
            punch("BIO001", tomorrow, "09:00:00"),
        ])
        self.assertEqual(
            BiometricPunch.objects.filter(punch_date__in=(today, tomorrow)).count(), 2)

    def test_the_tolerance_is_configurable(self):
        far = datetime.date.today() + datetime.timedelta(days=5)
        with self.settings(BIOMETRIC_FUTURE_PUNCH_TOLERANCE_DAYS=10):
            biometric_sync.ingest([punch("BIO001", far, "09:00:00")])
        self.assertTrue(BiometricPunch.objects.filter(punch_date=far).exists())

    def test_a_rejected_punch_does_not_stop_the_good_ones(self):
        far = datetime.date.today() + datetime.timedelta(days=66)
        run = biometric_sync.ingest([
            punch("BIO001", far, "18:55:56"),
            punch("BIO001", WED, "09:30:00"),
            punch("BIO001", WED, "18:30:00"),
        ])
        self.assertEqual(self.times(self.day_employee, WED), (time(9, 30), time(18, 30)))
        self.assertEqual(run.punches_stored, 2)


class RosterNightShiftTest(BiometricSyncBaseTest):
    """Night duty rotates, so the Shift Roster -- not the standing tick on the
    employee -- decides who is on nights for a given date. These pin the
    order the two are consulted in, and the explicit is_night_shift tick on
    the roster entry that removes the guesswork."""

    def roster(self, employee, **extra):
        fields = dict(
            employee=employee, shift_name="Rotating", start_date=TUE,
            end_date=THU, is_active=True,
        )
        fields.update(extra)
        return ShiftAssignment.objects.create(**fields)

    def night_punches(self, code):
        """A clean overnight pattern: in on WED, out on THU morning."""
        biometric_sync.ingest([
            punch(code, WED, "21:45:00"),
            punch(code, THU, "06:10:00"),
        ])

    # ── the explicit tick ────────────────────────────────────────────────
    def test_a_rostered_night_shift_is_honoured_with_no_timings_at_all(self):
        """The case the old code missed: a roster entry whose name says
        nothing and whose timings were left blank."""
        self.roster(self.day_employee, shift_name="B Shift", is_night_shift=True)
        self.night_punches("BIO001")
        self.assertEqual(self.times(self.day_employee, WED), (time(21, 45), time(6, 10)))

    def test_the_tick_wins_over_daytime_timings_on_the_same_entry(self):
        self.roster(self.day_employee, shift_name="Shift 3", is_night_shift=True,
                    shift_start_time=time(9, 0), shift_end_time=time(18, 0))
        self.night_punches("BIO001")
        self.assertEqual(self.times(self.day_employee, WED), (time(21, 45), time(6, 10)))

    # ── the roster overrides the employee's standing setting ─────────────
    def test_a_daytime_roster_entry_overrides_the_employees_night_tick(self):
        self.roster(self.night_employee, shift_name="General",
                    shift_start_time=time(9, 0), shift_end_time=time(18, 0))
        biometric_sync.ingest([
            punch("BIO002", WED, "09:05:00"),
            punch("BIO002", WED, "18:20:00"),
        ])
        self.assertEqual(self.times(self.night_employee, WED), (time(9, 5), time(18, 20)))

    def test_outside_the_rostered_dates_the_employee_setting_applies_again(self):
        # Rostered onto days for TUE..THU only; the night tick governs FRI.
        self.roster(self.night_employee, shift_name="General",
                    shift_start_time=time(9, 0), shift_end_time=time(18, 0))
        friday = datetime.date(2026, 10, 23)
        biometric_sync.ingest([
            punch("BIO002", friday, "21:50:00"),
            punch("BIO002", friday + datetime.timedelta(days=1), "06:05:00"),
        ])
        self.assertEqual(self.times(self.night_employee, friday), (time(21, 50), time(6, 5)))

    # ── an entry that says nothing must not be read as "day" ────────────
    def test_an_entry_that_says_nothing_falls_through_to_the_employee(self):
        """No tick, no timings, a neutral name -- that is not evidence of a
        day shift, so a permanently-night employee stays on nights."""
        self.roster(self.night_employee, shift_name="Shift 3")
        self.night_punches("BIO002")
        self.assertEqual(self.times(self.night_employee, WED), (time(21, 45), time(6, 10)))

    def test_an_archived_roster_entry_is_ignored(self):
        self.roster(self.night_employee, shift_name="General", is_active=False,
                    shift_start_time=time(9, 0), shift_end_time=time(18, 0))
        self.night_punches("BIO002")
        self.assertEqual(self.times(self.night_employee, WED), (time(21, 45), time(6, 10)))

    # ── the legacy inference still works ────────────────────────────────
    def test_timings_crossing_midnight_still_imply_nights(self):
        self.roster(self.day_employee, shift_name="Rotating",
                    shift_start_time=time(22, 0), shift_end_time=time(7, 0))
        self.night_punches("BIO001")
        self.assertEqual(self.times(self.day_employee, WED), (time(21, 45), time(6, 10)))

    def test_a_name_hint_still_implies_nights(self):
        for name in ("Night Shift", "OVERNIGHT", "graveyard"):
            with self.subTest(name=name):
                ShiftAssignment.objects.all().delete()
                Attendance.objects.all().delete()
                BiometricPunch.objects.all().delete()
                self.roster(self.day_employee, shift_name=name)
                self.night_punches("BIO001")
                self.assertEqual(self.times(self.day_employee, WED),
                                 (time(21, 45), time(6, 10)))

class RosterFormDefaultsToNightTest(TestCase):
    """The Shift Roster's add form starts with "Night shift" ticked, because
    the roster is used mainly for night rotations and HR should not have to
    tick it 16 times a cycle. The consequence is that a DAY rotation saved
    without unticking gets its in-time from the wrong end of the day, so the
    default and its warning are both worth pinning."""

    def template_html(self):
        from django.conf import settings as dj_settings

        for directory in dj_settings.TEMPLATES[0]["DIRS"]:
            candidate = os.path.join(str(directory), "attendance", "shift_roster.html")
            if os.path.exists(candidate):
                with open(candidate, encoding="utf-8") as handle:
                    return handle.read()
        self.fail("shift_roster.html not found in TEMPLATES DIRS")

    def test_the_add_form_checkbox_is_checked_by_default(self):
        html = self.template_html()
        self.assertIn('name="is_night_shift" id="addShiftIsNight" checked', html)

    def test_the_edit_form_checkbox_is_not_hardcoded_checked(self):
        """An existing entry must show what was saved. A `checked` attribute
        here would silently flip every day-shift entry the first time anyone
        opened it."""
        html = self.template_html()
        self.assertIn('name="is_night_shift" id="editShiftIsNight">', html)
        self.assertNotIn('id="editShiftIsNight" checked', html)

    def test_the_form_warns_that_a_day_shift_must_be_unticked(self):
        html = self.template_html()
        self.assertIn("Untick it for a day shift", html)

    def test_the_model_default_stays_false(self):
        """Only the form defaults to night. A ShiftAssignment created in code
        -- an import, a fixture, a test -- must not quietly become a night
        shift."""
        self.assertIs(ShiftAssignment._meta.get_field("is_night_shift").default, False)

class RosterAutoArchiveTest(BiometricSyncBaseTest):
    """Finished rotations leave the active roster so it stays readable, and
    that must not move a single in/out time. The sync therefore keeps
    honouring auto-archived entries for the dates they covered, while a
    MANUAL archive -- the app's soft delete -- still takes an entry out of
    its reckoning."""

    def setUp(self):
        super().setUp()
        from website.services import shift_roster_cleanup
        self.cleanup = shift_roster_cleanup

    def roster(self, employee, start, end, **extra):
        fields = dict(employee=employee, shift_name="Night Rotation",
                      start_date=start, end_date=end, is_night_shift=True,
                      is_active=True)
        fields.update(extra)
        return ShiftAssignment.objects.create(**fields)

    # ── what gets archived ──────────────────────────────────────────────
    def test_a_finished_rotation_past_the_grace_period_is_archived(self):
        old = self.roster(self.day_employee,
                          datetime.date(2026, 1, 5), datetime.date(2026, 1, 9))
        count, rows = self.cleanup.archive_past_assignments()
        self.assertEqual(count, 1)
        old.refresh_from_db()
        self.assertFalse(old.is_active)
        self.assertTrue(old.auto_archived)
        self.assertEqual(rows[0]["employee_code"], "BIO001")

    def test_a_rotation_inside_the_grace_period_is_left_alone(self):
        today = datetime.date.today()
        recent = self.roster(self.day_employee,
                             today - datetime.timedelta(days=4),
                             today - datetime.timedelta(days=2))
        count, _ = self.cleanup.archive_past_assignments()
        self.assertEqual(count, 0)
        recent.refresh_from_db()
        self.assertTrue(recent.is_active,
                        "a rotation that only just finished is still being "
                        "re-read by the sync and must stay visible")

    def test_a_current_or_future_rotation_is_left_alone(self):
        today = datetime.date.today()
        current = self.roster(self.day_employee, today, today + datetime.timedelta(days=6))
        count, _ = self.cleanup.archive_past_assignments()
        self.assertEqual(count, 0)
        current.refresh_from_db()
        self.assertTrue(current.is_active)

    def test_dry_run_reports_without_changing_anything(self):
        old = self.roster(self.day_employee,
                          datetime.date(2026, 1, 5), datetime.date(2026, 1, 9))
        count, rows = self.cleanup.archive_past_assignments(dry_run=True)
        self.assertEqual(count, 1)
        self.assertEqual(len(rows), 1)
        old.refresh_from_db()
        self.assertTrue(old.is_active)
        self.assertFalse(old.auto_archived)

    def test_an_already_archived_entry_is_not_picked_up_again(self):
        self.roster(self.day_employee, datetime.date(2026, 1, 5),
                    datetime.date(2026, 1, 9), is_active=False, auto_archived=True)
        count, _ = self.cleanup.archive_past_assignments()
        self.assertEqual(count, 0)

    def test_the_grace_period_is_configurable(self):
        today = datetime.date.today()
        self.roster(self.day_employee,
                    today - datetime.timedelta(days=4),
                    today - datetime.timedelta(days=3))
        self.assertEqual(self.cleanup.archive_past_assignments(grace=30, dry_run=True)[0], 0)
        self.assertEqual(self.cleanup.archive_past_assignments(grace=1, dry_run=True)[0], 1)

    # ── and the whole point: attendance does not move ───────────────────
    def test_archiving_does_not_change_the_attendance_it_already_built(self):
        self.roster(self.day_employee, TUE, THU)
        biometric_sync.ingest([
            punch("BIO001", WED, "21:45:00"),
            punch("BIO001", THU, "06:10:00"),
        ])
        before = self.times(self.day_employee, WED)
        self.assertEqual(before, (time(21, 45), time(6, 10)),
                         "precondition: the rostered night shift applied")

        self.cleanup.archive_past_assignments(
            today=THU + datetime.timedelta(days=30))
        self.assertFalse(ShiftAssignment.objects.get(
            employee=self.day_employee).is_active)

        self.assertEqual(self.times(self.day_employee, WED), before)

    def test_recalculating_an_archived_night_shift_still_reads_as_nights(self):
        """The real risk. Archiving tidies the roster; a later rebuild --
        the two-hourly job does this constantly -- must not quietly turn
        those nights back into day shifts."""
        self.roster(self.day_employee, TUE, THU)
        biometric_sync.ingest([
            punch("BIO001", WED, "21:45:00"),
            punch("BIO001", THU, "06:10:00"),
        ])
        self.cleanup.archive_past_assignments(
            today=THU + datetime.timedelta(days=30))

        biometric_sync.resync_window(from_date=TUE, to_date=THU, force=True)
        self.assertEqual(self.times(self.day_employee, WED), (time(21, 45), time(6, 10)))

    def test_a_manual_archive_is_still_ignored_by_the_sync(self):
        """Unchanged behaviour: a manual archive means somebody judged the
        entry wrong, so it must not keep steering attendance."""
        self.roster(self.night_employee, TUE, THU, shift_name="General",
                    is_night_shift=False, is_active=False, auto_archived=False,
                    shift_start_time=time(9, 0), shift_end_time=time(18, 0))
        biometric_sync.ingest([
            punch("BIO002", WED, "21:45:00"),
            punch("BIO002", THU, "06:10:00"),
        ])
        # The manually archived day-shift entry is ignored, so the employee's
        # own night tick governs.
        self.assertEqual(self.times(self.night_employee, WED), (time(21, 45), time(6, 10)))
