from datetime import date

from django.test import SimpleTestCase

from website.calendar_observances import month_observances


class ObservanceCalendarTests(SimpleTestCase):
    def test_festivals_follow_year_and_region(self):
        nov = month_observances(2026, 11)
        names = {event["name"] for event in nov["2026-11-08"]}
        self.assertIn("Diwali (Deepavali)", names)
        self.assertTrue(any("Jayanti" in e["name"] for e in nov["2026-11-24"]))
        self.assertIn({"name": "Kali Puja", "scope": "West Bengal"}, nov["2026-11-08"])
        next_year = month_observances(2027, 10)
        self.assertIn("Diwali (Deepavali)", [e["name"] for e in next_year["2027-10-29"]])

    def test_fixed_observances_and_month_boundaries(self):
        events = month_observances(2026, 6)
        self.assertIn({"name": "World Environment Day", "scope": "International"}, events["2026-06-05"])
        self.assertTrue(all(date.fromisoformat(day).month == 6 for day in events))
