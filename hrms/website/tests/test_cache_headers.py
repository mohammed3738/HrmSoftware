"""Nothing this application generates may be stored by a cache.

The symptom that found this: on a hosted staging box, one 403 turned into
403 on every page until the cache was cleared. Nothing on the server
remembers a refusal -- the permission check is per user and per request,
and `has_feature_permission` caches only on the request's own user object
-- so a refusal that outlives the request can only have been *stored*
somewhere in front of Django.

It could be, because Django sends no Cache-Control header of its own.
Every response left this app with no instruction at all, and what happens
then is up to the browser's disk cache, an nginx `proxy_cache` or a CDN.
The same gap meant an employee's salary slip or KYC scan could be served
to whoever used that browser next.

So these tests assert the header on the responses that matter, including
the error responses -- a 403 is exactly the one that must not be replayed.

Run with: python manage.py test website.tests.test_cache_headers
"""
from datetime import date

from django.contrib.auth.models import User
from django.http import HttpResponse
from django.test import Client, RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from website.middleware import PrivateCacheControlMiddleware
from website.models import Company, Employee


class CacheControlOnRealPagesTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.company = Company.objects.create(
            short_name="CCH", name="Cache Headers Co", phone="1",
            email="cch@test.com", address="Addr",
        )
        self.employee = Employee.objects.create(
            company=self.company, salutation="Mr", first_name="Rahul",
            last_name="Kulkarni", father_name="Father", gender="Male",
            blood_group="O+", date_of_birth=date(1990, 1, 1), place_of_birth="Pune",
            personal_email="cch@example.test", present_address="Addr",
            permanent_address="Addr", personal_mobile="1234567890",
            employee_code="CCH001", designation="Operator", department="Production",
            date_of_joining=date(2020, 1, 1), location="Pune",
            pan_no="ABCDE1234F", aadhar_no="123456789012",
            name_as_per_bank="Rahul Kulkarni", salary_account_number="1234567890",
            ifsc_code="TEST0001234", emergency_contact_name1="Spouse",
            emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321", status="Active",
        )
        self.employee.force_password_change = False
        self.employee.save(update_fields=["force_password_change"])
        self.employee.user.set_password("KulkarniRahul")
        self.employee.user.save()
        self.client.login(username="CCH001", password="KulkarniRahul")

    def assertNotStored(self, response, where):
        directives = response.headers.get("Cache-Control", "")
        self.assertIn("no-store", directives, f"{where} may be stored by a cache")
        self.assertIn("private", directives, f"{where} may be stored by a shared cache")
        self.assertIn("Cookie", response.headers.get("Vary", ""),
                      f"{where} does not vary on the session cookie")

    # -- the one that caused the report ----------------------------------

    def test_a_403_must_not_be_storable(self):
        """A stored 403 is replayed to later requests, which is what made
        one refusal look like the whole site was forbidden."""
        response = self.client.get(reverse("employee_list"))
        self.assertEqual(response.status_code, 403,
                         "precondition: an Employee may not list employees")
        self.assertNotStored(response, "a 403")

    def test_the_403_on_the_root_url_must_not_be_storable(self):
        """`/` is the admin dashboard, which an Employee may not see. It is
        also where a browser goes when someone types the bare domain, so a
        stored 403 here looks like the whole application is down."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 403)
        self.assertNotStored(response, "the 403 on /")

    # -- and the pages that carry employee data --------------------------

    def test_a_signed_in_page_must_not_be_storable(self):
        response = self.client.get(reverse("employee-dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertNotStored(response, "the employee dashboard")

    def test_a_redirect_must_not_be_storable(self):
        """A stored redirect is the worst of them: the browser stops asking
        the server where to go at all."""
        response = self.client.get(reverse("my_profile"))
        self.assertEqual(response.status_code, 302)
        self.assertNotStored(response, "a redirect")

    def test_the_login_page_must_not_be_storable(self):
        anonymous = Client()
        response = anonymous.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers.get("Cache-Control", ""))


class PrivateCacheControlMiddlewareTest(SimpleTestCase):
    """The middleware's own edges, without needing a database."""

    def setUp(self):
        self.factory = RequestFactory()

    def run_middleware(self, path="/anything/", response=None):
        response = response if response is not None else HttpResponse("ok")
        middleware = PrivateCacheControlMiddleware(lambda request: response)
        return middleware(self.factory.get(path))

    def test_it_sets_the_header_when_there_is_none(self):
        self.assertIn("no-store", self.run_middleware().headers["Cache-Control"])

    def test_it_also_sets_the_http_1_0_headers(self):
        response = self.run_middleware()
        self.assertEqual(response.headers["Pragma"], "no-cache")
        self.assertEqual(response.headers["Expires"], "0")

    def test_a_view_that_sets_its_own_cache_control_is_left_alone(self):
        """Otherwise nothing could ever opt in to being cached again."""
        deliberate = HttpResponse("ok")
        deliberate["Cache-Control"] = "public, max-age=3600"
        response = self.run_middleware(response=deliberate)
        self.assertEqual(response.headers["Cache-Control"], "public, max-age=3600")

    def test_static_files_are_left_alone(self):
        """nginx serves /static/ in production with its own expiry; Django
        only sees these paths in development."""
        response = self.run_middleware(path="/static/js/password-rules.js")
        self.assertNotIn("Cache-Control", response.headers)

    def test_it_adds_cookie_to_an_existing_vary_rather_than_replacing_it(self):
        varied = HttpResponse("ok")
        varied["Vary"] = "Accept-Encoding"
        response = self.run_middleware(response=varied)
        vary = response.headers["Vary"]
        self.assertIn("Accept-Encoding", vary)
        self.assertIn("Cookie", vary)
