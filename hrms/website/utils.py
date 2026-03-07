# ✅ UPDATED website/utils.py
# Now uses MonthlyEarnedLeaves instead of hardcoded credit logic

from website.models import (
    Attendance, LeaveBalance, PayrollSettings, CompOffRequest,
    MonthlyEarnedLeaves, Employee
)
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from django.db.models import Sum, Min, Max
from django.db import transaction


def get_monthly_earned_leaves(payroll_settings, month, year):
    """
    ✅ Get earned leaves for a specific month from database
    
    Reads from MonthlyEarnedLeaves table instead of calculating
    
    Parameters:
    - payroll_settings: PayrollSettings instance
    - month: Month number (1-12)
    - year: Year
    
    Returns: Decimal value of earned leaves for that month
    """
    try:
        monthly_leave = MonthlyEarnedLeaves.objects.get(
            payroll_settings=payroll_settings,
            month=month,
            year=year
        )
        return Decimal(str(monthly_leave.earned_leaves))
    except MonthlyEarnedLeaves.DoesNotExist:
        # If not found, return 0 (shouldn't happen if properly set up)
        return Decimal('0.00')


def recalculate_all_leave_balances():
    """
    ✅ UPDATED: Re-run leave balance calculation for ALL employees
    Now uses MonthlyEarnedLeaves from database
    
    This lets you test instantly without inserting new attendance/compoff.
    """

    today = date.today()
    employees = Employee.objects.filter(status='Active')
    
    for employee in employees:
        payroll_settings = PayrollSettings.objects.filter(
            company=employee.company
        ).first()
        
        if not payroll_settings:
            continue
        
        # Get all attendance periods for this employee
        periods = get_all_payroll_periods_for_employee(employee, payroll_settings)
        
        for period_info in periods:
            full_from_date = period_info['from_date']
            full_to_date = period_info['to_date']
            
            # ============================================
            # STEP 1: Opening Balance
            # Get previous period's final balance
            # ============================================
            prev_period_end = full_from_date - timedelta(days=1)
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
            
            # ============================================
            # STEP 2: Get Attendance (exclude holidays)
            # ============================================
            attendance_records = Attendance.objects.filter(
                employee=employee,
                date__gte=full_from_date,
                date__lte=full_to_date,
                is_holiday=False  # ✅ Exclude holidays
            )
            
            total_days = attendance_records.count()
            
            # ============================================
            # STEP 3: Paid Days
            # ============================================
            total_present_days = Decimal(
                attendance_records.aggregate(
                    total_present=Sum("count")
                )["total_present"] or 0
            )
            
            # ============================================
            # STEP 4: Leave Taken
            # ============================================
            leave_taken = Decimal(str(total_days)) - total_present_days
            if leave_taken < 0:
                leave_taken = Decimal("0.00")
            
            # ============================================
            # STEP 5: Late
            # ============================================
            total_late = Decimal(
                attendance_records.aggregate(
                    total_late=Sum("late")
                )["total_late"] or 0
            )
            
            late_days = total_late / Decimal("480")
            
            # ============================================
            # STEP 6: Comp-Off
            # ============================================
            compoff_days = Decimal(0)
            for c in CompOffRequest.objects.filter(
                employee=employee, 
                status="Approved",
                from_date__gte=full_from_date,
                to_date__lte=full_to_date
            ):
                compoff_days += Decimal((c.to_date - c.from_date).days + 1)
            
            # ============================================
            # STEP 7: Calculate LWP
            # ============================================
            balance_before_credit = opening_balance + compoff_days - leave_taken - late_days
            
            if balance_before_credit < 0:
                leave_without_pay = abs(balance_before_credit)
                leave_balance = Decimal("0.00")
            else:
                leave_without_pay = Decimal("0.00")
                leave_balance = balance_before_credit
            
            # ============================================
            # STEP 8: ✅ UPDATED - Get Monthly Credit from Database
            # ============================================
            monthly_credit = get_monthly_earned_leaves(
                payroll_settings,
                full_to_date.month,
                full_to_date.year
            )
            
            # ============================================
            # STEP 9: Closing Balance
            # ============================================
            closing_balance = leave_balance + monthly_credit
            final_leave_balance = min(
                closing_balance,
                Decimal(str(payroll_settings.max_leave_balance))
            )
            
            # ============================================
            # STEP 10: Save Record
            # ============================================
            LeaveBalance.objects.update_or_create(
                employee=employee,
                period_from_date=full_from_date,
                period_to_date=full_to_date,
                defaults={
                    'opening_balance': opening_balance,
                    'leave_taken': leave_taken,
                    'number_of_days_present': total_present_days,
                    'total_number_of_days': total_days,
                    'late': int(total_late),
                    'leave_without_pay': leave_without_pay,
                    'closing_balance': closing_balance,
                    'leave_balance': leave_balance,
                    'final_leave_balance': final_leave_balance,
                    'compoff': compoff_days,
                }
            )

    return True


