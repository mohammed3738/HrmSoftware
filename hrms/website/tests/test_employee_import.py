"""
Regression tests for the chunked employee Excel import.

Replaces a single all-in-one POST that processed the whole file inside one
request (a large file could time out with a generic, unhelpful failure) and
where only the final .save() call was wrapped in a try/except -- any
exception raised while building a row's data (a duplicated column header
turning row.get(col) into a Series, for instance) escaped every per-row
guard and aborted the rest of the file with a single opaque "Server error:
...", indistinguishable from a real crash and with no row number.

Covers:
  * the init/chunk flow actually creates employees and reports real
    processed/total progress a chunk at a time;
  * a bad row does not stop the rows around it, and is reported with its
    row number and a specific reason instead of killing the batch;
  * shift times entered as "10.00" (period instead of colon) are now
    understood instead of silently dropping the shift time -- the actual
    bug report this file was extended for;
  * the structural failures worth a clear message before any row is
    touched: duplicate column headers, an unreadable file, a file that
    doesn't match the template;
  * permission gating on both endpoints.

Run with: python manage.py test website.tests.test_employee_import
"""
import io
from datetime import time as dt_time

import openpyxl
from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse

from website import views as website_views
from website.models import Branch, Company, Employee, EmployeeImportUpload
from website.views import parse_excel_shift_time

TEMPLATE_HEADERS = [
    "Employee Code*", "Salutation*", "First Name*", "Middle Name", "Last Name*",
    "Father Name*", "Gender* (Male/Female)", "Blood Group*", "Date of Birth* (YYYY-MM-DD)",
    "Place of Birth*", "Personal Email*", "Personal Mobile*",
    "Present Address*", "Permanent Address*", "Date of Marriage (YYYY-MM-DD)",
    "Company Name*", "Branch Name*", "Designation*", "Department*",
    "Date of Joining* (YYYY-MM-DD)", "Date of Confirmation (YYYY-MM-DD)",
    "Location*", "On Payroll Of",
    "Shift Start Time (HH:MM)", "Shift End Time (HH:MM)",
    "PAN No*", "Aadhar No*", "Voter ID", "Passport", "UAN No", "PF No", "ESIC No",
    "Name As Per Bank*", "Salary Account Number*", "IFSC Code*",
    "Emergency Contact Name 1*", "Emergency Contact Relation 1*", "Emergency Contact Mobile 1*",
    "Emergency Contact Name 2", "Emergency Contact Relation 2", "Emergency Contact Mobile 2",
    "Status (Active/Pending/Left)",
]


