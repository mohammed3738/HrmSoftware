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
        # Fallback: If not found, return 0
        # This shouldn't happen if admin set up MonthlyEarnedLeaves correctly
        return Decimal('0.00')


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
    attendance_records = Attendance.objects.filter(
        employee=employee,
        date__gte=from_date,
        date__lte=to_date,
        is_holiday=False  # ✅ Don't count holidays as working days
    )
    
    # Total days in period (Column I)
    total_days = attendance_records.count()
    
    # ============================================
    # STEP 3: Calculate Paid Days (Column H)
    # SUM the count field (1.0 for full day, 0.5 for half day, 0.0 for absent)
    # ============================================
    paid_days_sum = attendance_records.aggregate(
        total=Sum("count")
    )["total"]
    paid_days = paid_days_sum if paid_days_sum else Decimal("0.00")
    
    # ============================================
    # STEP 4: Leave Taken (Column D)
    # Excel: =Total Days - Paid Days
    # ============================================
    leave_taken = Decimal(str(total_days)) - paid_days
    if leave_taken < 0:
        leave_taken = Decimal("0.00")
    
    # ============================================
    # STEP 5: Late Minutes to Days (Column E)
    # Convert late minutes to days (assuming 480 minutes = 1 day of 8 hours)
    # ============================================
    total_late_minutes = attendance_records.aggregate(
        total=Sum("late")
    )["total"]
    total_late_minutes = total_late_minutes if total_late_minutes else 0
    
    # Convert late minutes to days
    late_days = Decimal(str(total_late_minutes)) / Decimal("480")
    
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
    # Excel: =IF((C4+F4)<(D4+E4),(C4+F4)-(D4+E4),0)
    # If (opening + compoff) < (leave taken + late), balance goes negative = LWP
    # ============================================
    balance_before_credit = opening_balance + compoff_total - leave_taken - late_days
    
    if balance_before_credit < 0:
        leave_without_pay = abs(balance_before_credit)
        leave_balance = Decimal("0.00")
    else:
        leave_without_pay = Decimal("0.00")
        leave_balance = balance_before_credit
    
    # ============================================
    # STEP 8: ✅ UPDATED - Get Monthly Credit from Database
    # Instead of: earned_leaves_per_year / 12
    # Now: Read from MonthlyEarnedLeaves table
    # ============================================
    monthly_credit = get_monthly_earned_leaves(
        payroll_settings, 
        to_date.month,      # Month of period end date
        to_date.year        # Year of period end date
    )
    
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
    leave_record, created = LeaveBalance.objects.update_or_create(
        employee=employee,
        period_from_date=from_date,
        period_to_date=to_date,
        defaults={
            'opening_balance': opening_balance,
            'leave_taken': leave_taken,
            'number_of_days_present': paid_days,
            'total_number_of_days': total_days,
            'late': total_late_minutes,  # Store raw minutes
            'compoff': compoff_total,
            'leave_without_pay': leave_without_pay,
            'leave_balance': leave_balance,  # Column J
            'closing_balance': closing_balance,  # Column K before cap
            'final_leave_balance': final_leave_balance  # Column K after cap
        }
    )
    
    return final_leave_balance


def get_employee_leave_summary(employee, payroll_settings):
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
    Get payroll period for a specific date
    Wrapper around payroll_settings.get_payroll_period()
    """
    if target_date is None:
        target_date = date.today()
    
    return payroll_settings.get_payroll_period()