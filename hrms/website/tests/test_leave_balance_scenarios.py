"""
Leave balance end-to-end scenarios: opening balance = previous month's
final balance, and every way the numbers can change -- attendance edits,
status overrides (weekday, Sunday, holiday), deletes, comp-off requests,
approved leave, the LWP / Comp Off cell edits, the Recalculate button,
late marks, half days, the cap, the yearly reset, finalized payroll and
mid-month joiners. After each scenario the whole chain is checked against
the formula, so a month that silently went stale shows up.

Pay cycle 27th-26th with Sunday as the weekend, as on the live site.
No LeaveCreditPolicy unless a test adds one -> monthly credit is 1.

Run with: python manage.py test website.tests.test_leave_balance_scenarios
"""
from datetime import date, time, timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from website.models import (
    Attendance, Company, CompOffRequest, Employee, LeaveApplication, LeaveBalance,
    LeaveCreditPolicy, PayrollRun, PayrollSettings,
)
from website.signals import recalculate_leave_balance_for_employee, suspend_leave_balance_auto_recalc

JUN = (date(2026, 5, 27), date(2026, 6, 26))
JUL = (date(2026, 6, 27), date(2026, 7, 26))
AUG = (date(2026, 7, 27), date(2026, 8, 26))
SEP = (date(2026, 8, 27), date(2026, 9, 26))
D = Decimal

FIELDS = ("opening_balance", "leave_taken", "number_of_days_present", "late", "compoff",
          "leave_without_pay", "leave_balance", "closing_balance", "final_leave_balance",
          "lwp_overridden", "compoff_overridden")


def days(period):
    d, out = period[0], []
    while d <= period[1]:
        out.append(d)
        d += timedelta(days=1)
    return out


def weekdays(period):
    return [d for d in days(period) if d.weekday() != 6]


def sundays(period):
    return [d for d in days(period) if d.weekday() == 6]


