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
