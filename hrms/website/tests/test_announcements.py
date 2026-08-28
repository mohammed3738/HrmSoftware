"""
Regression tests for the Announcement/Notification system: model visibility
rules, company scoping, the management page's Admin/HR-only gating, and the
read-tracking API used by the notification bell + dashboard banner.

Run with: python manage.py test website.tests.test_announcements
"""
from datetime import date, timedelta

from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse
from django.utils.timezone import now

from website.models import Announcement, AnnouncementRead, Company, Employee


class AnnouncementModelTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="ANN", name="Announcements Co", phone="1", email="ann@test.com", address="Addr",
        )

    def test_is_visible_now_true_for_active_announcement_with_no_window(self):
        a = Announcement.objects.create(title="T", body="B")
        self.assertTrue(a.is_visible_now())

    def test_is_visible_now_false_when_inactive(self):
        a = Announcement.objects.create(title="T", body="B", is_active=False)
        self.assertFalse(a.is_visible_now())

    def test_is_visible_now_false_before_starts_at(self):
        a = Announcement.objects.create(title="T", body="B", starts_at=now() + timedelta(days=1))
        self.assertFalse(a.is_visible_now())

    def test_is_visible_now_false_after_expires_at(self):
        a = Announcement.objects.create(title="T", body="B", expires_at=now() - timedelta(days=1))
        self.assertFalse(a.is_visible_now())

    def test_is_visible_now_true_within_window(self):
        a = Announcement.objects.create(
            title="T", body="B", starts_at=now() - timedelta(days=1), expires_at=now() + timedelta(days=1),
        )
        self.assertTrue(a.is_visible_now())

    def test_is_visible_to_company_true_when_company_blank(self):
        a = Announcement.objects.create(title="T", body="B")
        self.assertTrue(a.is_visible_to_company(self.company))

    def test_is_visible_to_company_matches_own_company_only(self):
        other = Company.objects.create(short_name="OTH", name="Other Co", phone="1", email="oth@test.com", address="Addr")
        a = Announcement.objects.create(title="T", body="B", company=self.company)
        self.assertTrue(a.is_visible_to_company(self.company))
        self.assertFalse(a.is_visible_to_company(other))


class AnnouncementScopingAndReadTrackingTest(TestCase):
    """Covers _visible_announcements_for_user (via the announcements-api
    endpoint) and the read-tracking flow used by the notification bell and
    dashboard banner."""

    def setUp(self):
        self.company_a = Company.objects.create(
            short_name="CA", name="Company A", phone="1", email="a@test.com", address="Addr",
        )
        self.company_b = Company.objects.create(
            short_name="CB", name="Company B", phone="1", email="b@test.com", address="Addr",
        )
        self.global_announcement = Announcement.objects.create(title="Global", body="Everyone sees this")
        self.company_a_announcement = Announcement.objects.create(
            title="Company A only", body="Just for A", company=self.company_a,
        )
        self.company_b_announcement = Announcement.objects.create(
            title="Company B only", body="Just for B", company=self.company_b,
        )
        self.inactive_announcement = Announcement.objects.create(
            title="Inactive", body="Should never show", is_active=False,
        )

    def make_employee(self, company, code, group_name="Employee"):
        employee = Employee.objects.create(
            company=company, salutation="Mr", first_name="Emp", last_name=code,
            father_name="Father", gender="Male", blood_group="O+", date_of_birth=date(1990, 1, 1),
            place_of_birth="City", personal_email=f"{code}@test.com", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890", employee_code=code,
            designation="Dev", department="IT", date_of_joining=date(2020, 1, 1), location="City",
            pan_no="ABCDE1234F", aadhar_no="123456789012", name_as_per_bank="Emp",
            salary_account_number="1234567890", ifsc_code="TEST0001234",
            emergency_contact_name1="Jane", emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
        )
        # sync_user's auto-provisioning always forces force_password_change=True
        # on the newly-linked user regardless of the kwarg above; clear it so
        # ForcePasswordChangeMiddleware doesn't intercept every request in
        # these tests with a redirect to /change-password/.
        employee.force_password_change = False
        employee.save(update_fields=["force_password_change"])
        employee.user.groups.clear()
        employee.user.groups.add(Group.objects.get(name=group_name))
        return employee

    def test_employee_sees_only_own_company_and_global_announcements(self):
        employee = self.make_employee(self.company_a, "ANNEMP1")
        client = Client()
        client.login(username=employee.user.username, password="Temp@123")

        resp = client.get(reverse("announcements-api"))
        titles = {a["title"] for a in resp.json()["announcements"]}

        self.assertIn("Global", titles)
        self.assertIn("Company A only", titles)
        self.assertNotIn("Company B only", titles)
        self.assertNotIn("Inactive", titles)

    def test_manager_also_scoped_to_own_company(self):
        manager = self.make_employee(self.company_b, "ANNMGR1", group_name="Manager")
        client = Client()
        client.login(username=manager.user.username, password="Temp@123")

        resp = client.get(reverse("announcements-api"))
        titles = {a["title"] for a in resp.json()["announcements"]}

        self.assertIn("Global", titles)
        self.assertIn("Company B only", titles)
        self.assertNotIn("Company A only", titles)

    def test_global_access_user_without_employee_profile_sees_everything_active(self):
        admin = User.objects.create_user(username="ann_admin", password="pass12345")
        admin.groups.add(Group.objects.get(name="Admin"))
        client = Client()
        client.login(username="ann_admin", password="pass12345")

        resp = client.get(reverse("announcements-api"))
        titles = {a["title"] for a in resp.json()["announcements"]}

        self.assertIn("Global", titles)
        self.assertIn("Company A only", titles)
        self.assertIn("Company B only", titles)
        self.assertNotIn("Inactive", titles)

    def test_unread_count_and_mark_single_read(self):
        employee = self.make_employee(self.company_a, "ANNEMP2")
        client = Client()
        client.login(username=employee.user.username, password="Temp@123")

        resp = client.get(reverse("announcements-api"))
        data = resp.json()
        self.assertEqual(data["unread_count"], 2)  # Global + Company A only

        client.post(reverse("mark-announcement-read"), {"announcement_id": self.global_announcement.id})

        resp2 = client.get(reverse("announcements-api"))
        data2 = resp2.json()
        self.assertEqual(data2["unread_count"], 1)
        self.assertTrue(AnnouncementRead.objects.filter(
            announcement=self.global_announcement, user=employee.user,
        ).exists())

    def test_mark_all_read(self):
        employee = self.make_employee(self.company_a, "ANNEMP3")
        client = Client()
        client.login(username=employee.user.username, password="Temp@123")

        client.post(reverse("mark-announcement-read"), {})

        resp = client.get(reverse("announcements-api"))
        self.assertEqual(resp.json()["unread_count"], 0)


