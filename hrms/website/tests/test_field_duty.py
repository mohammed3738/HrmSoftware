"""Field Duty: the punch, the report that closes it, and the attendance it
stands in for.

What is worth pinning here is not that a record can be saved -- Django does
that -- but the four promises the feature makes, each of which is a way the
code could quietly be wrong:

* a punch with no selfie or no location is refused. The record exists to be
  evidence; a half-blind one is worse than none, because it looks like
  proof.
* the timestamps are the server's. A browser can post any `started_at` it
  likes, and if that were believed the whole record would be worthless.
* the attendance fill only ever *fills*. "If there is no in punch" and "the
  end time if latest" are the requirement, and the failure mode is
  overwriting a real punch with a self-reported one -- which would change
  somebody's pay.
* a selfie and a location are an employee's face and whereabouts, and are
  readable only by that employee and by whoever holds field_duty:view.

Run with: python manage.py test website.tests.test_field_duty
"""
import datetime
import io
import shutil
import tempfile
from datetime import date, timedelta

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from website.models import Attendance, Company, Employee, FieldDuty, PayrollRun
from website.services import field_duty as field_duty_service

MEDIA = tempfile.mkdtemp(prefix="hrms_test_field_duty_")

# Somewhere in Pune, to about a metre. Any fixed point does; what the tests
# care about is that it survives the round trip unmangled.
LAT, LON = "18.520430", "73.856744"


