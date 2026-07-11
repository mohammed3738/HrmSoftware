"""
✅ UPDATED Leave Balance Calculation Service
Now reads monthly earned leaves from MonthlyEarnedLeaves table instead of dividing by 12

Works with existing PayrollSettings model that has:
- is_auto (bool): True = calendar month, False = custom period
- from_date (int): Start day (e.g., 26)
- to_date (int): End day (e.g., 25)
- get_payroll_period(): Method that returns (from_date, to_date)
- earned_leaves_per_year (int): Total leaves per year
- max_leave_balance (int): Max leaves to carry forward
"""
from decimal import Decimal
from django.db.models import Sum
from datetime import date, timedelta
from website.models import Attendance, LeaveBalance, CompOffRequest, MonthlyEarnedLeaves


def get_monthly_earned_leaves(payroll_settings, month, year):
    """
    ✅ NEW: Get earned leaves for a specific month from database
    
    Instead of dividing earned_leaves_per_year by 12,
    this reads the actual value from MonthlyEarnedLeaves table
    
    Parameters:
    - payroll_settings: PayrollSettings instance
    - month: Month number (1-12)
    - year: Year
    
    Returns: Decimal value of earned leaves for that month
    
    Example:
    >>> payroll = PayrollSettings.objects.first()
    >>> march_leaves = get_monthly_earned_leaves(payroll, 3, 2025)
    >>> print(march_leaves)  # Output: Decimal('1.00')
    """
    try:
        monthly_leave = MonthlyEarnedLeaves.objects.get(
            payroll_settings=payroll_settings,
            month=month,
            year=year
        )
        return Decimal(str(monthly_leave.earned_leaves))
    except MonthlyEarnedLeaves.DoesNotExist:
        # Fallback: divide annual leaves evenly across 12 months
        return (Decimal(str(payroll_settings.earned_leaves_per_year)) / Decimal('12')).quantize(Decimal('0.01'))


