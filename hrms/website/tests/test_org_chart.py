from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from website.models import Company, Employee
from .test_role_dashboards import make_employee


class OrgChartTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name="Org Co", short_name="ORG")
        self.user = User.objects.create_user("chart-user")
        self.me = make_employee(company, "EMP", "Selected", user=self.user)
        self.lead = make_employee(company, "LEAD", "Leader")
        self.peer = make_employee(company, "PEER", "Colleague")
        self.manager = make_employee(company, "MGR", "Executive")
        Employee.objects.filter(pk__in=[self.me.pk, self.peer.pk]).update(reporting_person=self.lead, department="Software")
        Employee.objects.filter(pk=self.me.pk).update(manager=self.manager)
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def test_self_line_includes_peers_and_separate_manager(self):
        response = self.client.get(reverse("org-chart"))
        for name in ("Selected", "Leader", "Colleague", "Executive"):
            self.assertContains(response, name)
        self.assertNotContains(response, 'id="org-focus"')
        self.assertEqual(self.client.get(reverse("org-chart"), {"employee": self.peer.pk}).status_code, 403)

    def test_department_peer_with_different_lead_and_unrelated_sibling(self):
        make_employee(self.me.company, "DEV2", "OtherDeveloper", department=" software ")
        make_employee(self.me.company, "FIN", "FinanceSibling", department="Finance", reporting_person=self.lead)
        response = self.client.get(reverse("org-chart"))
        self.assertContains(response, "OtherDeveloper")
        self.assertNotContains(response, "FinanceSibling")

    def test_cycle_and_other_company(self):
        Employee.objects.filter(pk=self.lead.pk).update(manager=self.me)
        other = Company.objects.create(name="Other", short_name="EXT")
        outsider = make_employee(other, "OUT", "External")
        Employee.objects.filter(pk=outsider.pk).update(manager=self.me)
        response = self.client.get(reverse("org-chart"))
        self.assertContains(response, "circular reporting")
        self.assertNotContains(response, "External")

    def test_directory_reader_can_change_focus(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        response = self.client.get(reverse("org-chart"), {"employee": self.lead.pk})
        self.assertEqual(response.context["subject"].pk, self.lead.pk)
        self.assertContains(response, 'id="org-focus"')
