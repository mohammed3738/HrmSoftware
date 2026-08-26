"""
Regression tests for the per-row "Save" action on the payroll run detail
page (payroll_record_update).

Bug: the view treated every editable field present in the request payload
as a permanent manual override, including pf_employee/esic_employee. Since
the frontend always sent all 8 editable fields on every save, PF and ESIC
got frozen as "manual" the very first time a row was ever saved -- even if
the user only edited present_days or LWP and never touched PF/ESIC. From
then on, neither a later row Save nor the whole-run Recalculate would ever
auto-update PF/ESIC again for that record.

Fix: PF/ESIC are only locked in as a manual override when the frontend
explicitly says the user edited that field (pf_employee_manual /
esic_employee_manual flags, driven by the input's dataset.manual flag set
only on real user input). If a field was manually overridden on some
earlier save but the flag is now false, the stale override is cleared so it
goes back to auto-calculating.

Run with: python manage.py test website.tests.test_payroll_record_update
"""
import json as json_lib
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from website.models import Company, Employee, PayrollRun, PayrollRecord, PayrollSettings


class PayrollRecordUpdateTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="RU", name="Record Update Co", phone="1", email="ru@test.com", address="Addr",
        )
        PayrollSettings.objects.create(
            company=self.company, pf_percentage=12.00, pf_wage_ceiling=15000.0,
        )
        self.employee = Employee.objects.create(
            company=self.company, salutation="Mr", first_name="Test", last_name="Employee",
            father_name="Father", gender="Male", blood_group="O+",
            date_of_birth=date(1990, 1, 1), place_of_birth="City",
            personal_email="ruemp@test.com", present_address="Addr", permanent_address="Addr",
            personal_mobile="1234567890", employee_code="RUEMP1", designation="Dev", department="IT",
            date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Test",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
        )
        self.run = PayrollRun.objects.create(
            company=self.company, month=date(2026, 8, 1),
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 31),
        )
        self.record = PayrollRecord.objects.create(
            payroll=self.run, employee=self.employee, employee_code="RUEMP1",
            opted_for_pf=True, basic_pm=21000, total_days=31, leave_without_pay=0,
        )
        self.user = User.objects.create_superuser("admin", "admin@test.com", "pass12345")
        self.client = Client()
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def post_update(self, payload):
        return self.client.post(
            reverse("payroll-record-update", args=[self.record.id]),
            data=json_lib.dumps(payload), content_type="application/json",
        )

    def test_editing_lwp_without_touching_pf_keeps_pf_auto_calculated(self):
        # Simulates the frontend's payload when only LWP was edited: PF/ESIC
        # flags are false and the fields are omitted, as saveRow() now does.
        resp = self.post_update({
            "present_days": "30", "leave_without_pay": "1",
            "professional_tax": "200", "advance": "0", "tds": "0", "other_deductions": "0",
            "pf_employee_manual": False, "esic_employee_manual": False,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        # basic_proc = 21000 * 30/31 = 20322.58; 12% of that (2438.71) > flat
        # cap (1800), so PF should be the flat 1800, freshly auto-calculated.
        self.assertEqual(data["record"]["calculation_breakdown"]["deductions"]["pf_employee"], 1800.0)

        self.record.refresh_from_db()
        self.assertNotIn("pf_employee", self.record.manual_override)

    def test_manually_setting_pf_locks_it_as_override(self):
        resp = self.post_update({
            "present_days": "31", "leave_without_pay": "0",
            "professional_tax": "200", "advance": "0", "tds": "0", "other_deductions": "0",
            "pf_employee_manual": True, "pf_employee": "500.00",
            "esic_employee_manual": False,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["record"]["calculation_breakdown"]["deductions"]["pf_employee"], 500.0)

        self.record.refresh_from_db()
        self.assertEqual(self.record.pf_employee, 500.00)
        self.assertEqual(self.record.manual_override.get("pf_employee"), 500.0)

    def test_saving_again_without_pf_flag_clears_stale_manual_override(self):
        # First save manually overrides PF...
        self.post_update({
            "present_days": "31", "leave_without_pay": "0",
            "professional_tax": "200", "advance": "0", "tds": "0", "other_deductions": "0",
            "pf_employee_manual": True, "pf_employee": "500.00",
            "esic_employee_manual": False,
        })
        self.record.refresh_from_db()
        self.assertIn("pf_employee", self.record.manual_override)

        # ...then a later save edits something else and no longer flags PF
        # as manual -- the stale override must be cleared, not resurrected.
        resp = self.post_update({
            "present_days": "31", "leave_without_pay": "0",
            "professional_tax": "250", "advance": "0", "tds": "0", "other_deductions": "0",
            "pf_employee_manual": False, "esic_employee_manual": False,
        })
        data = resp.json()
        self.assertEqual(data["record"]["calculation_breakdown"]["deductions"]["pf_employee"], 1800.0)

        self.record.refresh_from_db()
        self.assertNotIn("pf_employee", self.record.manual_override)
        self.assertEqual(self.record.pf_employee, 1800.00)

    def test_response_reflects_authoritative_server_recalculation(self):
        resp = self.post_update({
            "present_days": "31", "leave_without_pay": "0",
            "professional_tax": "200", "advance": "100", "tds": "50", "other_deductions": "0",
            "pf_employee_manual": False, "esic_employee_manual": False,
        })
        data = resp.json()["record"]
        breakdown = data["calculation_breakdown"]
        expected_total_ded = (
            breakdown["deductions"]["pf_employee"] + breakdown["deductions"]["esic_employee"]
            + breakdown["deductions"]["professional_tax"] + breakdown["deductions"]["tds"]
            + breakdown["deductions"]["advance"] + breakdown["deductions"]["other"]
        )
        self.assertAlmostEqual(data["total_deductions"], expected_total_ded, places=2)
        self.assertAlmostEqual(
            data["net_salary"], breakdown["components"]["gross_processed"] - expected_total_ded, places=2,
        )

    def test_rejects_update_on_finalized_run(self):
        self.run.status = PayrollRun.STATUS_FINALIZED
        self.run.save()
        resp = self.post_update({"present_days": "31"})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])
