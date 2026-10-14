"""
The four rights added to Roles & Permissions are real: ticking one for HR
grants exactly that ability, and HR without it is refused.

  Leave Management -> Create        apply leave for someone else
  Attendance Corrections -> Create  raise a correction for someone else
  Comp-Off -> Edit                  raise a comp-off for someone else
  Attendance Register -> Edit       change a day's status in the register

Run with: python manage.py test website.tests.test_tickable_rights
"""
from datetime import date, time, timedelta

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import (
    Attendance, AttendanceCorrectionRequest, Company, CompOffRequest, Employee, Feature, LeaveApplication,
    RoleFeaturePermission,
)

DAY = date.today() - timedelta(days=5)
FUTURE = date.today() + timedelta(days=20)


class TickableRightsTest(TestCase):
    def setUp(self):
        company = Company.objects.create(name="Tick Co", short_name="TCK", address="A")
        self.hr_user = User.objects.create_user(username="tick_hr", password="pass12345")
        self.hr_group = Group.objects.get(name="HR")
        self.hr_user.groups.add(self.hr_group)
        Employee.objects.create(company=company, user=self.hr_user, first_name="Hr", last_name="T",
                                employee_code="TK-HR", status="Active", force_password_change=False,
                                date_of_joining=date(2020, 1, 1))
        self.colleague = Employee.objects.create(company=company, first_name="Col", last_name="T",
                                                 employee_code="TK-CO", status="Active", date_of_joining=date(2020, 1, 1))
        self.att = Attendance.objects.create(employee=self.colleague, date=DAY, in_time=time(9), out_time=time(18))
        self.client = Client()
        self.client.force_login(self.hr_user, backend="django.contrib.auth.backends.ModelBackend")

    def _tick(self, feature, action):
        rfp, _ = RoleFeaturePermission.objects.get_or_create(role=self.hr_group, feature=Feature.objects.get(key=feature))
        setattr(rfp, f"can_{action}", True)
        rfp.save()
        self.hr_user = User.objects.get(pk=self.hr_user.pk)  # drop the per-user permission cache
        self.client.force_login(self.hr_user, backend="django.contrib.auth.backends.ModelBackend")

    def test_new_boxes_appear_in_the_matrix(self):
        flags = {f.key: f for f in Feature.objects.filter(
            key__in=["leave_management", "attendance_corrections", "comp_off", "attendance_register"])}
        self.assertTrue(flags["leave_management"].has_create)
        self.assertTrue(flags["attendance_corrections"].has_create)
        self.assertTrue(flags["comp_off"].has_edit)
        self.assertTrue(flags["attendance_register"].has_edit)

    def test_leave_for_others(self):
        post = {"employee": self.colleague.pk, "start_date": FUTURE.isoformat(), "end_date": FUTURE.isoformat(), "reason": "x"}
        self.client.post(reverse("leave_apply"), post)
        self.assertNotEqual(LeaveApplication.objects.get().employee, self.colleague)  # applied for self instead
        LeaveApplication.objects.all().delete()
        self._tick("leave_management", "create")
        self.assertContains(self.client.get(reverse("leave_apply")), 'name="employee"')
        self.client.post(reverse("leave_apply"), post)
        self.assertEqual(LeaveApplication.objects.get().employee, self.colleague)

    def test_correction_for_others(self):
        post = {"attendance_id": self.att.pk, "new_in_time": "09:00", "new_out_time": "19:00", "reason": "x"}
        self.assertEqual(self.client.post(reverse("submit_correction_request"), post).status_code, 403)
        self._tick("attendance_corrections", "create")
        self.client.post(reverse("submit_correction_request"), post)
        self.assertTrue(AttendanceCorrectionRequest.objects.filter(attendance=self.att).exists())

    def test_comp_off_for_others(self):
        post = {"employee_id": self.colleague.pk, "from_date": DAY.isoformat(), "to_date": DAY.isoformat(), "reason": "x"}
        self.assertEqual(self.client.post(reverse("submit_comp_off_request"), post).status_code, 403)
        self._tick("comp_off", "edit")
        self.client.post(reverse("submit_comp_off_request"), post)
        self.assertEqual(CompOffRequest.objects.get().employee, self.colleague)

    def test_register_day_edits(self):
        self._tick("attendance_register", "view")
        page = self.client.get(reverse("attendance-register"))
        self.assertFalse(page.context["can_edit_attendance"])
        post = {"attendance_id": self.att.pk, "status": "Absent"}
        self.assertEqual(self.client.post(reverse("override_attendance_status"), post).status_code, 403)
        self._tick("attendance_register", "edit")
        self.assertTrue(self.client.get(reverse("attendance-register")).context["can_edit_attendance"])
        self.assertNotEqual(self.client.post(reverse("override_attendance_status"), post).status_code, 403)
