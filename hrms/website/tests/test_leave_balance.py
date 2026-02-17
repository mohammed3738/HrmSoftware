from decimal import Decimal
from datetime import date, timedelta
from website.services.leave_balance_service import calculate_leave_balance
from website.models import LeaveBalance
from .utils import create_attendance
from freezegun import freeze_time

@freeze_time("2024-02-15")
def test_full_present_month(employee, payroll_settings, leave_policy):
    start = date(2024, 1, 26)

    for i in range(22):
        create_attendance(employee, start + timedelta(days=i), 1)

    result = calculate_leave_balance(employee, payroll_settings)
    lb = LeaveBalance.objects.last()

    assert lb.opening_balance == Decimal("0.00")
    assert lb.leave_taken == Decimal("0.00")
    assert lb.late == 0
    assert lb.leave_balance == Decimal("0.00")
    assert lb.final_leave_balance == Decimal("2.00")  # credit_high


@freeze_time("2024-02-15")
def test_half_day_and_absent(employee, payroll_settings, leave_policy):
    start = date(2024, 1, 26)

    for i in range(18):
        create_attendance(employee, start + timedelta(days=i), 1)

    for i in range(18, 20):
        create_attendance(employee, start + timedelta(days=i), 0.5)

    for i in range(20, 22):
        create_attendance(employee, start + timedelta(days=i), 0)

    result = calculate_leave_balance(employee, payroll_settings)
    lb = LeaveBalance.objects.last()

    assert lb.number_of_days_present == Decimal("19.00")
    assert lb.leave_taken == Decimal("3.00")
    assert lb.final_leave_balance == Decimal("1.00")  # mid credit

@freeze_time("2024-02-15")
def test_late_penalty(employee, payroll_settings, leave_policy):
    start = date(2024, 1, 26)

    for i in range(20):
        create_attendance(employee, start + timedelta(days=i), 1, late=1)

    calculate_leave_balance(employee, payroll_settings)
    lb = LeaveBalance.objects.last()

    assert lb.late == 20
    assert lb.leave_balance == Decimal("0.00")  # negative → zero


from website.models import CompOffRequest
@freeze_time("2024-02-15")
def test_compoff_addition(employee, payroll_settings, leave_policy):
    start = date(2024, 1, 26)

    for i in range(10):
        create_attendance(employee, start + timedelta(days=i), 1)

    CompOffRequest.objects.create(
        employee=employee,
        from_date=start,
        to_date=start + timedelta(days=1),
        status="Approved"
    )

    calculate_leave_balance(employee, payroll_settings)
    lb = LeaveBalance.objects.last()

    assert lb.compoff == Decimal("2.00")

@freeze_time("2024-02-15")
def test_carry_forward(employee, payroll_settings, leave_policy):
    start = date(2024, 1, 26)

    for i in range(22):
        create_attendance(employee, start + timedelta(days=i), 1)

    calculate_leave_balance(employee, payroll_settings)
    first = LeaveBalance.objects.last()

    calculate_leave_balance(employee, payroll_settings)
    second = LeaveBalance.objects.last()

    assert second.opening_balance == first.final_leave_balance



@freeze_time("2024-04-15")
def test_reset_month(employee, payroll_settings, leave_policy):
    payroll_settings.carry_forward = False
    payroll_settings.reset_month = 4
    payroll_settings.save()

    calculate_leave_balance(employee, payroll_settings)
    lb = LeaveBalance.objects.last()

    assert lb.opening_balance == Decimal("0.00")
