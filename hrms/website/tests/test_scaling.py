"""
Pages and bulk jobs that must not slow down as the company grows: their
query counts stay flat as employees are added, and the faster code paths
give the same answers as the original ones.

Run with: python manage.py test website.tests.test_scaling
"""
from datetime import date, time, timedelta
from decimal import Decimal

import pandas as pd
from django.contrib.auth.models import User
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from website.forms import EmployeeForm
from website.models import (
    Attendance, AttendanceCorrectionRequest, Company, Employee, EmployeeAttachment, PayrollSettings,
)
from website.services.onboarding import bulk_onboarding_progress, onboarding_progress


class ScalingTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Scale Co", short_name="SCL", address="A")
        PayrollSettings.objects.create(company=self.company, weekend_days="sun", from_date=27, to_date=26)
        self.admin = User.objects.create_superuser("scale_admin", "s@test.com", "pass12345")
        self.client = Client()
        self.client.force_login(self.admin, backend="django.contrib.auth.backends.ModelBackend")
        self._add(5)

    def _add(self, n):
        start = Employee.objects.count()
        for i in range(start, start + n):
            emp = Employee.objects.create(company=self.company, first_name=f"S{i}", last_name="Emp",
                                          employee_code=f"SC{i:03d}", status="Active",
                                          date_of_joining=date(2020, 1, 1), personal_email=f"s{i}@t.com")
            if i % 2:
                EmployeeAttachment.objects.create(employee=emp, file_name="pan", file="x.pdf")
            day = date.today() - timedelta(days=10)
            att = Attendance.objects.create(employee=emp, date=day, in_time=time(9, 0), out_time=time(18, 0))
            AttendanceCorrectionRequest.objects.create(
                attendance=att, old_in_time=time(9, 0), old_out_time=time(18, 0),
                new_in_time=time(9, 0), new_out_time=time(19, 0), reason="x",
            )

    def _queries(self, url):
        self.client.get(url)  # warm caches that are meant to be warm
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(self.client.get(url).status_code, 200)
        return len(ctx.captured_queries)

    def test_page_query_counts_do_not_grow_with_employees(self):
        urls = [reverse("admin-dashboard"), reverse("employee_list"), reverse("attendance"),
                reverse("attendance_correction_requests_list"), reverse("leave_balance_report")]
        before = {u: self._queries(u) for u in urls}
        self._add(25)
        after = {u: self._queries(u) for u in urls}
        for url in urls:
            with self.subTest(url=url):
                self.assertLessEqual(after[url], before[url] + 2, f"{url}: {before[url]} -> {after[url]}")

    def test_bulk_onboarding_matches_single(self):
        bulk = bulk_onboarding_progress(Employee.objects.all())
        for emp in Employee.objects.all():
            self.assertEqual(bulk[emp.pk], onboarding_progress(emp))

    def test_employee_list_rows(self):
        resp = self.client.get(reverse("employee_list"))
        rows = resp.context["employees"]
        self.assertEqual(len(rows), Employee.objects.count())
        self.assertEqual(rows[0].keys() >= {"id", "code", "company", "percent", "complete", "status"}, True)
        self.assertContains(resp, 'id="employee-rows-data"')
        self.assertContains(resp, "deferRender: true")

    def test_fast_select_marks_the_selected_person(self):
        target = Employee.objects.first()
        other = Employee.objects.exclude(pk=target.pk).first()
        html = str(EmployeeForm(instance=other, initial={"reporting_person": target.pk})["reporting_person"])
        self.assertIn(f'<option value="{target.pk}" selected>', html)
        self.assertIn('<option value="">---------</option>', html)
        self.assertNotIn(f'<option value="{other.pk}"', html)  # nobody reports to themselves

    def test_upload_skips_a_bad_row_but_keeps_the_rest(self):
        from website.views import _process_attendance_rows
        day = date.today() - timedelta(days=3)
        df = pd.DataFrame({
            "Emp Code": ["SC000", "NOPE", "SC001"],
            "Att.Date": [day, day, day],
            "In Time": ["09:00", "09:00", "09:00"],
            "Out Time": ["18:00", "18:00", "18:00"],
        })
        created, updated, skipped, errors = _process_attendance_rows(df)
        self.assertEqual((created, skipped), (2, 1))
        self.assertEqual(Attendance.objects.filter(date=day).count(), 2)

    def test_upload_lookups_are_shared_across_rows(self):
        from website.views import _process_attendance_rows
        day = date.today() - timedelta(days=4)
        codes = [f"SC{i:03d}" for i in range(5)]
        df = pd.DataFrame({"Emp Code": codes, "Att.Date": [day] * 5, "In Time": ["09:00"] * 5, "Out Time": ["18:00"] * 5})
        with CaptureQueriesContext(connection) as ctx:
            _process_attendance_rows(df)
        settings_reads = [q for q in ctx.captured_queries if 'FROM "website_payrollsettings"' in q["sql"]]
        self.assertLessEqual(len(settings_reads), 3, len(settings_reads))
