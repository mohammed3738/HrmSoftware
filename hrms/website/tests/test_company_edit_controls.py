"""
Only Super Admin edits companies. Everyone else with company access (Admin,
Payroll Officer, HR) can read the company list but gets no add / bulk
upload / edit / archive controls, and the server refuses those actions.

Run with: python manage.py test website.tests.test_company_edit_controls
"""
from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import Company


class CompanyEditControlsTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Ctl Co", short_name="CTL", address="A", status="active")

    def _client(self, role):
        user = User.objects.create_user(username=f"ctl_{role}".replace(" ", "_"), password="pass12345")
        user.groups.add(Group.objects.get(name=role))
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return client

    def test_hr_reads_companies_without_edit_controls(self):
        resp = self._client("HR").get(reverse("create-company"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Ctl Co")
        self.assertNotContains(resp, 'data-bs-target="#add_company"')
        self.assertNotContains(resp, 'data-bs-target="#bulk_upload_company"')
        self.assertNotContains(resp, 'class="dropdown-item edit-company-btn"')
        self.assertNotContains(resp, 'onclick="confirmArchiveCompany(')

    def test_hr_cannot_add_a_company(self):
        resp = self._client("HR").post(reverse("create-company"), {
            "short_name": "NEW", "name": "New Co", "address": "A", "status": "active",
        })
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Company.objects.filter(short_name="NEW").exists())

    def test_super_admin_sees_edit_controls(self):
        resp = self._client("Super Admin").get(reverse("create-company"))
        self.assertContains(resp, 'data-bs-target="#add_company"')
        self.assertContains(resp, 'class="dropdown-item edit-company-btn"')
        self.assertContains(resp, 'onclick="confirmArchiveCompany(')