def selfie(name="selfie.jpg"):
    buf = io.BytesIO()
    Image.new("RGB", (60, 80), "blue").save(buf, format="JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


def punch_payload(**overrides):
    payload = {"latitude": LAT, "longitude": LON, "accuracy": "12", "selfie": selfie()}
    payload.update(overrides)
    return payload


@override_settings(MEDIA_ROOT=MEDIA)
class FieldDutyTestBase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.company = Company.objects.create(
            short_name="FDY", name="Field Duty Co", phone="1",
            email="fdy@test.com", address="Addr",
        )
        self.employee = self.make_employee("FDY001")
        self.client = Client()
        self.sign_in(self.employee)

    def make_employee(self, code, first_name="Nikhil"):
        employee = Employee.objects.create(
            company=self.company, salutation="Mr", first_name=first_name,
            last_name="Patil", father_name="Father", gender="Male",
            blood_group="O+", date_of_birth=date(1990, 1, 1), place_of_birth="Pune",
            personal_email=f"{code.lower()}@example.test", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890",
            employee_code=code, designation="Sales Executive", department="Sales",
            date_of_joining=date(2020, 1, 1), location="Pune",
            pan_no="ABCDE1234F", aadhar_no="123456789012",
            name_as_per_bank=f"{first_name} Patil", salary_account_number="1234567890",
            ifsc_code="TEST0001234", emergency_contact_name1="Spouse",
            emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
        )
        # Auto-provisioned logins start with force_password_change set,
        # which ForcePasswordChangeMiddleware would redirect every request to.
        employee.force_password_change = False
        employee.save(update_fields=["force_password_change"])
        return employee

    def sign_in(self, employee, password="FieldDuty@123"):
        employee.user.set_password(password)
        employee.user.save()
        self.assertTrue(
            self.client.login(username=employee.employee_code, password=password),
            f"could not sign in as {employee.employee_code}",
        )

    def start(self, **overrides):
        overrides.setdefault("activity", FieldDuty.Activity.SITE_VISIT)
        return self.client.post(reverse("field-duty-start"), punch_payload(**overrides))

    def end(self, **overrides):
        return self.client.post(reverse("field-duty-end"), punch_payload(**overrides))


class WhatIsRefusedTest(FieldDutyTestBase):
    """A punch with missing evidence must not be stored at all."""

    def test_a_punch_with_no_selfie_is_refused(self):
        response = self.client.post(reverse("field-duty-start"), {
            "activity": FieldDuty.Activity.DELIVERY,
            "latitude": LAT, "longitude": LON,
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("selfie", response.json()["error"].lower())
        self.assertEqual(FieldDuty.objects.count(), 0)

    def test_a_punch_with_no_location_is_refused(self):
        response = self.client.post(reverse("field-duty-start"), {
            "activity": FieldDuty.Activity.DELIVERY, "selfie": selfie(),
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("location", response.json()["error"].lower())
        self.assertEqual(FieldDuty.objects.count(), 0)

    def test_a_file_that_is_not_an_image_is_refused(self):
        """The content type is caller-supplied text; the bytes are not."""
        fake = SimpleUploadedFile("selfie.jpg", b"not a jpeg at all", content_type="image/jpeg")
        response = self.start(selfie=fake)
        self.assertEqual(response.status_code, 400)
        self.assertIn("not an image", response.json()["error"].lower())
        self.assertEqual(FieldDuty.objects.count(), 0)

    def test_an_out_of_range_coordinate_is_refused(self):
        response = self.start(latitude="91.5")
        self.assertEqual(response.status_code, 400)
        self.assertIn("range", response.json()["error"].lower())

    def test_an_unknown_activity_is_refused(self):
        response = self.start(activity="Holiday In Goa")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(FieldDuty.objects.count(), 0)

    def test_a_second_start_while_one_is_open_is_refused(self):
        self.assertEqual(self.start().status_code, 200)
        response = self.start()
        self.assertEqual(response.status_code, 409)
        self.assertIn("already have a field duty", response.json()["error"])
        self.assertEqual(FieldDuty.objects.count(), 1)

    def test_ending_with_nothing_open_is_refused(self):
        response = self.end()
        self.assertEqual(response.status_code, 404)
        self.assertIn("no field duty running", response.json()["error"])


class TimestampsComeFromTheServerTest(FieldDutyTestBase):
    def test_a_posted_start_time_is_ignored(self):
        """Believing this would make the record evidence of nothing."""
        before = timezone.now()
        response = self.start(started_at="2020-01-01T03:00:00Z", duty_date="2020-01-01")
        self.assertEqual(response.status_code, 200)

        duty = FieldDuty.objects.get()
        self.assertGreaterEqual(duty.started_at, before)
        self.assertEqual(duty.duty_date, timezone.localdate())

    def test_a_posted_end_time_is_ignored(self):
        self.start()
        before = timezone.now()
        self.end(ended_at="2020-01-01T23:00:00Z")

        duty = FieldDuty.objects.get()
        self.assertGreaterEqual(duty.ended_at, before)

    def test_the_duty_date_follows_the_start_time(self):
        self.start()
        duty = FieldDuty.objects.get()
        self.assertEqual(duty.duty_date, timezone.localtime(duty.started_at).date())


class StatusLifecycleTest(FieldDutyTestBase):
    """In Progress -> Pending Report (meetings only) -> Completed."""

    def test_a_delivery_completes_when_it_ends(self):
        self.client.post(reverse("field-duty-start"),
                         punch_payload(activity=FieldDuty.Activity.DELIVERY))
        self.assertEqual(FieldDuty.objects.get().status, FieldDuty.Status.IN_PROGRESS)

        response = self.end()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["pending_report"])
        self.assertEqual(FieldDuty.objects.get().status, FieldDuty.Status.COMPLETED)

    def test_a_meeting_stays_pending_until_the_minutes_are_uploaded(self):
        self.client.post(reverse("field-duty-start"),
                         punch_payload(activity=FieldDuty.Activity.MEETING,
                                       purpose="Zaco Infotech"))
        response = self.end()
        self.assertTrue(response.json()["pending_report"])
        self.assertEqual(response.json()["report_label"], "Minutes of Meeting")

        duty = FieldDuty.objects.get()
        self.assertEqual(duty.status, FieldDuty.Status.PENDING_REPORT)

        response = self.client.post(
            reverse("field-duty-upload-report", args=[duty.id]),
            {"report": SimpleUploadedFile("mom.pdf", b"%PDF-1.4 minutes", content_type="application/pdf"),
             "report_notes": "Agreed on a pilot."},
        )
        self.assertEqual(response.status_code, 200)

        duty.refresh_from_db()
        self.assertEqual(duty.status, FieldDuty.Status.COMPLETED)
        self.assertTrue(duty.report)
        self.assertIsNotNone(duty.report_uploaded_at)

    def test_the_status_is_derived_rather_than_stored_by_the_caller(self):
        """A status set by hand is overwritten on save, so `status` can never
        disagree with the row it sits on."""
        duty = FieldDuty.objects.create(
            employee=self.employee, activity=FieldDuty.Activity.MEETING,
            started_at=timezone.now(), start_selfie=selfie(),
            ended_at=timezone.now(), status=FieldDuty.Status.COMPLETED,
        )
        self.assertEqual(duty.status, FieldDuty.Status.PENDING_REPORT)

    def test_a_report_cannot_be_uploaded_while_the_duty_is_open(self):
        self.client.post(reverse("field-duty-start"),
                         punch_payload(activity=FieldDuty.Activity.MEETING))
        duty = FieldDuty.objects.get()
        response = self.client.post(
            reverse("field-duty-upload-report", args=[duty.id]),
            {"report": SimpleUploadedFile("mom.pdf", b"%PDF", content_type="application/pdf")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("End the field duty", response.json()["error"])

    def test_an_executable_file_type_is_not_accepted_as_a_report(self):
        """Nothing validates the content of an upload, so anything that could
        run in this origin stays out."""
        self.client.post(reverse("field-duty-start"),
                         punch_payload(activity=FieldDuty.Activity.MEETING))
        self.end()
        duty = FieldDuty.objects.get()
        response = self.client.post(
            reverse("field-duty-upload-report", args=[duty.id]),
            {"report": SimpleUploadedFile("mom.html", b"<script>alert(1)</script>",
                                          content_type="text/html")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("file type", response.json()["error"])
        duty.refresh_from_db()
        self.assertFalse(duty.report)


class AttendanceFillTest(FieldDutyTestBase):
    """"If there is no in punch then the starting time would become the punch
    in time, and the end time if latest would become the punch out time."

    Every test here is about the words *no* and *latest*: this fills gaps and
    extends the day, and never overwrites.
    """

    def today_attendance(self):
        return Attendance.objects.get(employee=self.employee, date=timezone.localdate())

    def test_starting_a_duty_fills_an_empty_in_time(self):
        response = self.start()
        self.assertEqual(response.status_code, 200)

        duty = FieldDuty.objects.get()
        attendance = self.today_attendance()
        self.assertEqual(attendance.in_time, timezone.localtime(duty.started_at).time().replace(microsecond=0))
        self.assertTrue(duty.filled_attendance_in)
        self.assertIn("in-time", response.json()["attendance_note"])

    def test_ending_a_duty_sets_the_out_time(self):
        self.start()
        self.end()

        duty = FieldDuty.objects.get()
        attendance = self.today_attendance()
        self.assertEqual(attendance.out_time, timezone.localtime(duty.ended_at).time().replace(microsecond=0))
        self.assertTrue(duty.filled_attendance_out)

    def test_an_in_time_that_already_exists_is_never_overwritten(self):
        """Somebody who punched in at the office at 09:30 and left for a site
        at 11:00 worked from 09:30."""
        Attendance.objects.create(
            employee=self.employee, date=timezone.localdate(),
            in_time=datetime.time(9, 30),
        )
        self.start()

        attendance = self.today_attendance()
        self.assertEqual(attendance.in_time, datetime.time(9, 30))
        self.assertFalse(FieldDuty.objects.get().filled_attendance_in)

    def test_a_later_out_time_is_not_shortened(self):
        """A duty that ended at lunchtime must not cut a day that ran to 18:40."""
        Attendance.objects.create(
            employee=self.employee, date=timezone.localdate(),
            in_time=datetime.time(9, 30), out_time=datetime.time(23, 59),
        )
        self.start()
        self.end()

        attendance = self.today_attendance()
        self.assertEqual(attendance.out_time, datetime.time(23, 59))
        self.assertFalse(FieldDuty.objects.get().filled_attendance_out)

    def test_a_day_whose_times_were_set_by_hand_is_left_alone(self):
        """times_locked means an approved correction or an Excel upload -- a
        decision somebody made deliberately."""
        Attendance.objects.create(
            employee=self.employee, date=timezone.localdate(),
            in_time=datetime.time(10, 0), out_time=datetime.time(19, 0),
            times_locked=True,
        )
        response = self.start()
        self.assertEqual(response.status_code, 200, "the punch itself must still be recorded")

        attendance = self.today_attendance()
        self.assertEqual(attendance.in_time, datetime.time(10, 0))
        self.assertIn("set by hand", response.json()["attendance_note"])

    def test_the_00_00_absent_marker_counts_as_no_punch(self):
        """This app's uploads write 00:00/00:00 to mean absent, and
        calculate_status() already reads that pair as no punch at all."""
        Attendance.objects.create(
            employee=self.employee, date=timezone.localdate(),
            in_time=datetime.time(0, 0), out_time=datetime.time(0, 0),
        )
        self.start()

        duty = FieldDuty.objects.get()
        self.assertEqual(self.today_attendance().in_time,
                         timezone.localtime(duty.started_at).time().replace(microsecond=0))

    def test_the_punch_time_is_whole_seconds(self):
        """Every other source of a punch time here is whole seconds, so a
        10:09:43.078158 in-time among them reads as a glitch rather than as
        a more precise measurement."""
        self.start()
        self.end()
        attendance = self.today_attendance()
        self.assertEqual(attendance.in_time.microsecond, 0)
        self.assertEqual(attendance.out_time.microsecond, 0)

    def test_a_finalized_payroll_period_is_not_touched(self):
        today = timezone.localdate()
        PayrollRun.objects.create(
            company=self.company, month=today.replace(day=1),
            start_date=today - timedelta(days=5), end_date=today + timedelta(days=5),
            status=PayrollRun.STATUS_FINALIZED,
        )
        response = self.start()
        self.assertEqual(response.status_code, 200, "the punch itself must still be recorded")
        self.assertIn("locked", response.json()["attendance_note"])
        self.assertFalse(
            Attendance.objects.filter(employee=self.employee, date=today).exists(),
            "a locked period must not even gain an attendance row",
        )

    def test_applying_the_same_duty_twice_changes_nothing_the_second_time(self):
        self.start()
        self.end()
        attendance_before = self.today_attendance()
        duty = FieldDuty.objects.get()

        outcome = field_duty_service.apply_to_attendance(duty)

        self.assertFalse(outcome["applied"])
        attendance_after = self.today_attendance()
        self.assertEqual(
            (attendance_before.in_time, attendance_before.out_time),
            (attendance_after.in_time, attendance_after.out_time),
        )

    def test_a_duty_that_ran_past_midnight_leaves_the_out_time_alone(self):
        """Writing the next day's clock time onto the start date would read as
        an out-time before the in-time. Overnight shifts are the roster's."""
        started = timezone.now() - timedelta(hours=30)
        duty = FieldDuty.objects.create(
            employee=self.employee, activity=FieldDuty.Activity.DELIVERY,
            started_at=started, start_selfie=selfie(),
        )
        field_duty_service.apply_to_attendance(duty)

        duty.ended_at = started + timedelta(hours=20)  # the next calendar day
        duty.save()
        outcome = field_duty_service.apply_to_attendance(duty)

        self.assertFalse(outcome["applied"])
        self.assertIn("next day", outcome["skipped"])
        attendance = Attendance.objects.get(
            employee=self.employee, date=timezone.localtime(started).date(),
        )
        self.assertIsNone(attendance.out_time)


class AccessControlTest(FieldDutyTestBase):
    """A selfie is somebody's face and the coordinates are their movements."""

    def setUp(self):
        super().setUp()
        self.colleague = self.make_employee("FDY002", first_name="Sneha")
        self.start()
        self.duty = FieldDuty.objects.get()

    def test_an_employee_can_open_their_own_selfie(self):
        response = self.client.get(
            reverse("field-duty-selfie", args=[self.duty.id, "start"]),
        )
        self.assertEqual(response.status_code, 200)

    def test_an_employee_cannot_open_a_colleagues_selfie(self):
        self.sign_in(self.colleague)
        response = self.client.get(
            reverse("field-duty-selfie", args=[self.duty.id, "start"]),
        )
        self.assertEqual(response.status_code, 403)

    def test_an_employee_cannot_open_a_colleagues_detail(self):
        self.sign_in(self.colleague)
        response = self.client.get(reverse("field-duty-detail", args=[self.duty.id]))
        self.assertEqual(response.status_code, 403)

    def test_an_employee_cannot_open_the_whole_companys_log(self):
        response = self.client.get(reverse("field-duty-log"))
        self.assertEqual(response.status_code, 403)

    def test_hr_can_open_the_log_and_sees_the_duty(self):
        hr = User.objects.create_user(username="fdy_hr", password="pass12345")
        hr.groups.add(Group.objects.get(name="HR"))
        self.client.force_login(hr, backend="django.contrib.auth.backends.ModelBackend")

        response = self.client.get(reverse("field-duty-log"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "FDY001")

    def test_an_unknown_selfie_side_is_a_404_not_a_guess(self):
        response = self.client.get(
            reverse("field-duty-selfie", args=[self.duty.id, "middle"]),
        )
        self.assertEqual(response.status_code, 404)

    def test_an_employee_cannot_upload_a_report_onto_a_colleagues_duty(self):
        self.end()
        self.sign_in(self.colleague)
        response = self.client.post(
            reverse("field-duty-upload-report", args=[self.duty.id]),
            {"report": SimpleUploadedFile("mom.pdf", b"%PDF", content_type="application/pdf")},
        )
        self.assertEqual(response.status_code, 403)


class PageRenderTest(FieldDutyTestBase):
    def test_the_page_offers_the_start_button_and_the_capture_modal(self):
        response = self.client.get(reverse("field-duty"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-field-duty-action="start"')
        self.assertContains(response, "fieldDutyCaptureModal")
        self.assertContains(response, "field-duty.js")

    def test_the_page_offers_the_end_button_once_a_duty_is_open(self):
        self.start()
        response = self.client.get(reverse("field-duty"))
        self.assertContains(response, 'data-field-duty-action="end"')
        self.assertNotContains(response, 'data-field-duty-action="start"')

    def test_there_is_no_file_input_for_the_selfie(self):
        """Live capture only, by choice: a file picker would let an old photo
        stand in for a selfie, which is the one thing this record rules out."""
        response = self.client.get(reverse("field-duty"))
        self.assertNotContains(response, 'name="selfie"')

    def test_each_permission_row_has_its_own_way_to_ask_again(self):
        """A refused or dismissed permission must not be a dead end: the
        page has to be able to ask the browser again without being
        reopened, and the camera and the location fail independently."""
        response = self.client.get(reverse("field-duty"))
        body = response.content.decode()
        for step in ("camera", "location"):
            self.assertIn(f'data-step="{step}"', body, f"no {step} row")
        self.assertEqual(body.count("data-step-retry"), 2,
                         "each row needs its own ask-again button")
        self.assertEqual(body.count("data-step-help"), 2,
                         "each row needs somewhere to say where the switch is")

    def test_a_pending_meeting_offers_its_upload_form(self):
        self.client.post(reverse("field-duty-start"),
                         punch_payload(activity=FieldDuty.Activity.MEETING))
        self.end()

        response = self.client.get(reverse("field-duty"))
        self.assertContains(response, "Minutes of Meeting")
        self.assertContains(response, "Waiting for your report")

    def test_a_user_with_no_employee_profile_is_sent_away_rather_than_crashing(self):
        orphan = User.objects.create_user(username="fdy_orphan", password="pass12345")
        self.client.force_login(orphan, backend="django.contrib.auth.backends.ModelBackend")
        response = self.client.get(reverse("field-duty"))
        self.assertEqual(response.status_code, 302)


class TeamScopeTest(FieldDutyTestBase):
    """A team leader sees their own people, and only their own people.

    The authority here is the reporting line, not a role: a team leader or
    manager is whoever a department or an employee record points at, so it
    cannot be granted from the Roles & Permissions matrix. Giving the role
    the company-wide right instead would show one team's leader every other
    team as well, which is the failure these tests exist to catch.
    """

    def setUp(self):
        super().setUp()
        self.leader = self.make_employee("FDYTL1", first_name="Priya")
        self.reportee = self.make_employee("FDYTL2", first_name="Rohan")
        self.reportee.reporting_person = self.leader
        self.reportee.save(update_fields=["reporting_person"])
        self.outsider = self.make_employee("FDYOUT", first_name="Kabir")

        self.reportee_duty = self.duty_for(self.reportee, "Client site A")
        self.outsider_duty = self.duty_for(self.outsider, "Client site B")

    def duty_for(self, employee, purpose):
        return FieldDuty.objects.create(
            employee=employee, activity=FieldDuty.Activity.MEETING, purpose=purpose,
            started_at=timezone.now() - timedelta(hours=2), start_selfie=selfie(),
            start_latitude=LAT, start_longitude=LON, start_accuracy_m=10,
        )

    def test_a_team_leader_can_open_the_log(self):
        self.sign_in(self.leader)
        response = self.client.get(reverse("field-duty-log"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_team_scope"])

    def test_a_team_leader_sees_their_reportee(self):
        self.sign_in(self.leader)
        response = self.client.get(reverse("field-duty-log"))
        self.assertContains(response, "Client site A")

    def test_a_team_leader_does_not_see_another_team(self):
        self.sign_in(self.leader)
        response = self.client.get(reverse("field-duty-log"))
        self.assertNotContains(response, "Client site B")

    def test_a_manager_counts_as_well_as_a_reporting_person(self):
        """Two separate fields route approvals today; both have to mean the
        same thing here, or a manager sees an empty page."""
        self.outsider.manager = self.leader
        self.outsider.save(update_fields=["manager"])

        self.sign_in(self.leader)
        response = self.client.get(reverse("field-duty-log"))
        self.assertContains(response, "Client site B")

    def test_a_team_leaders_own_duties_are_on_their_team_list(self):
        own = self.duty_for(self.leader, "My own meeting")
        self.sign_in(self.leader)
        response = self.client.get(reverse("field-duty-log"))
        self.assertContains(response, "My own meeting")
        self.assertEqual(own.employee, self.leader)

    def test_the_employee_filter_offers_only_this_leaders_team(self):
        """Otherwise the dropdown itself would name people outside the
        leader's scope."""
        self.sign_in(self.leader)
        response = self.client.get(reverse("field-duty-log"))
        codes = {person.employee_code for person in response.context["people"]}
        self.assertIn("FDYTL2", codes)
        self.assertNotIn("FDYOUT", codes)

    def test_a_team_leader_can_open_a_reportees_selfie_but_not_an_outsiders(self):
        self.sign_in(self.leader)
        allowed = self.client.get(
            reverse("field-duty-selfie", args=[self.reportee_duty.id, "start"]))
        refused = self.client.get(
            reverse("field-duty-selfie", args=[self.outsider_duty.id, "start"]))
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(refused.status_code, 403)

    def test_a_team_leader_can_open_a_reportees_detail_but_not_an_outsiders(self):
        self.sign_in(self.leader)
        allowed = self.client.get(reverse("field-duty-detail", args=[self.reportee_duty.id]))
        refused = self.client.get(reverse("field-duty-detail", args=[self.outsider_duty.id]))
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(refused.status_code, 403)

    def test_an_employee_with_nobody_reporting_to_them_still_cannot_open_the_log(self):
        self.sign_in(self.outsider)
        self.assertEqual(self.client.get(reverse("field-duty-log")).status_code, 403)

    def test_hr_sees_every_team(self):
        hr = User.objects.create_user(username="fdy_hr_scope", password="pass12345")
        hr.groups.add(Group.objects.get(name="HR"))
        self.client.force_login(hr, backend="django.contrib.auth.backends.ModelBackend")

        response = self.client.get(reverse("field-duty-log"))
        self.assertFalse(response.context["is_team_scope"])
        self.assertContains(response, "Client site A")
        self.assertContains(response, "Client site B")


class MonthFilterTest(FieldDutyTestBase):
    """The lists are browsed a month at a time, on both pages."""

    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        self.this_month = self.duty_on(timezone.now(), "Thismonth Client")
        # Safely inside the previous month whatever today's date is.
        previous = timezone.now() - timedelta(days=today.day + 5)
        self.last_month = self.duty_on(previous, "Lastmonth Client")

    def duty_on(self, moment, purpose):
        return FieldDuty.objects.create(
            employee=self.employee, activity=FieldDuty.Activity.MEETING,
            purpose=purpose, started_at=moment, ended_at=moment + timedelta(hours=1),
            start_selfie=selfie(), report=SimpleUploadedFile(
                "mom.pdf", b"%PDF", content_type="application/pdf"),
            start_latitude=LAT, start_longitude=LON,
        )

    def month_of(self, duty):
        return f"{duty.duty_date:%Y-%m}"

    def test_the_own_page_defaults_to_this_month(self):
        response = self.client.get(reverse("field-duty"))
        self.assertContains(response, "Thismonth Client")
        self.assertNotContains(response, "Lastmonth Client")

    def test_the_own_page_can_be_asked_for_last_month(self):
        response = self.client.get(
            reverse("field-duty"), {"month": self.month_of(self.last_month)})
        self.assertContains(response, "Lastmonth Client")
        self.assertNotContains(response, "Thismonth Client")

    def test_a_junk_month_falls_back_to_this_month_rather_than_erroring(self):
        """This is a filter in a URL, not a submitted form; a 500 here would
        be triggered by a mistyped link."""
        response = self.client.get(reverse("field-duty"), {"month": "not-a-month"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["month_value"],
                         f"{timezone.localdate():%Y-%m}")

    def test_the_own_page_links_the_location_and_the_photo(self):
        response = self.client.get(reverse("field-duty"))
        self.assertContains(response, "https://www.google.com/maps?q=")
        self.assertContains(
            response, reverse("field-duty-selfie", args=[self.this_month.id, "start"]))

    def test_the_log_filters_by_month_too(self):
        hr = User.objects.create_user(username="fdy_hr_month", password="pass12345")
        hr.groups.add(Group.objects.get(name="HR"))
        self.client.force_login(hr, backend="django.contrib.auth.backends.ModelBackend")

        current = self.client.get(reverse("field-duty-log"))
        self.assertContains(current, "Thismonth Client")
        self.assertNotContains(current, "Lastmonth Client")

        previous = self.client.get(
            reverse("field-duty-log"), {"month": self.month_of(self.last_month)})
        self.assertContains(previous, "Lastmonth Client")
        self.assertNotContains(previous, "Thismonth Client")

    def test_the_log_can_be_narrowed_to_one_employee(self):
        colleague = self.make_employee("FDYMON2", first_name="Isha")
        FieldDuty.objects.create(
            employee=colleague, activity=FieldDuty.Activity.DELIVERY,
            purpose="Colleague Client", started_at=timezone.now(),
            start_selfie=selfie(), start_latitude=LAT, start_longitude=LON,
        )
        hr = User.objects.create_user(username="fdy_hr_emp", password="pass12345")
        hr.groups.add(Group.objects.get(name="HR"))
        self.client.force_login(hr, backend="django.contrib.auth.backends.ModelBackend")

        response = self.client.get(
            reverse("field-duty-log"), {"employee": self.employee.id})
        self.assertContains(response, "Thismonth Client")
        self.assertNotContains(response, "Colleague Client")


class MapLinkTest(FieldDutyTestBase):
    """The coordinates have to be openable, which is the whole reason for
    storing them rather than a place name."""

    def test_the_map_url_carries_the_stored_coordinates(self):
        self.start()
        duty = FieldDuty.objects.get()
        self.assertEqual(
            duty.start_map_url,
            f"https://www.google.com/maps?q={duty.start_latitude},{duty.start_longitude}",
        )

    def test_the_coordinates_survive_the_round_trip_unmangled(self):
        self.start()
        duty = FieldDuty.objects.get()
        self.assertEqual(str(duty.start_latitude), LAT)
        self.assertEqual(str(duty.start_longitude), LON)

    def test_a_duty_with_no_end_yet_has_no_end_map_link(self):
        self.start()
        self.assertEqual(FieldDuty.objects.get().end_map_url, "")

    def test_both_ends_are_linked_once_the_duty_is_closed(self):
        self.start()
        self.end()
        duty = FieldDuty.objects.get()
        self.assertTrue(duty.start_map_url)
        self.assertTrue(duty.end_map_url)


class DashboardButtonTest(FieldDutyTestBase):
    """Field Duty is reachable from the dashboard, which is where somebody
    standing outside a client's office actually lands.

    The button is state-aware for a reason: showing "Start Field Duty" to
    somebody who is already out is the wrong button, and the one they need
    is the other one.
    """

    def test_the_employee_dashboard_offers_start_when_nothing_is_running(self):
        response = self.client.get(reverse("employee-dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Start Field Duty")
        self.assertNotContains(response, "End Field Duty")
        self.assertContains(response, reverse("field-duty"))

    def test_the_employee_dashboard_offers_end_once_a_duty_is_running(self):
        self.client.post(reverse("field-duty-start"),
                         punch_payload(activity=FieldDuty.Activity.MEETING))
        response = self.client.get(reverse("employee-dashboard"))
        self.assertContains(response, "End Field Duty")
        self.assertNotContains(response, "Start Field Duty")
        # And it names what is running, so the button is unambiguous.
        self.assertContains(response, "Client Meeting")

    def test_the_dashboard_button_follows_the_open_duty_not_the_newest_one(self):
        """A finished duty must not leave the dashboard asking to end it."""
        self.start()
        self.end()
        response = self.client.get(reverse("employee-dashboard"))
        self.assertContains(response, "Start Field Duty")
        self.assertNotContains(response, "End Field Duty")

    def test_the_admin_dashboard_offers_the_log_to_hr(self):
        hr = User.objects.create_user(username="fdy_hr_dash", password="pass12345")
        hr.groups.add(Group.objects.get(name="HR"))
        self.client.force_login(hr, backend="django.contrib.auth.backends.ModelBackend")

        response = self.client.get(reverse("admin-dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("field-duty-log"))
        self.assertContains(response, "Field Duty Log")

    def test_a_team_leaders_own_dashboard_links_their_team(self):
        """A team leader lands on the employee dashboard, not the admin one,
        so without this the only way in is the Attendance menu."""
        leader = self.make_employee("FDYDSH1", first_name="Meera")
        reportee = self.make_employee("FDYDSH2", first_name="Arjun")
        reportee.reporting_person = leader
        reportee.save(update_fields=["reporting_person"])

        self.sign_in(leader)
        response = self.client.get(reverse("employee-dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("field-duty-log"))
        self.assertContains(response, "My Team's Field Duty")

    def test_the_admin_dashboard_does_not_offer_the_log_to_an_outsider(self):
        """Somebody with neither the grant nor a reportee would get a 403
        from the link, so it must not be drawn."""
        colleague = self.make_employee("FDYDSH3", first_name="Dev")
        self.sign_in(colleague)
        response = self.client.get(reverse("employee-dashboard"))
        self.assertNotContains(response, reverse("field-duty-log"))
