"""Date helpers shared by the payroll-period code.

Inert: no model or view imports, so website/models.py can import this
without a cycle.
"""
from calendar import monthrange
from datetime import date


def day_in_month(year, month, day):
    """A date in `year`/`month` on `day`, with `day` clamped to the last day
    the month actually has.

    PayrollSettings.from_date / to_date are bare day-of-month numbers
    (1-31). Building `date(year, month, day)` straight out of them raises
    `ValueError: day is out of range for month` for any cycle running to the
    29th, 30th or 31st as soon as February comes round -- which took out
    payroll run creation, the attendance register and leave-balance
    recalculation for those companies, as an unhandled 500.

    A day number past the end of a month means the end of that month, which
    is how a "1st to the 31st" cycle is read everywhere.
    """
    return date(year, month, min(day, monthrange(year, month)[1]))
