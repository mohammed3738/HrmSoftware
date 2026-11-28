from io import BytesIO

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from website.models import Company, Employee
from website.views import role_based_dashboard_url
from .test_role_dashboards import make_employee


class DashboardReportTests(TestCase):
    def setUp(self):
        company = Company.objects.create(short_name="Test", name="Test")
        self.viewer = User.objects.create_user("viewer")
        self.person = make_employee(company, "VIEW", user=self.viewer)
        self.client.force_login(self.viewer, backend="django.contrib.auth.backends.ModelBackend")
        self.report = make_employee(company, "REP", department="Sales")
        Employee.objects.filter(pk=self.report.pk).update(manager=self.person)
        sub = make_employee(company, "SUB", department="Sales")
        Employee.objects.filter(pk=sub.pk).update(reporting_person=self.report)
        make_employee(company, "OUT", department="Restricted")

    def test_reporting_scope_applies_before_filters_and_export(self):
        response = self.client.get(reverse("team-analytics"))
        self.assertContains(response, "Manager dashboard")
        self.assertEqual(dict(response.context["metrics"])["Active employees today"], 2)
        self.assertNotContains(response, "Restricted")
        export = self.client.get(reverse("team-analytics"), {"department": "Restricted", "export": "xlsx"})
        sheet = load_workbook(BytesIO(export.content), read_only=True).active
        self.assertIn(("Active employees today", 0), list(sheet.values))
        self.assertEqual(self.client.get(reverse("executive-dashboard")).status_code, 403)

    def test_director_lands_on_executive_summaries(self):
        self.viewer.groups.add(Group.objects.get(name="Director"))
        self.assertEqual(role_based_dashboard_url(self.viewer), "executive-dashboard")
        response = self.client.get(reverse("executive-dashboard"))
        self.assertContains(response, "Finalized payroll")
        self.assertEqual(dict(response.context["metrics"])["Active employees today"], 4)

    def test_no_team_access_without_reports(self):
        Employee.objects.filter(pk=self.report.pk).update(manager=None)
        self.assertEqual(self.client.get(reverse("team-analytics")).status_code, 403)

    def test_admin_company_filter_scopes_dashboard_and_analytics_link(self):
        self.viewer.groups.add(Group.objects.get(name="Super Admin"))
        other = Company.objects.create(short_name="Other", name="Other")
        make_employee(other, "OTHER")
        response = self.client.get(reverse("admin-dashboard"), {"company": other.pk})
        self.assertEqual(response.context["total_active"], 1)
        self.assertContains(response, reverse("workforce-analytics") + "?company=" + str(other.pk))
        self.assertEqual(self.client.get(reverse("admin-dashboard"), {"company": "invalid"}).status_code, 404)
