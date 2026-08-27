"""
Regression test: the Holiday Management page previously showed all 6 tabs
(Calendar View, Holidays List, Holiday Types, Earned Leaves, Half-Day
Scenarios, Settings) to every authenticated user, including a plain
Employee -- who should only see the Calendar View.

Run with: python manage.py test website.tests.test_holiday_dashboard_tab_visibility
"""
from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse


class HolidayDashboardTabVisibilityTest(TestCase):
    def setUp(self):
        self.employee_user = User.objects.create_user(username="hol_tab_emp", password="pass12345")
        self.employee_user.groups.add(Group.objects.get(name="Employee"))

        self.hr_user = User.objects.create_user(username="hol_tab_hr", password="pass12345")
        self.hr_user.groups.add(Group.objects.get(name="HR"))

    def _client_as(self, user):
        client = Client()
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        return client

    def _tab_markers(self, html):
        return {tab: f'data-tab="{tab}"' in html for tab in
                ("calendar", "holidays", "holiday-types", "earned", "halfday", "settings")}

    def test_employee_only_sees_calendar_tab(self):
        resp = self._client_as(self.employee_user).get(reverse("holiday-calendar"))
        self.assertEqual(resp.status_code, 200)
        markers = self._tab_markers(resp.content.decode("utf-8"))
        self.assertEqual(markers, {
            "calendar": True, "holidays": False, "holiday-types": False,
            "earned": False, "halfday": False, "settings": False,
        })

    def test_hr_sees_all_tabs(self):
        resp = self._client_as(self.hr_user).get(reverse("holiday-calendar"))
        self.assertEqual(resp.status_code, 200)
        markers = self._tab_markers(resp.content.decode("utf-8"))
        self.assertTrue(all(markers.values()))