class LeaveBalanceScenarioBase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(short_name="LBS", name="Leave Co", phone="1", email="l@t.com", address="A")
        self.ps = PayrollSettings.objects.create(company=self.company, from_date=27, to_date=26, weekend_days="sun")
        self.emp = Employee.objects.create(company=self.company, first_name="Vai", last_name="J", employee_code="LBS1",
                                           date_of_joining=date(2020, 1, 1), status="Active")
        admin = User.objects.create_user(username="lbs_admin", password="pass12345")
        admin.groups.add(Group.objects.get(name="Admin"))
        self.client = Client()
        self.client.force_login(admin, backend="django.contrib.auth.backends.ModelBackend")

    # ── building attendance ──────────────────────────────────────────
    def fill(self, period, absent=(), late=(), half=(), emp=None):
        """A row for every working day: present 9-18 unless the date is in
        absent (no punch), late (9-16: Late Present) or half (9-14)."""
        emp = emp or self.emp
        with suspend_leave_balance_auto_recalc():
            for d in weekdays(period):
                if emp.date_of_joining and d < emp.date_of_joining:
                    continue
                if d in absent:
                    times = (None, None)
                elif d in late:
                    times = (time(9), time(16))
                elif d in half:
                    times = (time(9), time(14))
                else:
                    times = (time(9), time(18))
                Attendance.objects.create(employee=emp, date=d, in_time=times[0], out_time=times[1])
        recalculate_leave_balance_for_employee(emp, period[0])

    def lb(self, period, emp=None):
        return LeaveBalance.objects.get(employee=emp or self.emp, period_from_date=period[0], period_to_date=period[1])

    def snapshot(self):
        return {(lb.period_from_date,): tuple(getattr(lb, f) for f in FIELDS)
                for lb in LeaveBalance.objects.filter(employee=self.emp)}

    def row(self, d):
        return Attendance.objects.get(employee=self.emp, date=d)

    # ── endpoints the screens use ────────────────────────────────────
    def override_status(self, d, status):
        resp = self.client.post(reverse("override_attendance_status"),
                                {"employee_id": self.emp.id, "date": d.isoformat(), "new_status": status})
        return resp

    def override_lwp(self, period, value):
        return self.client.post(reverse("override-lwp"), {"lb_id": self.lb(period).id, "lwp_value": str(value)})

    def override_compoff(self, period, value):
        return self.client.post(reverse("override-compoff"), {"lb_id": self.lb(period).id, "compoff_value": str(value)})

    def press_recalculate(self):
        resp = self.client.post(reverse("recalculate_leave_balances"), {"company_id": self.company.id})
        self.assertTrue(resp.json()["success"], resp.json())

    # ── the formula, checked on every month ──────────────────────────
    def assert_consistent(self, emp=None):
        emp = emp or self.emp
        ps = PayrollSettings.objects.get(company=self.company)
        rows = list(LeaveBalance.objects.filter(employee=emp).order_by("period_from_date"))
        self.assertTrue(rows, "no leave balance rows")
        prev = None
        for lb in rows:
            label = f"{emp.employee_code} {lb.period_from_date}..{lb.period_to_date}"
            late_days = D((lb.late - 5) // 3) if (lb.late > 5 and ps.late_marks_affect_lwp) else D(0)
            before = lb.opening_balance + lb.compoff - lb.leave_taken - late_days
            if lb.lwp_overridden:
                self.assertEqual(lb.leave_balance, max(D(0), before - lb.leave_without_pay), label)
            else:
                self.assertEqual(lb.leave_balance, max(D(0), before), label)
                self.assertEqual(lb.leave_without_pay, max(D(0), -before), label)
            credit = lb.closing_balance - lb.leave_balance
            self.assertIn(credit, (D(0), D(1), D(2)), label)
            self.assertEqual(lb.final_leave_balance, min(lb.closing_balance, D(ps.max_leave_balance)), label)
            if prev is not None:
                reset = (not ps.carry_forward) and ps.reset_month == lb.period_to_date.month
                expected_open = D(0) if reset else prev.final_leave_balance
                self.assertEqual(lb.opening_balance, expected_open,
                                 f"{label}: opening {lb.opening_balance} but previous month closed at "
                                 f"{prev.final_leave_balance}")
            prev = lb
        out = StringIO()
        call_command("check_leave_chain", stdout=out)
        self.assertIn("0 employee(s)", out.getvalue(), out.getvalue())


class OpeningBalanceChainTest(LeaveBalanceScenarioBase):
    def test_full_attendance_builds_up_one_a_month(self):
        for p in (JUN, JUL, AUG):
            self.fill(p)
        self.assertEqual([self.lb(p).opening_balance for p in (JUN, JUL, AUG)], [0, 1, 2])
        self.assertEqual([self.lb(p).final_leave_balance for p in (JUN, JUL, AUG)], [1, 2, 3])
        for p in (JUN, JUL, AUG):
            self.assertEqual(self.lb(p).leave_taken, 0)
            self.assertEqual(self.lb(p).leave_without_pay, 0)
            self.assertEqual(self.lb(p).number_of_days_present, len(days(p)))
        self.assertEqual(self.lb(JUN).total_number_of_days, 31)
        self.assertEqual(self.lb(JUL).total_number_of_days, 30)
        self.assertEqual(self.lb(AUG).total_number_of_days, 31)
        self.assertEqual(self.lb(AUG).late, 0)
        self.assert_consistent()

    def test_months_filled_out_of_order_still_chain(self):
        """August uploaded before July: once July arrives, August's opening
        must move to July's closing."""
        self.fill(JUN)
        self.fill(AUG)
        self.fill(JUL)
        self.assertEqual(self.lb(AUG).opening_balance, self.lb(JUL).final_leave_balance)
        self.assert_consistent()

    def test_absences_spend_balance_then_become_lwp(self):
        self.fill(JUN)                                   # closes at 1
        self.fill(JUL, absent=weekdays(JUL)[:3])         # 3 absent, only 1 in hand
        jul = self.lb(JUL)
        self.assertEqual((jul.opening_balance, jul.leave_taken), (1, 3))
        self.assertEqual((jul.leave_without_pay, jul.leave_balance), (2, 0))
        self.assertEqual(jul.final_leave_balance, 1)     # this month's credit
        self.assertEqual(jul.number_of_days_present, len(days(JUL)) - 3)
        self.fill(AUG)
        self.assertEqual(self.lb(AUG).opening_balance, 1)
        self.assert_consistent()

    def test_half_day_takes_half(self):
        self.fill(JUN)
        self.fill(JUL, half=weekdays(JUL)[:1])
        jul = self.lb(JUL)
        self.assertEqual(jul.leave_taken, D("0.5"))
        self.assertEqual(jul.leave_balance, D("0.5"))
        self.assertEqual(jul.final_leave_balance, D("1.5"))
        self.assert_consistent()

    def test_holiday_is_not_leave(self):
        from website.models import Holiday, HolidayType
        hol = weekdays(JUL)[4]
        author = User.objects.get(username="lbs_admin")
        Holiday.objects.create(holiday_date=hol, name="Fest", status="declared", is_national=True, created_by=author,
                               holiday_type=HolidayType.objects.create(name="National", type_category="national"))
        self.fill(JUN)
        self.fill(JUL, absent=[hol])   # no punch on the holiday
        self.assertTrue(self.row(hol).is_holiday)
        jul = self.lb(JUL)
        self.assertEqual(jul.leave_taken, 0)
        self.assertEqual(jul.number_of_days_present, len(days(JUL)) - 1)  # holiday isn't a present day
        self.assertEqual(jul.final_leave_balance, 2)
        self.assert_consistent()


class LateMarksTest(LeaveBalanceScenarioBase):
    def test_first_five_late_marks_are_free(self):
        self.fill(JUN)
        self.fill(JUL, late=weekdays(JUL)[:5])
        jul = self.lb(JUL)
        self.assertEqual(jul.late, 5)
        self.assertEqual(jul.leave_balance, 1)
        self.assert_consistent()

    def test_every_three_after_five_costs_a_day(self):
        self.fill(JUN)
        self.fill(JUL, late=weekdays(JUL)[:8])   # (8-5)//3 = 1
        jul = self.lb(JUL)
        self.assertEqual(jul.late, 8)
        self.assertEqual(jul.leave_taken, 0)     # late present is still a paid day
        self.assertEqual(jul.leave_balance, 0)
        self.assert_consistent()

    def test_late_marks_ignored_when_setting_off(self):
        PayrollSettings.objects.filter(pk=self.ps.pk).update(late_marks_affect_lwp=False)
        self.fill(JUN)
        self.fill(JUL, late=weekdays(JUL)[:11])
        self.assertEqual(self.lb(JUL).leave_balance, 1)
        self.assert_consistent()


class ManualAttendanceChangesTest(LeaveBalanceScenarioBase):
    """Changing an OLD month must ripple into every later month's opening."""

    def setUp(self):
        super().setUp()
        self.absent_days = weekdays(JUN)[:2]
        self.fill(JUN, absent=self.absent_days)  # 2 taken, 0 in hand -> LWP 2, closes 1
        self.fill(JUL)
        self.fill(AUG)
        self.before = {p: self.lb(p).final_leave_balance for p in (JUN, JUL, AUG)}

    def test_baseline(self):
        self.assertEqual(self.lb(JUN).leave_without_pay, 2)
        self.assertEqual(self.before, {JUN: 1, JUL: 2, AUG: 3})
        self.assert_consistent()

    def test_override_absent_to_present_in_old_month(self):
        resp = self.override_status(self.absent_days[0], "Present")
        self.assertTrue(resp.json()["success"], resp.content)
        jun = self.lb(JUN)
        self.assertEqual((jun.leave_taken, jun.leave_without_pay), (1, 1))
        self.assertEqual(jun.final_leave_balance, 1)
        self.assert_consistent()

    def test_override_present_to_absent_ripples_forward(self):
        """JUL has 1 in hand; an extra absence uses it, so JUL and AUG
        each close one lower than before."""
        resp = self.override_status(weekdays(JUL)[3], "Absent")
        self.assertTrue(resp.json()["success"], resp.content)
        self.assertEqual(self.lb(JUL).final_leave_balance, self.before[JUL] - 1)
        self.assertEqual(self.lb(AUG).opening_balance, self.before[JUL] - 1)
        self.assertEqual(self.lb(AUG).final_leave_balance, self.before[AUG] - 1)
        self.assert_consistent()

    def test_override_to_half_day(self):
        self.override_status(weekdays(JUL)[3], "Half Day")
        self.assertEqual(self.lb(JUL).leave_taken, D("0.5"))
        self.assertEqual(self.lb(AUG).final_leave_balance, self.before[AUG] - D("0.5"))
        self.assert_consistent()

    def test_override_absent_to_holiday(self):
        self.override_status(self.absent_days[0], "Holiday")
        self.assertEqual(self.lb(JUN).leave_taken, 1)
        self.assert_consistent()

    def test_sunday_overridden_absent_costs_a_day_and_revert_restores(self):
        sunday = sundays(JUL)[0]
        resp = self.override_status(sunday, "Absent")
        self.assertTrue(resp.json()["success"], resp.content)
        jul = self.lb(JUL)
        self.assertEqual(jul.leave_taken, 1)
        self.assertEqual(jul.number_of_days_present, len(days(JUL)) - 1)
        self.assertEqual(self.lb(AUG).opening_balance, self.before[JUL] - 1)
        self.assert_consistent()

        self.override_status(sunday, "Late Present")   # "clear override"
        self.assertEqual(self.lb(JUL).leave_taken, 0)
        self.assertEqual(self.lb(AUG).final_leave_balance, self.before[AUG])
        self.assert_consistent()

    def test_sunday_overridden_present_changes_nothing(self):
        self.override_status(sundays(JUL)[0], "Present")
        self.assertEqual(self.lb(JUL).leave_taken, 0)
        self.assertEqual(self.lb(JUL).number_of_days_present, len(days(JUL)))
        self.assert_consistent()

    def test_excel_style_time_correction(self):
        """An upload / correction setting punch times on an absent row."""
        row = self.row(self.absent_days[0])
        row.in_time, row.out_time = time(9), time(18)
        row.save()
        self.assertEqual(self.lb(JUN).leave_taken, 1)
        self.assert_consistent()

    def test_deleting_an_absent_row(self):
        self.row(self.absent_days[0]).delete()
        self.assertEqual(self.lb(JUN).leave_taken, 1)
        self.assert_consistent()

    def test_deleting_whole_old_month(self):
        Attendance.objects.filter(employee=self.emp, date__range=JUN).delete()
        self.assert_consistent()


class LwpAndCompOffEditsTest(LeaveBalanceScenarioBase):
    def setUp(self):
        super().setUp()
        self.fill(JUN)
        self.fill(JUL, absent=weekdays(JUL)[:1])
        self.fill(AUG)

    def test_lwp_edit_carries_forward(self):
        resp = self.override_lwp(JUL, 2)
        self.assertTrue(resp.json()["success"], resp.content)
        jul = self.lb(JUL)
        self.assertTrue(jul.lwp_overridden)
        self.assertEqual(jul.leave_without_pay, 2)
        self.assertEqual(self.lb(AUG).opening_balance, jul.final_leave_balance)
        self.assert_consistent()

    def test_compoff_edit_carries_forward_and_can_clear_lwp(self):
        self.fill(SEP, absent=weekdays(SEP)[:5])  # SEP: opening 2, 5 taken -> LWP 3
        self.assertEqual(self.lb(SEP).leave_without_pay, 3)
        resp = self.override_compoff(SEP, 3)
        self.assertTrue(resp.json()["success"], resp.content)
        sep = self.lb(SEP)
        self.assertEqual((sep.compoff, sep.leave_without_pay), (3, 0))
        self.assert_consistent()

    def test_edits_survive_a_change_in_an_earlier_month(self):
        self.override_lwp(JUL, 2)
        self.override_compoff(AUG, 1)
        self.override_status(weekdays(JUN)[2], "Absent")   # older month moves
        jul, aug = self.lb(JUL), self.lb(AUG)
        self.assertEqual((jul.leave_without_pay, jul.lwp_overridden), (2, True))
        self.assertEqual((aug.compoff, aug.compoff_overridden), (1, True))
        self.assert_consistent()

    def test_edits_survive_a_change_in_the_same_month(self):
        self.override_lwp(JUL, 2)
        self.override_status(weekdays(JUL)[5], "Absent")
        jul = self.lb(JUL)
        self.assertEqual((jul.leave_without_pay, jul.leave_taken), (2, 2))
        self.assert_consistent()

    def test_recalculate_button_keeps_edits_and_changes_nothing(self):
        self.override_lwp(JUL, 2)
        self.override_compoff(AUG, D("1.5"))
        before = self.snapshot()
        self.press_recalculate()
        self.assertEqual(self.snapshot(), before)
        self.press_recalculate()
        self.assertEqual(self.snapshot(), before)
        self.assert_consistent()

    def test_negative_values_refused(self):
        self.assertEqual(self.override_lwp(JUL, -1).status_code, 400)
        self.assertEqual(self.override_compoff(JUL, -1).status_code, 400)
        self.assertFalse(self.lb(JUL).lwp_overridden)


class RecalculateButtonOrderTest(LeaveBalanceScenarioBase):
    """The Recalculate buttons walked the months newest-first, so each
    month opened with the previous month's OLD closing balance -- the
    "July closed at 4 but August opened at 3" report."""

    def setUp(self):
        super().setUp()
        for p in (JUN, JUL, AUG, SEP):
            self.fill(p)
        # Stale numbers, as left by an older bug or a direct DB edit.
        LeaveBalance.objects.filter(employee=self.emp).update(
            opening_balance=7, leave_balance=7, closing_balance=8, final_leave_balance=8)

    def test_company_recalculate_button(self):
        self.press_recalculate()
        self.assertEqual([self.lb(p).final_leave_balance for p in (JUN, JUL, AUG, SEP)], [1, 2, 3, 4])
        self.assert_consistent()

    def test_all_companies_recalculate_button(self):
        resp = self.client.post(reverse("recalculate_leave_balances"))
        self.assertTrue(resp.json()["success"])
        self.assert_consistent()

    def test_single_employee_recalculate(self):
        self.client.get(reverse("recalc-employee-leave", args=[self.emp.id]))
        self.assert_consistent()

    def test_single_employee_recalculate_leaves_finalized_month(self):
        PayrollRun.objects.create(company=self.company, month=date(2026, 6, 1), start_date=JUN[0], end_date=JUN[1],
                                  status=PayrollRun.STATUS_FINALIZED)
        self.client.get(reverse("recalc-employee-leave", args=[self.emp.id]))
        self.assertEqual(self.lb(JUN).final_leave_balance, 8)     # as paid
        self.assertEqual(self.lb(JUL).opening_balance, 8)


class CompOffRequestsTest(LeaveBalanceScenarioBase):
    def setUp(self):
        super().setUp()
        self.fill(JUN)
        self.fill(JUL, absent=weekdays(JUL)[:3])   # 1 in hand, 3 taken -> LWP 2
        self.fill(AUG)

    def _req(self, status):
        """A 2-day comp off (the count comes from the dates)."""
        d = weekdays(JUL)[10]
        return CompOffRequest.objects.create(employee=self.emp, from_date=d, to_date=d + timedelta(days=1),
                                             status=status)

    def test_half_day_request_counts_half(self):
        d = weekdays(JUL)[10]
        CompOffRequest.objects.create(employee=self.emp, from_date=d, to_date=d, is_half_day=True, status="Approved")
        self.assertEqual(self.lb(JUL).compoff, D("0.5"))
        self.assert_consistent()

    def test_approved_request_counts_and_carries_forward(self):
        req = self._req("Approved")
        jul = self.lb(JUL)
        self.assertEqual((jul.compoff, jul.leave_without_pay), (2, 0))
        self.assert_consistent()
        req.delete()
        jul = self.lb(JUL)
        self.assertEqual((jul.compoff, jul.leave_without_pay), (0, 2))
        self.assert_consistent()

    def test_pending_or_rejected_request_ignored(self):
        self._req("Pending")
        self._req("Rejected")
        self.assertEqual(self.lb(JUL).compoff, 0)
        self.assert_consistent()

    def test_approving_a_pending_request_counts(self):
        req = self._req("Pending")
        req.status = "Approved"
        req.save()
        self.assertEqual(self.lb(JUL).compoff, 2)
        self.assert_consistent()


class ApprovedLeaveTest(LeaveBalanceScenarioBase):
    """Leave approved for days that have no attendance row yet."""

    def setUp(self):
        super().setUp()
        self.fill(JUN)
        self.leave_days = weekdays(JUL)[-2:]
        self.fill(JUL)
        Attendance.objects.filter(employee=self.emp, date__in=self.leave_days).delete()
        self.fill(AUG)

    def _leave(self, status="Approved"):
        return LeaveApplication.objects.create(employee=self.emp, start_date=self.leave_days[0],
                                               end_date=self.leave_days[-1], status=status, reason="x")

    def test_approved_leave_reflects_immediately(self):
        self._leave()
        self.assertEqual(self.lb(JUL).leave_taken, 2)
        self.assertEqual(self.lb(AUG).opening_balance, self.lb(JUL).final_leave_balance)
        self.assert_consistent()

    def test_approving_pending_leave_reflects_immediately(self):
        leave = self._leave("Pending")
        self.assertEqual(self.lb(JUL).leave_taken, 0)
        leave.status = "Approved"
        leave.save()
        self.assertEqual(self.lb(JUL).leave_taken, 2)
        self.assert_consistent()

    def test_cancelling_approved_leave_gives_it_back(self):
        leave = self._leave()
        leave.status = "Rejected"
        leave.save()
        self.assertEqual(self.lb(JUL).leave_taken, 0)
        self._leave().delete()
        self.assertEqual(self.lb(JUL).leave_taken, 0)
        self.assert_consistent()

    def test_recalculate_button_counts_it(self):
        self._leave()
        self.press_recalculate()
        self.assertEqual(self.lb(JUL).leave_taken, 2)
        self.assert_consistent()


class SettingsTest(LeaveBalanceScenarioBase):
    def test_max_balance_cap(self):
        PayrollSettings.objects.filter(pk=self.ps.pk).update(max_leave_balance=2)
        for p in (JUN, JUL, AUG, SEP):
            self.fill(p)
        self.assertEqual([self.lb(p).final_leave_balance for p in (JUN, JUL, AUG, SEP)], [1, 2, 2, 2])
        self.assertEqual(self.lb(SEP).opening_balance, 2)
        self.assert_consistent()

    def test_reset_month_without_carry_forward(self):
        PayrollSettings.objects.filter(pk=self.ps.pk).update(carry_forward=False, reset_month=7)
        for p in (JUN, JUL, AUG):
            self.fill(p)
        self.assertEqual(self.lb(JUL).opening_balance, 0)    # July period ends 26 Jul
        self.assertEqual(self.lb(AUG).opening_balance, self.lb(JUL).final_leave_balance)
        self.assert_consistent()

    def test_carry_forward_on_ignores_reset_month(self):
        PayrollSettings.objects.filter(pk=self.ps.pk).update(carry_forward=True, reset_month=7)
        for p in (JUN, JUL):
            self.fill(p)
        self.assertEqual(self.lb(JUL).opening_balance, 1)

    def test_credit_policy_by_days_present(self):
        LeaveCreditPolicy.objects.create(company=self.company)   # <=15:0  <=25:1  else 2
        self.fill(JUN)                                            # 31 present -> 2
        self.fill(JUL, absent=weekdays(JUL)[:8])                  # 22 present -> 1
        self.fill(AUG, absent=weekdays(AUG)[:17])                 # 14 present -> 0
        credits = [self.lb(p).closing_balance - self.lb(p).leave_balance for p in (JUN, JUL, AUG)]
        self.assertEqual(credits, [2, 1, 0])
        self.assert_consistent()

    def test_credit_capped_by_yearly_entitlement(self):
        LeaveCreditPolicy.objects.create(company=self.company)
        PayrollSettings.objects.filter(pk=self.ps.pk).update(earned_leaves_per_year=12)   # 1 a month
        self.fill(JUN)
        self.assertEqual(self.lb(JUN).closing_balance, 1)


class FinalizedPayrollTest(LeaveBalanceScenarioBase):
    def setUp(self):
        super().setUp()
        self.fill(JUN, absent=weekdays(JUN)[:1])
        self.fill(JUL)
        PayrollRun.objects.create(company=self.company, month=date(2026, 6, 1), start_date=JUN[0], end_date=JUN[1],
                                  status=PayrollRun.STATUS_FINALIZED)
        self.jun = tuple(getattr(self.lb(JUN), f) for f in FIELDS)

    def _jun_unchanged(self):
        self.assertEqual(tuple(getattr(self.lb(JUN), f) for f in FIELDS), self.jun)

    def test_finalized_month_cannot_be_edited(self):
        self.assertFalse(self.override_status(weekdays(JUN)[0], "Present").json()["success"])
        self.assertFalse(self.override_lwp(JUN, 5).json().get("success", False))
        self.assertFalse(self.override_compoff(JUN, 5).json().get("success", False))
        self._jun_unchanged()

    def test_later_month_still_opens_with_finalized_close(self):
        self.override_status(weekdays(JUL)[0], "Absent")
        self.press_recalculate()
        self._jun_unchanged()
        self.assertEqual(self.lb(JUL).opening_balance, self.lb(JUN).final_leave_balance)
        self.assert_consistent()


class JoinerTest(LeaveBalanceScenarioBase):
    def test_no_balance_before_joining(self):
        newbie = Employee.objects.create(company=self.company, first_name="New", last_name="B", employee_code="LBS2",
                                         date_of_joining=JUL[0] + timedelta(days=10), status="Active")
        self.fill(JUN)                    # company has June attendance
        self.fill(JUL, emp=newbie)
        self.fill(AUG, emp=newbie)
        self.assertFalse(LeaveBalance.objects.filter(employee=newbie, period_from_date=JUN[0]).exists())
        jul = self.lb(JUL, newbie)
        self.assertEqual(jul.opening_balance, 0)
        self.assertEqual(jul.leave_taken, 10)     # the 10 days before joining
        self.assertEqual(self.lb(AUG, newbie).opening_balance, jul.final_leave_balance)
        self.assert_consistent(newbie)


class DayStartPlaceholdersTest(LeaveBalanceScenarioBase):
    """The start-of-day Absent rows: they count as absent until a punch
    arrives, and the punch gives the day back."""

    def test_placeholder_then_punch(self):
        from website.services.biometric_sync import mark_day_start
        self.fill(JUN)
        self.fill(JUL)
        day = weekdays(AUG)[0]
        mark_day_start(day)
        self.assertEqual(self.lb(AUG).leave_taken, 1)
        row = self.row(day)
        row.in_time, row.out_time = time(9), time(18)
        row.save()
        self.assertEqual(self.lb(AUG).leave_taken, 0)
        self.assert_consistent()
