"""
A stale or missing CSRF token must not show a bare "Forbidden" page: forms
go back to the page with a "please try again" message, fetch calls get JSON.

Run with: python manage.py test website.tests.test_csrf_failure
"""
from django.conf import settings
from django.test import Client, TestCase
from django.urls import reverse


class CsrfFailureTest(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def test_hrms_uses_its_own_cookie_names(self):
        self.assertEqual(settings.CSRF_COOKIE_NAME, "hrms_csrftoken")
        self.assertEqual(settings.SESSION_COOKIE_NAME, "hrms_sessionid")
        resp = self.client.get(reverse("login"))
        self.assertIn("hrms_csrftoken", resp.cookies)

    def test_stale_login_form_goes_back_to_login_with_message(self):
        login = reverse("login")
        self.client.get(login)
        resp = self.client.post(
            login,
            {"username": "x", "password": "y", "csrfmiddlewaretoken": "stale" * 8},
            HTTP_REFERER="http://testserver" + login,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "http://testserver" + login)
        page = self.client.get(login)
        self.assertContains(page, "Your page had expired")

    def test_offsite_referer_is_ignored(self):
        resp = self.client.post(reverse("login"), {}, HTTP_REFERER="https://evil.example.com/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("login"))

    def test_employee_opening_site_address_lands_on_own_dashboard(self):
        from datetime import date
        from django.contrib.auth.models import Group, User
        from website.models import Company, Employee
        company = Company.objects.create(short_name="RT", name="Root Co", phone="1", email="r@t.com", address="A")
        user = User.objects.create_user(username="rootemp", password="pass12345")
        user.groups.add(Group.objects.get(name="Employee"))
        Employee.objects.create(company=company, user=user, first_name="R", last_name="E", employee_code="RT1",
                                date_of_joining=date(2020, 1, 1), status="Active", force_password_change=False)
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        resp = client.get("/")
        self.assertRedirects(resp, reverse("employee-dashboard"))

    def test_forbidden_page_is_friendly(self):
        from django.contrib.auth.models import User
        user = User.objects.create_user(username="bare", password="pass12345")
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        resp = client.get("/")
        self.assertEqual(resp.status_code, 403)
        self.assertContains(resp, "have access to this page", status_code=403)

    def test_fetch_call_gets_json_403(self):
        resp = self.client.post(reverse("login"), {}, HTTP_X_CSRFTOKEN="stale")
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(resp.json()["success"])
