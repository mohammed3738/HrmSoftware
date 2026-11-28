from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from website.models import CalendarEntry


class CalendarPlannerTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("planner")
        self.other = User.objects.create_user("other-planner")
        self.client.force_login(self.owner, backend="django.contrib.auth.backends.ModelBackend")
        self.url = reverse("calendar-entry-update")

    def test_entry_lifecycle_and_month_marker_data(self):
        response = self.client.post(self.url, {"action": "add", "kind": "task", "day": "2026-11-20", "text": "Review handover"})
        self.assertEqual(response.status_code, 302)
        entry = CalendarEntry.objects.get(owner=self.owner)
        month = reverse("holiday-calendar") + "?year=2026&month=11&day=20"
        self.assertContains(self.client.get(month), "Review handover")
        for action, done in [("complete", True), ("reopen", False)]:
            self.client.post(self.url, {"entry": entry.pk, "action": action})
            entry.refresh_from_db()
            self.assertEqual(entry.completed, done)
        self.client.post(self.url, {"entry": entry.pk, "action": "edit", "text": "Updated handover"})
        self.assertContains(self.client.get(month), "Updated handover")
        self.assertNotContains(self.client.get(reverse("holiday-calendar"), {"month": 12, "year": 2026}), "Updated handover")
        self.client.post(self.url, {"entry": entry.pk, "action": "remove"})
        self.assertFalse(CalendarEntry.objects.exists())

    def test_private_entries_are_scoped_to_owner_and_input_validated(self):
        entry = CalendarEntry.objects.create(owner=self.other, kind="note", day="2026-11-01", text="Private reminder")
        self.assertNotContains(self.client.get(reverse("holiday-calendar"), {"month": 11, "year": 2026}), "Private reminder")
        for action in ["edit", "remove", "complete"]:
            self.assertEqual(self.client.post(self.url, {"action": action, "entry": entry.pk, "text": "Changed"}).status_code, 404)
        self.assertEqual(self.client.post(self.url, {"action": "add", "kind": "task", "text": "Check", "day": "2026-02-30"}).status_code, 400)
