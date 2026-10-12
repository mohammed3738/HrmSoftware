"""
HR archives and restores nothing: every archive endpoint, and the shared
restore endpoint, also needs "Archive & Restore Records", which HR doesn't
hold. Admin still archives as before.

Run with: python manage.py test website.tests.test_hr_cannot_archive
"""
from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from website.models import Announcement, Branch, Company, Department, Employee


class HrCannotArchiveTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Arc Co", short_name="ARC", address="A", status="active")
        self.branch = Branch.objects.create(branch_name="Arc HQ")
        self.department = Department.objects.create(name="Arc Dept")
        self.announcement = Announcement.objects.create(title="Hi", body="Hello")
        self.employee = Employee.objects.create(
            company=self.company, first_name="Arc", last_name="Hive", employee_code="ARC001", status="Active",
        )
        self.hr = self._client("HR")
        self.admin = self._client("Admin")

    def _client(self, role):
        user = User.objects.create_user(username=f"arc_{role}", password="pass12345")
        user.groups.add(Group.objects.get(name=role))
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return client

    def _archive_urls(self):
        return [
            reverse("department-delete", args=[self.department.pk]),
            reverse("delete_branch", args=[self.branch.pk]),
            reverse("delete_company", args=[self.company.pk]),
            reverse("delete_employee", args=[self.employee.pk]),
            reverse("delete-announcement", args=[self.announcement.pk]),
        ]

    def test_hr_is_refused_everywhere(self):
        for url in self._archive_urls():
            with self.subTest(url=url):
                self.assertEqual(self.hr.post(url).status_code, 403)
        self.department.refresh_from_db()
        self.branch.refresh_from_db()
        self.announcement.refresh_from_db()
        self.assertTrue(self.department.is_active and self.branch.is_active and self.announcement.is_active)

    def test_hr_cannot_restore(self):
        Branch.objects.filter(pk=self.branch.pk).update(is_active=False)
        Employee.objects.filter(pk=self.employee.pk).update(status="Archived")
        self.assertEqual(self.hr.post(reverse("restore-record", args=["branch", self.branch.pk])).status_code, 403)
        self.assertEqual(self.hr.post(reverse("restore-record", args=["employee", self.employee.pk])).status_code, 403)
        self.branch.refresh_from_db()
        self.employee.refresh_from_db()
        self.assertFalse(self.branch.is_active)
        self.assertEqual(self.employee.status, "Archived")

    def test_admin_still_archives_and_restores(self):
        self.admin.post(reverse("department-delete", args=[self.department.pk]))
        self.admin.post(reverse("delete_branch", args=[self.branch.pk]))
        self.department.refresh_from_db()
        self.branch.refresh_from_db()
        self.assertFalse(self.department.is_active)
        self.assertFalse(self.branch.is_active)
        self.admin.post(reverse("restore-record", args=["branch", self.branch.pk]))
        self.branch.refresh_from_db()
        self.assertTrue(self.branch.is_active)

    def test_hr_sees_no_archive_buttons(self):
        pages = {
            reverse("department-list"): "Archive this department?",
            reverse("create-branch"): 'onclick="confirmArchiveBranch(',
            reverse("employee_list"): 'onclick="confirmEmployeeDelete(',
        }
        for url, marker in pages.items():
            with self.subTest(url=url):
                self.assertNotContains(self.hr.get(url), marker)
                self.assertContains(self.admin.get(url), marker)
        self.assertContains(self.hr.get(reverse("announcements-hub")), "const canArchive = false")
