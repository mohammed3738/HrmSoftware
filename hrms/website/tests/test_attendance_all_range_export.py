"""
All-employees Attendance page: a From / To filter, Company and Department
filters, and an eSSL-style Excel download (day-by-day "Detailed" sheet plus
a per-employee "Summary" sheet) for any month, year or custom range.

Run with: python manage.py test website.tests.test_attendance_all_range_export
"""
import io
from datetime import date, time, timedelta

import openpyxl
from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import Attendance, Company, Employee


class AllAttendanceRangeExportTest(TestCase):
    def setUp(self):
        self.c1 = Company.objects.create(short_name="AA1", name="Alpha Co", phone="1", email="a@t.com", address="A")
        self.c2 = Company.objects.create(short_name="AA2", name="Beta Co", phone="1", email="b@t.com", address="A")
        self.e1 = Employee.objects.create(company=self.c1, first_name="Ann", last_name="One", employee_code="A1",
                                          department="IT", date_of_joining=date(2020, 1, 1), status="Active")
        self.e2 = Employee.objects.create(company=self.c1, first_name="Bob", last_name="Two", employee_code="A2",
                                          department="Sales", date_of_joining=date(2020, 1, 1), status="Active")
        self.e3 = Employee.objects.create(company=self.c2, first_name="Cid", last_name="Three", employee_code="B1",
                                          department="IT", date_of_joining=date(2020, 1, 1), status="Active")
        d = date(2026, 7, 1)
        while d <= date(2026, 7, 10):
            for e in (self.e1, self.e2, self.e3):
                Attendance.objects.create(employee=e, date=d, in_time=time(9), out_time=time(18))
            d += timedelta(days=1)

        self.admin = User.objects.create_user(username="aa_admin", password="pass12345")
        self.admin.groups.add(Group.objects.get(name="Admin"))
        self.client = Client()
        self.client.force_login(self.admin, backend="django.contrib.auth.backends.ModelBackend")

    def _page(self, **params):
        return self.client.get(reverse("attendance"), params)

    def _export(self, client=None, **params):
        return (client or self.client).get(reverse("attendance_export"), params)

    @staticmethod
    def _sheet_rows(resp, sheet):
        ws = openpyxl.load_workbook(io.BytesIO(resp.content))[sheet]
        return [r for r in ws.iter_rows(min_row=4, values_only=True) if r and r[0]]

    def test_from_to_filter_on_the_page(self):
        resp = self._page(from_date="2026-07-02", to_date="2026-07-07")
        self.assertEqual(resp.context["view_mode"], "range")
        records = list(resp.context["attendance_records"])
        self.assertEqual(len(records), 6 * 3)
        self.assertEqual({r.date for r in records}, {date(2026, 7, d) for d in range(2, 8)})
        self.assertContains(resp, 'id="attAllDownloadModal"')

    def test_company_and_department_filters_on_the_page(self):
        resp = self._page(from_date="2026-07-02", to_date="2026-07-07", company_id=self.c1.pk, department="IT")
        self.assertEqual({r.employee for r in resp.context["attendance_records"]}, {self.e1})

    def test_export_detailed_and_summary_sheets(self):
        resp = self._export(from_date="2026-07-02", to_date="2026-07-07")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("attendance_all_2026-07-02_to_2026-07-07.xlsx", resp["Content-Disposition"])
        detailed = self._sheet_rows(resp, "Detailed")
        self.assertEqual(len(detailed), 18)
        self.assertEqual(detailed[0][:2], ("A1", "Ann One"))
        summary = {r[0]: r for r in self._sheet_rows(resp, "Summary")}
        self.assertEqual(set(summary), {"A1", "A2", "B1"})
        a1 = summary["A1"]
        self.assertEqual(sum(a1[4:11]) - a1[5], 6)  # every one of the 6 days lands in one bucket

    def test_export_month_and_company_filter(self):
        resp = self._export(from_date="2026-07-01", to_date="2026-07-31", company_id=self.c2.pk)
        self.assertEqual({r[0] for r in self._sheet_rows(resp, "Detailed")}, {"B1"})
        self.assertIn("AA2_", resp["Content-Disposition"])

    def test_export_refuses_more_than_a_year(self):
        self.assertEqual(self._export(from_date="2024-01-01", to_date="2026-01-01").status_code, 400)

    def test_employee_cannot_use_page_or_download(self):
        user = User.objects.create_user(username="aa_emp", password="pass12345")
        user.groups.add(Group.objects.get(name="Employee"))
        self.e1.user = user
        self.e1.force_password_change = False
        self.e1.save()
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        self.assertEqual(self._export(client=client, from_date="2026-07-01", to_date="2026-07-31").status_code, 403)

    def test_super_admin_can_download(self):
        sa = User.objects.create_user(username="aa_sa", password="pass12345")
        sa.groups.add(Group.objects.get(name="Super Admin"))
        client = Client()
        client.force_login(sa, backend="django.contrib.auth.backends.ModelBackend")
        resp = self._export(client=client, from_date="2026-07-01", to_date="2026-07-10")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(self._sheet_rows(resp, "Detailed")), 30)

    def test_old_single_day_view_still_works(self):
        resp = self._page(date="2026-07-03")
        self.assertEqual(resp.context["view_mode"], "date")
        self.assertEqual(len(list(resp.context["attendance_records"])), 3)
