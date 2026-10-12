"""
HR (like any employee) raises leave, comp-off and attendance-correction
requests only for themselves; Admin can still raise them for others. Also:
the salary slip shows the net pay in words.

Run with: python manage.py test website.tests.test_raise_for_self_only
"""
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import (
    Attendance, AttendanceCorrectionRequest, Company, CompOffRequest, Employee, LeaveApplication,
    PayrollRecord, PayrollRun,
)
from website.views import _amount_in_words

DAY = date.today() - timedelta(days=5)
FUTURE = date.today() + timedelta(days=20)


class RaiseForSelfOnlyTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Self Co", short_name="SLF", address="A")
        self.hr_user, self.hr = self._login("self_hr", "HR")
        self.hr_emp = self._employee("SELF-HR", self.hr_user)
        self.colleague = self._employee("SELF-CO")
        _, self.admin = self._login("self_admin", "Admin")
        self.colleague_att = Attendance.objects.create(employee=self.colleague, date=DAY,
                                                       in_time=time(9, 0), out_time=time(18, 0))
        self.own_att = Attendance.objects.create(employee=self.hr_emp, date=DAY,
                                                 in_time=time(9, 0), out_time=time(18, 0))

    def _login(self, username, role):
        user = User.objects.create_user(username=username, password="pass12345")
        user.groups.add(Group.objects.get(name=role))
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return user, client

    def _employee(self, code, user=None):
        return Employee.objects.create(company=self.company, user=user, first_name=code, last_name="X",
                                       employee_code=code, status="Active", force_password_change=False,
                                       date_of_joining=date(2020, 1, 1))

    # ── leave ─────────────────────────────────────────────────────────
    def _apply(self, client, employee):
        return client.post(reverse("leave_apply"), {
            "employee": employee.pk, "start_date": FUTURE.isoformat(), "end_date": FUTURE.isoformat(), "reason": "x",
        })

    def test_hr_leave_is_always_for_themselves(self):
        self._apply(self.hr, self.colleague)  # tries to apply for a colleague
        leave = LeaveApplication.objects.get()
        self.assertEqual(leave.employee, self.hr_emp)

    def test_hr_sees_only_their_own_leaves_and_no_employee_picker(self):
        LeaveApplication.objects.create(employee=self.colleague, start_date=FUTURE, end_date=FUTURE, reason="theirs")
        LeaveApplication.objects.create(employee=self.hr_emp, start_date=FUTURE, end_date=FUTURE, reason="mine")
        page = self.hr.get(reverse("leave_apply"))
        self.assertEqual([l.employee for l in page.context["leaves"]], [self.hr_emp])
        self.assertNotContains(page, 'name="employee"')
        self.assertContains(page, "Applying for:")

    def test_admin_can_apply_for_someone_else(self):
        self._apply(self.admin, self.colleague)
        self.assertEqual(LeaveApplication.objects.get().employee, self.colleague)

    # ── comp-off ──────────────────────────────────────────────────────
    def _compoff(self, client, employee):
        return client.post(reverse("submit_comp_off_request"), {
            "employee_id": employee.pk, "from_date": DAY.isoformat(), "to_date": DAY.isoformat(), "reason": "x",
        })

    def test_hr_cannot_raise_comp_off_for_others(self):
        self.assertEqual(self._compoff(self.hr, self.colleague).status_code, 403)
        self.assertFalse(CompOffRequest.objects.exists())

    def test_hr_can_raise_comp_off_for_themselves(self):
        self._compoff(self.hr, self.hr_emp)
        self.assertEqual(CompOffRequest.objects.get().employee, self.hr_emp)

    def test_admin_can_raise_comp_off_for_others(self):
        self._compoff(self.admin, self.colleague)
        self.assertEqual(CompOffRequest.objects.get().employee, self.colleague)

    # ── attendance correction ─────────────────────────────────────────
    def _correction(self, client, att):
        return client.post(reverse("submit_correction_request"), {
            "attendance_id": att.pk, "new_in_time": "09:00", "new_out_time": "19:00", "reason": "x",
        })

    def test_hr_cannot_raise_correction_for_others(self):
        self.assertEqual(self._correction(self.hr, self.colleague_att).status_code, 403)
        self.assertFalse(AttendanceCorrectionRequest.objects.exists())

    def test_hr_can_raise_correction_for_themselves(self):
        self._correction(self.hr, self.own_att)
        self.assertTrue(AttendanceCorrectionRequest.objects.filter(attendance=self.own_att).exists())

    def test_attendance_list_offers_hr_raise_buttons_only_on_own_rows(self):
        page = self.hr.get(reverse("attendance") + f"?date={DAY.isoformat()}").content.decode()
        self.assertIn(f"openCorrectionModal('{self.own_att.pk}'", page)
        self.assertNotIn(f"openCorrectionModal('{self.colleague_att.pk}'", page)
        self.assertIn(f"openCompOffModal('{self.hr_emp.pk}'", page)
        self.assertNotIn(f"openCompOffModal('{self.colleague.pk}'", page)
        admin_page = self.admin.get(reverse("attendance") + f"?date={DAY.isoformat()}").content.decode()
        self.assertIn(f"openCorrectionModal('{self.colleague_att.pk}'", admin_page)

    # ── amount in words ───────────────────────────────────────────────
    def test_amount_in_words(self):
        self.assertEqual(_amount_in_words(Decimal("19155")), "Rupees Nineteen Thousand One Hundred Fifty Five Only")
        self.assertEqual(_amount_in_words(123456), "Rupees One Lakh Twenty Three Thousand Four Hundred Fifty Six Only")
        self.assertEqual(_amount_in_words(25034567),
                         "Rupees Two Crore Fifty Lakh Thirty Four Thousand Five Hundred Sixty Seven Only")
        self.assertEqual(_amount_in_words(Decimal("999.5")), "Rupees One Thousand Only")
        self.assertEqual(_amount_in_words(0), "Rupees Zero Only")

    def test_salary_slip_shows_net_pay_in_words(self):
        run = PayrollRun.objects.create(company=self.company, month=date(2026, 1, 1), start_date=date(2026, 1, 1),
                                        end_date=date(2026, 1, 31), status=PayrollRun.STATUS_FINALIZED)
        rec = PayrollRecord.objects.create(payroll=run, employee=self.hr_emp, employee_code="SELF-HR",
                                           employee_name="Hr", total_days=31, basic_processed=Decimal(20000),
                                           net_salary=Decimal(19155))
        page = self.hr.get(reverse("salary-slip", args=[rec.pk]))
        self.assertContains(page, "Rupees Nineteen Thousand One Hundred Fifty Five Only")