class AnnouncementManagementPermissionTest(TestCase):
    """announcements_hub / save_announcement / delete_announcement are
    Admin+HR only per SEED_GRANTS; Manager and Employee must be denied."""

    def setUp(self):
        self.company = Company.objects.create(
            short_name="AMP", name="Mgmt Perm Co", phone="1", email="amp@test.com", address="Addr",
        )

    def make_user(self, username, group_name):
        user = User.objects.create_user(username=username, password="pass12345")
        user.groups.add(Group.objects.get(name=group_name))
        return user

    def test_admin_can_view_hub(self):
        self.make_user("amp_admin", "Admin")
        client = Client()
        client.login(username="amp_admin", password="pass12345")
        resp = client.get(reverse("announcements-hub"))
        self.assertEqual(resp.status_code, 200)

    def test_hr_can_view_hub(self):
        self.make_user("amp_hr", "HR")
        client = Client()
        client.login(username="amp_hr", password="pass12345")
        resp = client.get(reverse("announcements-hub"))
        self.assertEqual(resp.status_code, 200)

    def test_manager_cannot_view_hub(self):
        self.make_user("amp_mgr", "Manager")
        client = Client()
        client.login(username="amp_mgr", password="pass12345")
        resp = client.get(reverse("announcements-hub"))
        self.assertEqual(resp.status_code, 403)

    def test_employee_cannot_view_hub(self):
        self.make_user("amp_emp", "Employee")
        client = Client()
        client.login(username="amp_emp", password="pass12345")
        resp = client.get(reverse("announcements-hub"))
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_create_announcement(self):
        self.make_user("amp_admin2", "Admin")
        client = Client()
        client.login(username="amp_admin2", password="pass12345")
        resp = client.post(reverse("save-announcement"), {
            "title": "New Notice", "body": "Body text", "priority": "important", "is_active": "on",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        self.assertTrue(Announcement.objects.filter(title="New Notice").exists())

    def test_manager_cannot_create_announcement(self):
        self.make_user("amp_mgr2", "Manager")
        client = Client()
        client.login(username="amp_mgr2", password="pass12345")
        resp = client.post(reverse("save-announcement"), {
            "title": "Should Fail", "body": "Body text", "priority": "normal", "is_active": "on",
        })
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Announcement.objects.filter(title="Should Fail").exists())

    def test_save_announcement_rejects_missing_title(self):
        self.make_user("amp_admin3", "Admin")
        client = Client()
        client.login(username="amp_admin3", password="pass12345")
        resp = client.post(reverse("save-announcement"), {
            "title": "", "body": "Body text", "priority": "normal", "is_active": "on",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])

    def test_admin_can_delete_announcement(self):
        self.make_user("amp_admin4", "Admin")
        a = Announcement.objects.create(title="Delete Me", body="B")
        client = Client()
        client.login(username="amp_admin4", password="pass12345")
        resp = client.post(reverse("delete-announcement", args=[a.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        self.assertFalse(Announcement.objects.filter(pk=a.pk).exists())

    def test_employee_cannot_delete_announcement(self):
        self.make_user("amp_emp2", "Employee")
        a = Announcement.objects.create(title="Keep Me", body="B")
        client = Client()
        client.login(username="amp_emp2", password="pass12345")
        resp = client.post(reverse("delete-announcement", args=[a.pk]))
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Announcement.objects.filter(pk=a.pk).exists())
