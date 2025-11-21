
# website/utils.py
from website.models import Attendance, LeaveBalance, PayrollSettings, CompOffRequest
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from django.db.models import Sum

def recalculate_all_leave_balances():
    """
    Re-run the leave balance calculation for ALL employees manually.
    This lets you test instantly without inserting new attendance/compoff.
    """

    today = date.today()

    all_leave_balances = LeaveBalance.objects.select_related("employee").all()

    for record in all_leave_balances:
        employee = record.employee

        # Payroll period
        payroll_settings = PayrollSettings.objects.filter(company=employee.company).first()
        if payroll_settings:
            full_from_date, full_to_date = payroll_settings.get_payroll_period()
        else:
            full_from_date = today.replace(day=1)
            full_to_date = (today.replace(day=1) + relativedelta(months=1)) - timedelta(days=1)

        # Attendance
        total_present_days = Decimal(
            Attendance.objects.filter(
                employee=employee,
                date__gte=full_from_date,
                date__lte=today
            ).aggregate(total_present=Sum("count"))["total_present"] or 0
        )

        total_late = Decimal(
            Attendance.objects.filter(
                employee=employee,
                date__gte=full_from_date,
                date__lte=today
            ).aggregate(total_late=Sum("late"))["total_late"] or 0
        )

        total_days_till_now = Decimal((today - full_from_date).days + 1)
        leave_taken_till_now = total_days_till_now - total_present_days

        opening_balance = Decimal(record.opening_balance or 0)

        # Compoff
        compoff_days = Decimal(0)
        for c in CompOffRequest.objects.filter(
            employee=employee, status="Approved",
            from_date__gte=full_from_date,
            to_date__lte=today
        ):
            compoff_days += Decimal((c.to_date - c.from_date).days + 1)

        # Formula
        closing_balance = opening_balance - leave_taken_till_now - total_late + compoff_days

        if closing_balance < 0:
            leave_without_pay = abs(closing_balance)
            leave_balance = Decimal(0)
        else:
            leave_without_pay = Decimal(0)
            leave_balance = closing_balance

        # Credit logic
        if total_present_days <= 15:
            monthly_credit = Decimal(0)
        elif 15 < total_present_days <= 25:
            monthly_credit = Decimal(1)
        else:
            monthly_credit = Decimal(2)

        final_leave_balance = leave_balance + monthly_credit

        # Save
        record.leave_taken = leave_taken_till_now
        record.number_of_days_present = total_present_days
        record.late = int(total_late)
        record.leave_without_pay = leave_without_pay
        record.closing_balance = closing_balance
        record.leave_balance = leave_balance
        record.final_leave_balance = final_leave_balance
        record.compoff = float(compoff_days)
        record.save()

    return True