def get_payroll_period_for_date(payroll_settings, target_date):
    """Get payroll period for a specific date"""
    return payroll_settings.get_payroll_period()


def get_all_payroll_periods_for_employee(employee, payroll_settings):
    """
    Get all payroll periods that have attendance data for an employee
    
    Returns: List of dicts with 'from_date' and 'to_date'
    """
    periods = []
    
    attendance_stats = Attendance.objects.filter(
        employee=employee
    ).aggregate(
        min_date=Min('date'),
        max_date=Max('date')
    )
    
    min_date = attendance_stats.get('min_date')
    max_date = attendance_stats.get('max_date')
    
    if not min_date or not max_date:
        return periods
    
    current_date = min_date
    seen_periods = set()
    
    while current_date <= max_date:
        from_d, to_d = payroll_settings.get_payroll_period()
        
        period_key = f"{from_d}_{to_d}"
        
        if period_key not in seen_periods:
            seen_periods.add(period_key)
            
            has_attendance = Attendance.objects.filter(
                employee=employee,
                date__gte=from_d,
                date__lte=to_d
            ).exists()
            
            if has_attendance:
                periods.append({
                    'from_date': from_d,
                    'to_date': to_d,
                })
        
        current_date += timedelta(days=1)
    
    return periods


def recalculate_employee_leave_balance(employee):
    """
    Recalculate leave balance for a single employee
    
    Usage in views:
    from website.utils import recalculate_employee_leave_balance
    
    recalculate_employee_leave_balance(employee)
    messages.success(request, f"✓ Leave balance recalculated for {employee.first_name}")
    """
    payroll_settings = PayrollSettings.objects.filter(
        company=employee.company
    ).first()
    
    if not payroll_settings:
        return False
    
    periods = get_all_payroll_periods_for_employee(employee, payroll_settings)
    
    for period_info in periods:
        full_from_date = period_info['from_date']
        full_to_date = period_info['to_date']
        
        # Get previous balance
        prev_period_end = full_from_date - timedelta(days=1)
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
        
        # Get attendance
        attendance_records = Attendance.objects.filter(
            employee=employee,
            date__gte=full_from_date,
            date__lte=full_to_date,
            is_holiday=False
        )
        
        total_days = attendance_records.count()
        total_present_days = Decimal(
            attendance_records.aggregate(
                total_present=Sum("count")
            )["total_present"] or 0
        )
        
        leave_taken = Decimal(str(total_days)) - total_present_days
        if leave_taken < 0:
            leave_taken = Decimal("0.00")
        
        total_late = Decimal(
            attendance_records.aggregate(
                total_late=Sum("late")
            )["total_late"] or 0
        )
        late_days = total_late / Decimal("480")
        
        compoff_days = Decimal(0)
        for c in CompOffRequest.objects.filter(
            employee=employee,
            status="Approved",
            from_date__gte=full_from_date,
            to_date__lte=full_to_date
        ):
            compoff_days += Decimal((c.to_date - c.from_date).days + 1)
        
        balance_before_credit = opening_balance + compoff_days - leave_taken - late_days
        
        if balance_before_credit < 0:
            leave_without_pay = abs(balance_before_credit)
            leave_balance = Decimal("0.00")
        else:
            leave_without_pay = Decimal("0.00")
            leave_balance = balance_before_credit
        
        # ✅ Get monthly credit from database
        monthly_credit = get_monthly_earned_leaves(
            payroll_settings,
            full_to_date.month,
            full_to_date.year
        )
        
        closing_balance = leave_balance + monthly_credit
        final_leave_balance = min(
            closing_balance,
            Decimal(str(payroll_settings.max_leave_balance))
        )
        
        LeaveBalance.objects.update_or_create(
            employee=employee,
            period_from_date=full_from_date,
            period_to_date=full_to_date,
            defaults={
                'opening_balance': opening_balance,
                'leave_taken': leave_taken,
                'number_of_days_present': total_present_days,
                'total_number_of_days': total_days,
                'late': int(total_late),
                'leave_without_pay': leave_without_pay,
                'closing_balance': closing_balance,
                'leave_balance': leave_balance,
                'final_leave_balance': final_leave_balance,
                'compoff': compoff_days,
            }
        )
    
    return True