def build_excel(headers, rows):
    """rows: list of dicts keyed by header name; missing keys become blank."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h, "") for h in headers])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    buf.name = "employees.xlsx"
    return buf


def minimal_row(code, **overrides):
    row = {
        "Employee Code*": code,
        "Salutation*": "Mr",
        "First Name*": "Test",
        "Last Name*": code,
        "Gender* (Male/Female)": "Male",
        "Date of Birth* (YYYY-MM-DD)": "1990-01-01",
        "Personal Email*": f"{code.lower()}@test.com",
        "Personal Mobile*": "1234567890",
        "Designation*": "Dev",
        "Date of Joining* (YYYY-MM-DD)": "2024-01-01",
        "PAN No*": "ABCDE1234F",
        "Aadhar No*": "123456789012",
        "Status (Active/Pending/Left)": "Active",
    }
    row.update(overrides)
    return row


class EmployeeImportTest(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(username="imp_admin", password="pass12345")
        self.admin_user.groups.add(Group.objects.get(name="Admin"))
        self.client = Client()
        self.client.login(username="imp_admin", password="pass12345")

    def _init(self, excel_file):
        return self.client.post(reverse("import-employees-init"), {"employee_file": excel_file})

    def _run_to_completion(self, upload_id, max_chunks=50):
        """Call the chunk endpoint until done=True, returning the final
        payload -- mirrors what the frontend's processNextChunk loop does."""
        data = None
        for _ in range(max_chunks):
            resp = self.client.post(reverse("import-employees-chunk", args=[upload_id]))
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["success"], data)
            if data["done"]:
                return data
        self.fail("import did not complete within max_chunks")

    # ── happy path ──────────────────────────────────────────────────────

    def test_init_reports_total_rows_without_creating_anyone(self):
        excel = build_excel(TEMPLATE_HEADERS, [minimal_row("IMP001"), minimal_row("IMP002")])
        resp = self._init(excel)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["total_rows"], 2)
        self.assertIn("upload_id", data)
        self.assertIn("chunk_size", data)
        self.assertFalse(Employee.objects.filter(employee_code__in=["IMP001", "IMP002"]).exists())

    def test_chunk_creates_employees_and_reports_real_progress(self):
        excel = build_excel(TEMPLATE_HEADERS, [minimal_row("IMP010"), minimal_row("IMP011")])
        upload_id = self._init(excel).json()["upload_id"]

        resp = self.client.post(reverse("import-employees-chunk", args=[upload_id]))
        data = resp.json()
        self.assertTrue(data["done"])  # both rows fit in one chunk (chunk size 100)
        self.assertEqual(data["processed_rows"], 2)
        self.assertEqual(data["total_rows"], 2)
        self.assertEqual(data["created"], 2)
        self.assertEqual(data["skipped"], 0)
        self.assertEqual(Employee.objects.filter(employee_code__in=["IMP010", "IMP011"]).count(), 2)

    def test_progress_advances_across_multiple_chunks(self):
        """Forces a small chunk size so a handful of rows still needs
        several chunk calls, proving the frontend's percentage would climb
        instead of jumping straight to 100%."""
        rows = [minimal_row(f"IMPC{i:03d}") for i in range(5)]
        excel = build_excel(TEMPLATE_HEADERS, rows)
        upload_id = self._init(excel).json()["upload_id"]

        original_chunk_size = website_views.EMPLOYEE_IMPORT_CHUNK_SIZE
        website_views.EMPLOYEE_IMPORT_CHUNK_SIZE = 2
        try:
            seen_progress = []
            for _ in range(10):
                resp = self.client.post(reverse("import-employees-chunk", args=[upload_id]))
                data = resp.json()
                seen_progress.append(data["processed_rows"])
                if data["done"]:
                    break
        finally:
            website_views.EMPLOYEE_IMPORT_CHUNK_SIZE = original_chunk_size

        self.assertEqual(seen_progress, [2, 4, 5])  # climbs, not one jump to the end
        self.assertEqual(Employee.objects.filter(employee_code__startswith="IMPC").count(), 5)

    def test_creates_the_linked_login_with_forced_password_change(self):
        excel = build_excel(TEMPLATE_HEADERS, [minimal_row("IMP020")])
        upload_id = self._init(excel).json()["upload_id"]
        self._run_to_completion(upload_id)

        emp = Employee.objects.get(employee_code="IMP020")
        self.assertIsNotNone(emp.user)
        # Login provisioning is handled by the sync_user signal (same path
        # as manually adding an employee), which keeps the employee code's
        # original case rather than lowercasing it.
        self.assertEqual(emp.user.username, "IMP020")
        self.assertTrue(emp.force_password_change)

    def test_a_row_whose_login_username_is_already_taken_still_creates_the_employee(self):
        # A User with this exact username already exists but isn't linked
        # to any employee (e.g. an orphaned/leftover account) -- this must
        # not crash the whole row. The employee record itself is still
        # useful even if the login has to be provisioned by hand afterwards
        # via the existing Create User page.
        User.objects.create_user(username="IMP021", password="whatever")
        excel = build_excel(TEMPLATE_HEADERS, [minimal_row("IMP021")])
        upload_id = self._init(excel).json()["upload_id"]
        data = self._run_to_completion(upload_id)

        self.assertEqual(data["created"], 1)
        self.assertEqual(data["skipped"], 0)
        emp = Employee.objects.get(employee_code="IMP021")
        self.assertIsNone(emp.user)

    def test_company_and_branch_are_resolved_by_name(self):
        company = Company.objects.create(
            short_name="IMPC", name="Import Test Co", phone="1", email="i@test.com", address="Addr",
        )
        branch = Branch.objects.create(branch_name="Import HQ")
        excel = build_excel(TEMPLATE_HEADERS, [minimal_row(
            "IMP030", **{"Company Name*": "Import Test Co", "Branch Name*": "Import HQ"}
        )])
        upload_id = self._init(excel).json()["upload_id"]
        self._run_to_completion(upload_id)

        emp = Employee.objects.get(employee_code="IMP030")
        self.assertEqual(emp.company_id, company.id)
        self.assertEqual(emp.branch_id, branch.id)

    # ── shift times entered as "10.00" instead of "10:00" ──────────────
    #
    # The template header asks for "(HH:MM)", but real files commonly have
    # the hour/minute separated by a period instead of a colon -- typed via
    # numpad, or because the cell wasn't formatted as text so Excel turned
    # "10:00" into the number 10. pd.to_datetime(..., format="%H:%M") only
    # matches a literal colon and its flexible fallback doesn't understand
    # a bare "10.00" either, so every one of these silently produced no
    # shift time at all with zero indication anything was wrong.

    def test_period_separated_shift_times_are_understood(self):
        excel = build_excel(TEMPLATE_HEADERS, [minimal_row(
            "IMP200", **{"Shift Start Time (HH:MM)": "10.00", "Shift End Time (HH:MM)": "7.00"},
        )])
        upload_id = self._init(excel).json()["upload_id"]
        self._run_to_completion(upload_id)

        emp = Employee.objects.get(employee_code="IMP200")
        self.assertEqual(emp.shift_start_time, dt_time(10, 0))
        self.assertEqual(emp.shift_end_time, dt_time(7, 0))

    def test_colon_separated_shift_times_still_work_as_documented(self):
        excel = build_excel(TEMPLATE_HEADERS, [minimal_row(
            "IMP201", **{"Shift Start Time (HH:MM)": "07:00", "Shift End Time (HH:MM)": "18:30"},
        )])
        upload_id = self._init(excel).json()["upload_id"]
        self._run_to_completion(upload_id)

        emp = Employee.objects.get(employee_code="IMP201")
        self.assertEqual(emp.shift_start_time, dt_time(7, 0))
        self.assertEqual(emp.shift_end_time, dt_time(18, 30))

    def test_a_shift_time_that_cannot_be_understood_is_a_warning_not_a_skip(self):
        excel = build_excel(TEMPLATE_HEADERS, [minimal_row(
            "IMP202", **{"Shift Start Time (HH:MM)": "half past ten"},
        )])
        upload_id = self._init(excel).json()["upload_id"]
        data = self._run_to_completion(upload_id)

        self.assertEqual(data["created"], 1)
        self.assertEqual(data["skipped"], 0)
        self.assertEqual(len(data["errors"]), 0)
        self.assertEqual(len(data["warnings"]), 1)
        self.assertEqual(data["warnings"][0]["row"], 2)
        self.assertIn("half past ten", data["warnings"][0]["errors"][0])

        emp = Employee.objects.get(employee_code="IMP202")
        self.assertIsNone(emp.shift_start_time)

    def test_a_blank_shift_time_is_not_a_warning(self):
        excel = build_excel(TEMPLATE_HEADERS, [minimal_row("IMP203")])  # no shift columns set
        upload_id = self._init(excel).json()["upload_id"]
        data = self._run_to_completion(upload_id)
        self.assertEqual(data["warnings"], [])

    # ── the core fix: one bad row must not take the whole file down ────

    def test_a_bad_row_is_skipped_with_its_row_number_and_the_rest_still_import(self):
        excel = build_excel(TEMPLATE_HEADERS, [
            minimal_row("IMP040"),
            minimal_row(""),          # row 3: blank employee code
            minimal_row("IMP041"),
        ])
        upload_id = self._init(excel).json()["upload_id"]
        data = self._run_to_completion(upload_id)

        self.assertEqual(data["created"], 2)
        self.assertEqual(data["skipped"], 1)
        self.assertEqual(len(data["errors"]), 1)
        self.assertEqual(data["errors"][0]["row"], 3)
        self.assertIn("Employee Code is required", data["errors"][0]["errors"][0])
        self.assertTrue(Employee.objects.filter(employee_code="IMP040").exists())
        self.assertTrue(Employee.objects.filter(employee_code="IMP041").exists())

    def test_duplicate_employee_code_within_the_file_is_reported_clearly(self):
        excel = build_excel(TEMPLATE_HEADERS, [
            minimal_row("IMP050"),
            minimal_row("IMP050"),  # row 3: same code again
        ])
        upload_id = self._init(excel).json()["upload_id"]
        data = self._run_to_completion(upload_id)

        self.assertEqual(data["created"], 1)
        self.assertEqual(data["skipped"], 1)
        self.assertIn("already exists", data["errors"][0]["errors"][0])
        self.assertEqual(Employee.objects.filter(employee_code="IMP050").count(), 1)

    def test_duplicate_employee_code_against_an_existing_employee_is_reported_clearly(self):
        Employee.objects.create(employee_code="IMP060", first_name="Existing", last_name="One", status="Active")
        excel = build_excel(TEMPLATE_HEADERS, [minimal_row("IMP060")])
        upload_id = self._init(excel).json()["upload_id"]
        data = self._run_to_completion(upload_id)

        self.assertEqual(data["created"], 0)
        self.assertEqual(data["skipped"], 1)
        self.assertIn('"IMP060" already exists', data["errors"][0]["errors"][0])

    def test_a_row_that_raises_unexpectedly_does_not_stop_the_rows_after_it(self):
        """Proves the whole row body is inside the per-row guard, not just
        the final .save() -- forces an exception during row-data
        construction (what a duplicate-header Series used to trigger
        uncaught) and checks the row after it still imports.

        There are 4 date columns in the template (DOB, joining, confirmation,
        marriage), so parse_excel_date is called 4 times per row regardless
        of whether each cell is filled -- the 5th call overall is therefore
        the first date field of the SECOND row, which is the one this test
        needs to fail."""
        from unittest.mock import patch

        excel = build_excel(TEMPLATE_HEADERS, [
            minimal_row("IMP070"),
            minimal_row("IMP071"),
            minimal_row("IMP072"),
        ])
        upload_id = self._init(excel).json()["upload_id"]

        call_count = {"n": 0}
        real_parse_excel_date = website_views.parse_excel_date

        def flaky_parse_excel_date(val):
            call_count["n"] += 1
            if call_count["n"] == 5:
                raise ValueError("simulated corrupt cell")
            return real_parse_excel_date(val)

        with patch.object(website_views, "parse_excel_date", side_effect=flaky_parse_excel_date):
            data = self._run_to_completion(upload_id)

        self.assertEqual(data["created"], 2)
        self.assertEqual(data["skipped"], 1)
        self.assertEqual(len(data["errors"]), 1)
        self.assertIn("simulated corrupt cell", data["errors"][0]["errors"][0])
        self.assertTrue(Employee.objects.filter(employee_code="IMP070").exists())
        self.assertFalse(Employee.objects.filter(employee_code="IMP071").exists())
        self.assertTrue(Employee.objects.filter(employee_code="IMP072").exists())

    # ── clear errors for structural problems, before any row is touched ─

    def test_duplicate_column_headers_are_rejected_with_a_specific_message(self):
        # A literal duplicate header (two cells reading exactly "Employee
        # Code*") gets auto-renamed by pandas itself on read (to "Employee
        # Code*.1"), so it never actually collides. A trailing-space variant
        # is the real-world case: pandas reads it as a distinct column, and
        # only this app's own .str.strip() call turns the two into a true
        # duplicate -- which is the case this check exists for.
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Employee Code*", "First Name*", "Employee Code* "])
        ws.append(["IMP080", "Dup", "IMP080"])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "dupes.xlsx"

        resp = self._init(buf)
        data = resp.json()
        self.assertFalse(data["success"])
        self.assertIn("duplicate column headers", data["error"].lower())
        self.assertIn("Employee Code*", data["error"])
        self.assertFalse(EmployeeImportUpload.objects.exists())

    def test_a_file_that_does_not_match_the_template_is_rejected(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Some Column", "Another Column"])
        ws.append(["a", "b"])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "wrong.xlsx"

        resp = self._init(buf)
        data = resp.json()
        self.assertFalse(data["success"])
        self.assertIn("Download Excel Template", data["error"])

    def test_an_unreadable_file_is_rejected_with_a_readable_message(self):
        bogus = io.BytesIO(b"this is not an excel file")
        bogus.name = "not_excel.xlsx"
        resp = self._init(bogus)
        data = resp.json()
        self.assertFalse(data["success"])
        self.assertIn("Cannot read this file", data["error"])

    def test_a_file_with_zero_data_rows_completes_immediately(self):
        excel = build_excel(TEMPLATE_HEADERS, [])
        resp = self._init(excel)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["total_rows"], 0)
        upload = EmployeeImportUpload.objects.get(id=data["upload_id"])
        self.assertEqual(upload.status, "completed")

    def test_no_file_uploaded_is_a_clean_error_not_a_crash(self):
        resp = self.client.post(reverse("import-employees-init"), {})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["success"])
        self.assertIn("No file uploaded", data["error"])

    # ── calling chunk on a finished/unknown upload ─────────────────────

    def test_chunk_on_an_already_completed_upload_is_idempotent(self):
        excel = build_excel(TEMPLATE_HEADERS, [minimal_row("IMP090")])
        upload_id = self._init(excel).json()["upload_id"]
        first = self._run_to_completion(upload_id)

        again = self.client.post(reverse("import-employees-chunk", args=[upload_id])).json()
        self.assertEqual(again, first)
        self.assertEqual(Employee.objects.filter(employee_code="IMP090").count(), 1)

    def test_chunk_for_an_unknown_upload_id_404s_rather_than_500s(self):
        resp = self.client.post(reverse("import-employees-chunk", args=[999999]))
        self.assertEqual(resp.status_code, 404)

    # ── permissions ─────────────────────────────────────────────────────

    def test_employee_role_cannot_import(self):
        emp_user = User.objects.create_user(username="imp_emp", password="pass12345")
        emp_user.groups.add(Group.objects.get(name="Employee"))
        client = Client()
        client.login(username="imp_emp", password="pass12345")

        excel = build_excel(TEMPLATE_HEADERS, [minimal_row("IMP100")])
        resp = client.post(reverse("import-employees-init"), {"employee_file": excel})
        self.assertEqual(resp.status_code, 403)

    def test_hr_can_import_new_employees(self):
        """HR holds employee_records:create but not :edit -- the import
        endpoints are gated on :edit (adding via import is still a change
        to the employee table, matching the existing create_or_edit_employee
        gate), so confirm HR's actual access explicitly rather than assume."""
        from website.utils.permissions import has_feature_permission
        hr_user = User.objects.create_user(username="imp_hr", password="pass12345")
        hr_user.groups.add(Group.objects.get(name="HR"))
        client = Client()
        client.login(username="imp_hr", password="pass12345")

        excel = build_excel(TEMPLATE_HEADERS, [minimal_row("IMP110")])
        resp = client.post(reverse("import-employees-init"), {"employee_file": excel})
        expected_403 = not has_feature_permission(hr_user, "employee_records", "edit")
        self.assertEqual(resp.status_code, 403 if expected_403 else 200)


