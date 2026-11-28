"""Informational calendar overlays, independent of company attendance rules."""
from collections import defaultdict
from datetime import date
from functools import lru_cache

from holidays.countries.india import India


# Fixed dates from https://www.un.org/en/observances/international-days-and-weeks
INTERNATIONAL_DAYS = {
    (1, 24): "International Day of Education", (2, 21): "International Mother Language Day",
    (3, 8): "International Women's Day", (3, 22): "World Water Day",
    (4, 7): "World Health Day", (4, 22): "International Mother Earth Day",
    (5, 15): "International Day of Families", (6, 5): "World Environment Day",
    (6, 21): "International Day of Yoga", (7, 30): "International Day of Friendship",
    (8, 12): "International Youth Day", (9, 8): "International Literacy Day",
    (9, 21): "International Day of Peace", (10, 5): "World Teachers' Day",
    (10, 24): "United Nations Day", (11, 20): "World Children's Day",
    (12, 3): "International Day of Persons with Disabilities", (12, 10): "Human Rights Day",
}


@lru_cache(maxsize=12)
def _year_observances(year):
    names = defaultdict(dict)
    if India.start_year <= year <= India.end_year:
        region_names = {}
        for name, code in India.subdivisions_aliases.items():
            if len(name) > 2:
                region_names.setdefault(code, name)
        for code in (None, *India.subdivisions):
            calendar = India(years=year, subdiv=code, categories=India.supported_categories,
                             language="en_IN", observed=False)
            for day in calendar:
                for title in calendar.get_list(day):
                    regions = names[day].setdefault(title, set())
                    regions.add(region_names.get(code, code))
    for (month, day), title in INTERNATIONAL_DAYS.items():
        names[date(year, month, day)][title] = {"International"}
    return {day: [{"name": name, "scope": "India" if None in regions else ", ".join(sorted(regions))}
                  for name, regions in sorted(entries.items())] for day, entries in sorted(names.items())}


def month_observances(year, month):
    return {day.isoformat(): events for day, events in _year_observances(year).items() if day.month == month}
