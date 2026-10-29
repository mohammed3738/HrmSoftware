"""
Regression tests for payroll-cycle day numbers that do not exist in every
month.

PayrollSettings.from_date / to_date are plain day-of-month integers (1-31).
Three separate places built a date straight out of them:

  * views._compute_payroll_dates        -> date(year, m, from_day/to_day)
  * views.get_payroll_period_for_date   -> six such calls
  * PayrollSettings.get_payroll_period  -> date(start_year, start_month, from_day)

None clamped the day to the month's length, so a company whose cycle runs to
the 29th, 30th or 31st raised

    ValueError: day is out of range for month

the moment any of them was asked about February -- creating a February
payroll run, opening the attendance register for February, or recalculating
February leave balances. ValueError is not caught anywhere on those paths,
so it surfaced as a 500.

A day number past the end of a month means the end of that month, which is
how a "1st to the 31st" cycle is universally read. February 2026 has 28
days and February 2024 (a leap year) has 29, and both are asserted from
those independently-known lengths rather than from calendar.monthrange, so
the test does not restate the implementation.

Run with:
    python manage.py test website.tests.test_payroll_period_short_months
"""
from datetime import date

from django.test import TestCase

from website.models import Company, PayrollSettings
from website.views import _compute_payroll_dates, get_payroll_period_for_date


class ComputePayrollDatesShortMonthTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="PPS", name="Period Co", phone="1",
            email="pps@test.com", address="Addr",
        )

    def _settings(self, from_day, to_day):
        return PayrollSettings.objects.create(
            company=self.company, from_date=from_day, to_date=to_day,
        )

    def test_same_month_cycle_ending_on_the_31st_in_february(self):
        ps = self._settings(1, 31)
        start, end = _compute_payroll_dates(ps, 2026, 2)
        self.assertEqual(start, date(2026, 2, 1))
        self.assertEqual(end, date(2026, 2, 28))

    def test_same_month_cycle_ending_on_the_31st_in_a_leap_february(self):
        ps = self._settings(1, 31)
        start, end = _compute_payroll_dates(ps, 2024, 2)
        self.assertEqual(start, date(2024, 2, 1))
        self.assertEqual(end, date(2024, 2, 29))

    def test_same_month_cycle_ending_on_the_31st_in_a_30_day_month(self):
        ps = self._settings(1, 31)
        start, end = _compute_payroll_dates(ps, 2026, 4)
        self.assertEqual(start, date(2026, 4, 1))
        self.assertEqual(end, date(2026, 4, 30))

    def test_month_with_31_days_is_unaffected(self):
        ps = self._settings(1, 31)
        start, end = _compute_payroll_dates(ps, 2026, 1)
        self.assertEqual(start, date(2026, 1, 1))
        self.assertEqual(end, date(2026, 1, 31))

    def test_cross_month_cycle_starting_on_the_31st(self):
        """A 31 -> 30 cycle for March 2026: the start falls in February,
        which has no 31st, so it clamps to 28 Feb."""
        ps = self._settings(31, 30)
        start, end = _compute_payroll_dates(ps, 2026, 3)
        self.assertEqual(start, date(2026, 2, 28))
        self.assertEqual(end, date(2026, 3, 30))

    def test_ordinary_cross_month_cycle_is_unaffected(self):
        ps = self._settings(27, 26)
        start, end = _compute_payroll_dates(ps, 2026, 3)
        self.assertEqual(start, date(2026, 2, 27))
        self.assertEqual(end, date(2026, 3, 26))

    def test_calendar_month_fallback_when_no_day_numbers_are_set(self):
        ps = PayrollSettings.objects.create(company=self.company)
        start, end = _compute_payroll_dates(ps, 2026, 2)
        self.assertEqual(start, date(2026, 2, 1))
        self.assertEqual(end, date(2026, 2, 28))


class GetPayrollPeriodForDateShortMonthTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            short_name="PP2", name="Period Co 2", phone="1",
            email="pp2@test.com", address="Addr",
        )

    def _settings(self, from_day, to_day):
        return PayrollSettings.objects.create(
            company=self.company, from_date=from_day, to_date=to_day,
        )

    def test_same_month_cycle_to_the_31st_for_a_february_date(self):
        ps = self._settings(1, 31)
        start, end = get_payroll_period_for_date(ps, date(2026, 2, 14))
        self.assertEqual(start, date(2026, 2, 1))
        self.assertEqual(end, date(2026, 2, 28))

    def test_same_month_cycle_falling_back_to_a_short_previous_month(self):
        """from_day 15, to_day 31: 3 March is before the 15th, so the
        period is the previous month's -- February, with no 31st."""
        ps = self._settings(15, 31)
        start, end = get_payroll_period_for_date(ps, date(2026, 3, 3))
        self.assertEqual(start, date(2026, 2, 15))
        self.assertEqual(end, date(2026, 2, 28))

    def test_cross_month_cycle_ending_in_a_short_month(self):
        """from_day 30, to_day 29: 31 January is on/after the 30th, so the
        period ends on the 29th of February."""
        ps = self._settings(30, 29)
        start, end = get_payroll_period_for_date(ps, date(2026, 1, 31))
        self.assertEqual(start, date(2026, 1, 30))
        self.assertEqual(end, date(2026, 2, 28))

    def test_cross_month_cycle_starting_in_a_short_month(self):
        """from_day 30, to_day 29: 10 March is before the 30th, so the
        period started on February's 30th, which does not exist."""
        ps = self._settings(30, 29)
        start, end = get_payroll_period_for_date(ps, date(2026, 3, 10))
        self.assertEqual(start, date(2026, 2, 28))
        self.assertEqual(end, date(2026, 3, 29))

    def test_ordinary_cycle_is_unaffected(self):
        ps = self._settings(27, 26)
        start, end = get_payroll_period_for_date(ps, date(2026, 3, 10))
        self.assertEqual(start, date(2026, 2, 27))
        self.assertEqual(end, date(2026, 3, 26))


class PayrollSettingsGetPayrollPeriodShortMonthTest(TestCase):
    """get_payroll_period() reads today's date, so it is exercised through
    a frozen 'today' rather than by waiting for February."""

    def setUp(self):
        self.company = Company.objects.create(
            short_name="PP3", name="Period Co 3", phone="1",
            email="pp3@test.com", address="Addr",
        )

    def test_cycle_to_the_31st_does_not_raise_in_february(self):
        import website.models as models_module

        ps = PayrollSettings.objects.create(
            company=self.company, from_date=1, to_date=31,
        )

        class FrozenDate(models_module.date):
            @classmethod
            def today(cls):
                return models_module.date(2026, 2, 14)

        original = models_module.date
        models_module.date = FrozenDate
        try:
            start, end = ps.get_payroll_period()
        finally:
            models_module.date = original

        self.assertEqual(start, date(2026, 2, 1))
        self.assertEqual(end, date(2026, 2, 28))
