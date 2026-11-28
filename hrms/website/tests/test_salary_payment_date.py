from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from website.models import AuditLog, Company, PayrollRecord, PayrollRun
from .test_role_dashboards import make_employee


class SalaryPaymentDateTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        company = Company.objects.create(name="Payroll Co", short_name="PAY")
        self.staff = User.objects.create_user("payroll")
        self.staff.groups.add(Group.objects.get(name="Payroll Officer"))
        self.employee_user = User.objects.create_user("employee")
        employee = make_employee(company, "PAY1", user=self.employee_user)
        self.run = PayrollRun.objects.create(company=company, month=self.today.replace(day=1),
            start_date=self.today, end_date=self.today, status=PayrollRun.STATUS_FINALIZED)
        self.pay = PayrollRecord.objects.create(payroll=self.run, employee=employee, net_salary=100)
        self.url = reverse("payroll-payment-date", args=[self.pay.pk])
        self.login(self.staff)

    def login(self, user):
        self.client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")

    def record(self, day, previous=""):
        return self.client.post(self.url, {"payment_date": day.isoformat(), "previous": previous})

    def test_employee_sees_confirmed_date_and_retries_preserve_audit(self):
        detail = self.client.get(reverse("payroll-run-detail", args=[self.run.pk]))
        self.assertContains(detail, self.url)
        self.assertEqual(self.record(self.today).status_code, 302)
        self.assertEqual(self.record(self.today).status_code, 302)
        logs = AuditLog.objects.filter(action=AuditLog.Action.PAYROLL_PAYMENT_RECORDED)
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.get().actor, self.staff)
        yesterday = self.today - timedelta(days=1)
        self.assertEqual(self.record(yesterday).status_code, 409)
        self.assertEqual(self.record(yesterday, self.today.isoformat()).status_code, 302)
        self.login(self.employee_user)
        self.assertEqual(self.record(self.today).status_code, 403)
        self.assertContains(self.client.get(reverse("employee-dashboard")), f"Paid on {yesterday.day} {yesterday:%B %Y}")

    def test_draft_future_and_zero_net_rejected(self):
        self.assertEqual(self.record(self.today + timedelta(days=1)).status_code, 400)
        self.run.status = PayrollRun.STATUS_DRAFT
        self.run.save(update_fields=["status"])
        self.assertEqual(self.record(self.today).status_code, 400)
        self.run.status = PayrollRun.STATUS_FINALIZED
        self.run.save(update_fields=["status"])
        PayrollRecord.objects.filter(pk=self.pay.pk).update(net_salary=0)
        self.assertEqual(self.record(self.today).status_code, 400)
        self.pay.refresh_from_db()
        self.assertIsNone(self.pay.payment_date)
    def test_report_counts_confirmations_in_selected_payroll_month(self):
        endpoint = reverse("workforce-analytics")
        filters = {"month": self.today.strftime("%Y-%m")}
        def counts():
            response = self.client.get(endpoint, filters)
            sections = dict(response.context["sections"])
            return dict(sections["Salary payment confirmations"])
        self.assertEqual(counts(), {"Confirmed payslips": 0, "Awaiting confirmation": 1})
        self.record(self.today)
        self.assertEqual(counts(), {"Confirmed payslips": 1, "Awaiting confirmation": 0})