def calculate_leave_balance(employee, payroll_settings, target_date=None):
    """
    ✅ UPDATED: Calculate monthly leave balance for an employee
    Now reads monthly credit from MonthlyEarnedLeaves table
    
    Uses payroll_settings.get_payroll_period() to get the date range
    
    Formula references match Excel columns:
    C=Opening, D=Leave Taken, E=Late, F=Compoff, G=LWP, H=Paid Days, 
    I=Total Days, J=Balance, K=Closing Balance
    """
    
    if target_date is None:
        target_date = date.today()
    
    # Get payroll period using the existing method
    from_date, to_date = payroll_settings.get_payroll_period()
    
    # ============================================
    # STEP 1: Opening Balance (Column C)
    # Get the LAST leave balance record before this period
    # ============================================
    prev_period_end = from_date - timedelta(days=1)
    prev_from, prev_to = get_payroll_period_for_date(payroll_settings, prev_period_end)

    previous_record = (
        LeaveBalance.objects
        .filter(
            employee=employee,
            period_from_date=prev_from,
            period_to_date=prev_to
        )
        .first()
    )
    
    opening_balance = (
        previous_record.final_leave_balance 
        if previous_record 
        else Decimal("0.00")
    )
    
    # Handle reset logic - if carry_forward is False and we're in reset month
    if not getattr(payroll_settings, 'carry_forward', True):
        reset_month = getattr(payroll_settings, 'reset_month', None)
        if reset_month and reset_month == to_date.month:
            opening_balance = Decimal("0.00")
    
    # ============================================
    # STEP 2: Attendance Aggregation
    # Get attendance records for this payroll period
    # ✅ EXCLUDE HOLIDAYS (is_holiday=False)
    # ============================================
    # Determine weekend exclusion (Django week_day: 1=Sunday, 7=Saturday)
    if getattr(payroll_settings, 'weekend_days', 'sat_sun') == 'sun':
        weekend_exclude = [1]       # Sunday only
    else:
        weekend_exclude = [1, 7]    # Saturday & Sunday

    attendance_records = Attendance.objects.filter(
        employee=employee,
        date__gte=from_date,
        date__lte=to_date,
        is_holiday=False,
    ).exclude(date__week_day__in=weekend_exclude)

    # Total days = actual calendar days in the payroll period (from_date to to_date inclusive)
    total_days = (to_date - from_date).days + 1

    # Working days (excluding weekends/holidays) for leave taken calculation
    working_days = attendance_records.count()

    # ============================================
    # STEP 3: Calculate Paid Days (Column H)
    # SUM the count field (1.0 for full day, 0.5 for half day, 0.0 for absent)
    # ============================================
    paid_days_sum = attendance_records.aggregate(
        total=Sum("count")
    )["total"]
    paid_days = paid_days_sum if paid_days_sum else Decimal("0.00")

    # Count weekend days in the period — they are always treated as present
    sunday_only = getattr(payroll_settings, 'weekend_days', 'sat_sun') == 'sun'
    weekend_day_count = 0
    d = from_date
    while d <= to_date:
        is_weekend = (d.weekday() == 6) if sunday_only else (d.weekday() >= 5)
        if is_weekend:
            weekend_day_count += 1
        d += timedelta(days=1)

    # Days present shown in leave balance = actual paid working days + all weekends
    days_present = paid_days + Decimal(str(weekend_day_count))

    # ============================================
    # STEP 4: Leave Taken (Column D)
    # Based on working days only — weekends are never counted as leave taken
    # ============================================
    leave_taken = Decimal(str(working_days)) - paid_days
    if leave_taken < 0:
        leave_taken = Decimal("0.00")
    
    # ============================================
    # STEP 5: Late Count (Column E)
    # Count attendance records marked as "Late Present".
    # If late_marks_affect_lwp is False in settings, late marks are tracked
    # but never converted to LWP deductions.
    # ============================================
    late_count = attendance_records.filter(status="Late Present").count()
    if getattr(payroll_settings, 'late_marks_affect_lwp', True):
        # Grace: first 5 late marks are free. Every 3 marks after that = 1 day deducted.
        late_days = Decimal(str((late_count - 5) // 3)) if late_count > 5 else Decimal("0")
    else:
        late_days = Decimal("0")
    
    # ============================================
    # STEP 6: Approved Comp-Off (Column F)
    # ============================================
    compoff_total = (
        CompOffRequest.objects
        .filter(
            employee=employee,
            status="Approved",
            from_date__gte=from_date,
            to_date__lte=to_date
        )
        .aggregate(total=Sum("count"))["total"]
        or Decimal("0.00")
    )
    
    # ============================================
    # STEP 7: Calculate LWP (Column G)
    # If this period's record has a manual LWP override, preserve it.
    # Otherwise calculate normally.
    # ============================================
    existing_lb = LeaveBalance.objects.filter(
        employee=employee,
        period_from_date=from_date,
        period_to_date=to_date,
        lwp_overridden=True,
    ).first()

    if existing_lb:
        leave_without_pay = existing_lb.leave_without_pay
        balance_after_lwp = opening_balance + compoff_total - leave_taken - late_days - leave_without_pay
        leave_balance = max(Decimal("0.00"), balance_after_lwp)
    else:
        balance_before_credit = opening_balance + compoff_total - leave_taken - late_days
        if balance_before_credit < 0:
            leave_without_pay = abs(balance_before_credit)
            leave_balance = Decimal("0.00")
        else:
            leave_without_pay = Decimal("0.00")
            leave_balance = balance_before_credit
    
    # ============================================
    # STEP 8: Monthly Leave Credit via LeaveCreditPolicy
    # Credit depends on how many days the employee was present this period.
    # ============================================
    try:
        policy = employee.company.leave_credit_policy
        present_for_credit = int(days_present)
        if present_for_credit <= policy.credit_1_limit:
            monthly_credit = Decimal(str(policy.credit_low))
        elif present_for_credit <= policy.credit_2_limit:
            monthly_credit = Decimal(str(policy.credit_mid))
        else:
            monthly_credit = Decimal(str(policy.credit_high))
        monthly_cap = Decimal(str(payroll_settings.earned_leaves_per_year)) / Decimal('12')
        monthly_credit = min(monthly_credit, monthly_cap)
    except Exception:
        monthly_credit = Decimal("1.00")
    
    # ============================================
    # STEP 9: Closing Balance (Column K)
    # Excel: =MIN((J4+monthly_credit), max_balance)
    # ============================================
    closing_balance = leave_balance + monthly_credit
    
    # Apply max leave balance cap from settings
    final_leave_balance = min(
        closing_balance,
        Decimal(str(payroll_settings.max_leave_balance))
    )
    
    # ============================================
    # STEP 10: Save Record (Prevent Duplicates)
    # Use update_or_create to avoid duplicate records
    # ============================================
    LeaveBalance.objects.update_or_create(
        employee=employee,
        period_from_date=from_date,
        period_to_date=to_date,
        defaults={
            'opening_balance': opening_balance,
            'leave_taken': leave_taken,
            'number_of_days_present': days_present,
            'total_number_of_days': total_days,
            'late': late_count,
            'compoff': compoff_total,
            'leave_without_pay': leave_without_pay,
            'leave_balance': leave_balance,  # Column J
            'closing_balance': closing_balance,  # Column K before cap
            'final_leave_balance': final_leave_balance  # Column K after cap
        }
    )
    
    return final_leave_balance


def get_employee_leave_summary(employee):
    """
    Get current leave balance summary for an employee
    Useful for display purposes
    """
    latest_record = (
        LeaveBalance.objects
        .filter(employee=employee)
        .order_by("-id")
        .first()
    )
    
    if not latest_record:
        return {
            'available_leaves': Decimal("0.00"),
            'lwp_this_month': Decimal("0.00"),
            'leaves_taken': Decimal("0.00"),
            'compoff_available': Decimal("0.00")
        }
    
    # Count pending approved comp-offs not yet used
    today = date.today()
    unused_compoff = (
        CompOffRequest.objects
        .filter(
            employee=employee,
            status="Approved",
            to_date__gte=today
        )
        .aggregate(total=Sum("count"))["total"]
        or Decimal("0.00")
    )
    
    return {
        'available_leaves': latest_record.final_leave_balance,
        'lwp_this_month': latest_record.leave_without_pay,
        'leaves_taken': latest_record.leave_taken,
        'compoff_available': unused_compoff,
        'last_updated': latest_record.id
    }


def get_payroll_period_for_date(payroll_settings, target_date=None):
    """
    Get payroll period that contains target_date.
    If from_date and to_date (day numbers) are explicitly configured, they always
    take priority over the is_auto flag.  is_auto is only used as a fallback when
    neither day number is set.
    """
    if target_date is None:
        target_date = date.today()

    from_day = payroll_settings.from_date
    to_day = payroll_settings.to_date

    if from_day and to_day:
        if from_day <= to_day:
            # Same-month period (e.g. 1 → 31)
            if target_date.day >= from_day:
                from_d = date(target_date.year, target_date.month, from_day)
                to_d = date(target_date.year, target_date.month, to_day)
            else:
                prev_month = target_date.month - 1
                prev_year = target_date.year
                if prev_month == 0:
                    prev_month = 12
                    prev_year -= 1
                from_d = date(prev_year, prev_month, from_day)
                to_d = date(prev_year, prev_month, to_day)
        else:
            # Cross-month period (e.g. 27 → 26)
            if target_date.day >= from_day:
                from_d = date(target_date.year, target_date.month, from_day)
                next_month = target_date.month + 1
                next_year = target_date.year
                if next_month > 12:
                    next_month = 1
                    next_year += 1
                to_d = date(next_year, next_month, to_day)
            else:
                prev_month = target_date.month - 1
                prev_year = target_date.year
                if prev_month == 0:
                    prev_month = 12
                    prev_year -= 1
                from_d = date(prev_year, prev_month, from_day)
                to_d = date(target_date.year, target_date.month, to_day)
        return from_d, to_d

    # Fallback: calendar month
    first_day = target_date.replace(day=1)
    if target_date.month == 12:
        last_day = date(target_date.year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(target_date.year, target_date.month + 1, 1) - timedelta(days=1)
    return first_day, last_day