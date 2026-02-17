"""
Leave Balance Calculation Service
Works with existing PayrollSettings model that has:
- is_auto (bool): True = calendar month, False = custom period
- from_date (int): Start day (e.g., 26)
- to_date (int): End day (e.g., 25)
- get_payroll_period(): Method that returns (from_date, to_date)
"""
from decimal import Decimal
from django.db.models import Sum
from datetime import date, timedelta
from website.models import Attendance, LeaveBalance, CompOffRequest


def calculate_leave_balance(employee, payroll_settings, target_date=None):
    """
    Calculate monthly leave balance for an employee
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
    # ============================================
    attendance_records = Attendance.objects.filter(
        employee=employee,
        date__gte=from_date,
        date__lte=to_date
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
    # STEP 8: Leave Credit Based on Policy
    # ============================================
    policy = employee.company.leave_credit_policy
    
    # Use paid_days for credit calculation
    present_days_for_credit = int(paid_days)
    
    if present_days_for_credit <= policy.credit_1_limit:
        monthly_credit = policy.credit_low
    elif present_days_for_credit <= policy.credit_2_limit:
        monthly_credit = policy.credit_mid
    else:
        monthly_credit = policy.credit_high
    
    # Apply monthly cap (earned_leaves_per_year / 12)
    monthly_cap = Decimal(str(payroll_settings.earned_leaves_per_year)) / Decimal("12")
    monthly_credit = min(Decimal(str(monthly_credit)), monthly_cap)
    
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