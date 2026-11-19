"""
Attendance page: a From / To filter (e.g. only the 2nd to the 7th), and an
Excel download for any range (the page turns month / year / "what's on
screen" into a from / to pair).

Run with: python manage.py test website.tests.test_attendance_date_range
"""
import io
from datetime import date, time, timedelta

import openpyxl
from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import Attendance, Company, Employee


class AttendanceDateRangeTest(TestCase):
    def setUp(self):
        company = Company.objects.create(short_name="ADR", name="Range Co", phone="1", email="r@t.com", address="A")
        self.user = User.objects.create_user(username="adr_emp", password="pass12345")
        self.user.groups.add(Group.objects.get(name="Employee"))
        self.employee = Employee.objects.create(company=company, user=self.user, first_name="Ran", last_name="Ge",
                                                employee_code="ADR1", date_of_joining=date(2020, 1, 1),
                                                status="Active", force_password_change=False)
        self.other = Employee.objects.create(company=company, first_name="Oth", last_name="Er", employee_code="ADR2",
                                             date_of_joining=date(2020, 1, 1), status="Active")
        d = date(2026, 7, 1)
        while d <= date(2026, 7, 31):
            Attendance.objects.create(employee=self.employee, date=d, in_time=time(9), out_time=time(18))
            d += timedelta(days=1)
        Attendance.objects.create(employee=self.employee, date=date(2025, 3, 3), in_time=time(9), out_time=time(18))
        self.client = Client()
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def _page(self, **params):
        return self.client.get(reverse("employee_attendance_detail", args=[self.employee.pk]), params)

    def _export(self, employee=None, **params):
        return self.client.get(reverse("employee_attendance_export", args=[(employee or self.employee).pk]), params)

    def _rows(self, resp):
        ws = openpyxl.load_workbook(io.BytesIO(resp.content)).active
        return [r[0] for r in ws.iter_rows(min_row=4, values_only=True) if r[0] and r[0][:2].isdigit()]

    def test_from_to_filter_shows_only_those_days(self):
        resp = self._page(from_date="2026-07-02", to_date="2026-07-07")
        dates = [r.date for r in resp.context["attendance_records"]]
        self.assertEqual(sorted(dates), [date(2026, 7, d) for d in range(2, 8)])
        self.assertEqual(resp.context["export_from"], "2026-07-02")

    def test_reversed_dates_are_swapped(self):
        resp = self._page(from_date="2026-07-07", to_date="2026-07-02")
        self.assertEqual(len(list(resp.context["attendance_records"])), 6)

    def test_export_custom_range(self):
        resp = self._export(from_date="2026-07-02", to_date="2026-07-07")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("attendance_ADR1_2026-07-02_to_2026-07-07.xlsx", resp["Content-Disposition"])
        self.assertEqual(self._rows(resp), [f"{d:02d}-07-2026" for d in range(2, 8)])

    def test_export_month_and_year(self):
        self.assertEqual(len(self._rows(self._export(from_date="2026-07-01", to_date="2026-07-31"))), 31)
        self.assertEqual(self._rows(self._export(from_date="2025-01-01", to_date="2025-12-31")), ["03-03-2025"])

    def test_export_everything_when_no_dates(self):
        self.assertEqual(len(self._rows(self._export())), 32)

    def test_employee_cannot_download_a_colleague(self):
        self.assertEqual(self._export(employee=self.other).status_code, 403)

    def test_page_has_the_download_dialog(self):
        resp = self._page()
        self.assertContains(resp, 'id="attDownloadModal"')
        self.assertContains(resp, 'name="from_date"')

    def test_super_admin_can_filter_and_download_anyone(self):
        sa = User.objects.create_user(username="adr_sa", password="pass12345")
        sa.groups.add(Group.objects.get(name="Super Admin"))
        client = Client()
        client.force_login(sa, backend="django.contrib.auth.backends.ModelBackend")
        page = client.get(reverse("employee_attendance_detail", args=[self.employee.pk]),
                          {"from_date": "2026-07-02", "to_date": "2026-07-07"})
        self.assertEqual(len(list(page.context["attendance_records"])), 6)
        self.assertContains(page, 'id="attDownloadModal"')
        self.assertContains(page, 'id="employeeSearch"')  # can jump to any employee
        resp = client.get(reverse("employee_attendance_export", args=[self.employee.pk]),
                          {"from_date": "2026-07-02", "to_date": "2026-07-07"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(self._rows(resp)), 6)