class ParseExcelShiftTimeTest(TestCase):
    """Unit-level coverage for parse_excel_shift_time(), independent of the
    import flow -- exercises exactly the values from the reported bug's
    spreadsheet (a "Shift Start/End Time" column showing "10.00", "7.00",
    "12.00" etc. alongside a few genuine "07:00" cells)."""

    def test_period_separated_whole_hours_from_the_reported_sheet(self):
        for text, expected in [
            ("10.00", dt_time(10, 0)), ("7.00", dt_time(7, 0)), ("12.00", dt_time(12, 0)),
            ("9.00", dt_time(9, 0)), ("11.00", dt_time(11, 0)), ("8.00", dt_time(8, 0)),
        ]:
            with self.subTest(text=text):
                result, note = parse_excel_shift_time(text)
                self.assertEqual(result, expected)
                self.assertIsNone(note)

    def test_the_same_values_as_bare_numbers_not_strings(self):
        """Cells that were never text -- Excel stored them as plain floats
        (10.0, not "10.00") once the cell wasn't formatted as text."""
        for value, expected in [(10.0, dt_time(10, 0)), (7.0, dt_time(7, 0)), (12.0, dt_time(12, 0))]:
            with self.subTest(value=value):
                result, note = parse_excel_shift_time(value)
                self.assertEqual(result, expected)
                self.assertIsNone(note)

    def test_colon_format_still_works(self):
        result, note = parse_excel_shift_time("07:00")
        self.assertEqual(result, dt_time(7, 0))
        self.assertIsNone(note)

    def test_period_separated_with_real_minutes(self):
        result, note = parse_excel_shift_time("9.30")
        self.assertEqual(result, dt_time(9, 30))
        self.assertIsNone(note)

    def test_blank_and_none_are_not_warnings(self):
        for value in (None, "", "nan", float("nan")):
            with self.subTest(value=value):
                result, note = parse_excel_shift_time(value)
                self.assertIsNone(result)
                self.assertIsNone(note)

    def test_a_datetime_time_object_passes_through(self):
        result, note = parse_excel_shift_time(dt_time(14, 15))
        self.assertEqual(result, dt_time(14, 15))
        self.assertIsNone(note)

    def test_genuinely_unreadable_text_produces_a_note_and_no_time(self):
        result, note = parse_excel_shift_time("whenever")
        self.assertIsNone(result)
        self.assertIn("whenever", note)

    def test_out_of_range_values_are_rejected_not_wrapped(self):
        result, note = parse_excel_shift_time("25.99")
        self.assertIsNone(result)
        self.assertIsNotNone(note)
