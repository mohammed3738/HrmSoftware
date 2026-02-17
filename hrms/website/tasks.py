from celery import shared_task
from django.utils.timezone import now
from .models import *
from datetime import date, timedelta

@shared_task(bind=True)
def test_func(self):
    for i in range(10):
        print(i)
    return "Done"



@shared_task
def check_and_update_status():
    # Get today's date
    today = now().date()

    # Fetch offboarding records where the relieving date matches today
    offboarding_records = Offboarding.objects.filter(date_of_relieving=today)

    for record in offboarding_records:
        try:
            # Get the related onboarding record
            onboarding_record = Employee.objects.get(id=record.employee.id)
            # Update the status to 'left'
            onboarding_record.status = 'Left'
            onboarding_record.save()
            print('yes worked')
        except Employee.DoesNotExist:
            print(f"No onboarding record found for employee: {record.id}")




from django.db import transaction, IntegrityError

# @shared_task
# def process_salary_increments():
#     today = date.today()
#     increments = SalaryIncrement.objects.filter(effective_date__lte=today, is_processed=False)

#     for increment in increments:
#         try:
#             with transaction.atomic():
#                 old_salary = SalaryMaster.objects.filter(employee=increment.employee, is_active=True).first()

#                 print('incri', increment.gross_ctc_pm)
#                 print('incri1', increment.gross_ctc_pa)

#                 if old_salary:
#                     # Deactivate old salary
#                     old_salary.is_active = False
#                     old_salary.save()
#                     print(f"🔄 Deactivated old salary for {increment.employee.first_name}")

#                     # Create new salary record (copy old data + updated CTC)
#                     new_salary = SalaryMaster.objects.create(
#                         employee=increment.employee,
#                         pf_deducted=increment.pf_deducted,
#                         gratuity_applicable=increment.gratuity_applicable,
#                         esic_applicable=increment.esic_applicable,  

#                         gross_ctc_pm=increment.gross_ctc_pm,
#                         gross_ctc_pa=increment.gross_ctc_pm * 12,

#                         basic_pm=increment.basic_pm,
#                         basic_pa=increment.basic_pm * 12,

#                         hra_pm=increment.hra_pm,
#                         hra_pa=increment.hra_pm * 12,

#                         stat_bonus_pm=increment.stat_bonus_pm,
#                         stat_bonus_pa=increment.stat_bonus_pm * 12,

#                         sp_allowance_pm=increment.sp_allowance_pm,
#                         sp_allowance_pa=increment.sp_allowance_pm * 12,

#                         allowance1_pm=increment.allowance1_pm,
#                         allowance1_pa=increment.allowance1_pm * 12,

#                         allowance2_pm=increment.allowance2_pm,
#                         allowance2_pa=increment.allowance2_pm * 12,

#                         guaranteed_cash_pm=increment.guaranteed_cash_pm,
#                         guaranteed_cash_pa=increment.guaranteed_cash_pm * 12,

#                         ctc_pm=increment.ctc_pm,
#                         ctc_pa=increment.ctc_pm * 12,

#                         pf_er_cont_pm=increment.pf_er_cont_pm,
#                         pf_er_cont_pa=increment.pf_er_cont_pm * 12,

#                         esic_er_cont_pm=increment.esic_er_cont_pm,
#                         esic_er_cont_pa=increment.esic_er_cont_pm * 12,

#                         pf_ee_cont_pm=increment.pf_ee_cont_pm,
#                         pf_ee_cont_pa=increment.pf_ee_cont_pm * 12,

#                         esic_ee_cont_pm=increment.esic_ee_cont_pm,
#                         esic_ee_cont_pa=increment.esic_ee_cont_pm * 12,

#                         profession_tax_pm=increment.profession_tax_pm,
#                         profession_tax_pa=increment.profession_tax_pm * 12,

#                         net_salary_pm=increment.net_salary_pm,
#                         net_salary_pa=increment.net_salary_pm * 12,

#                         effective_date=today,
#                         is_active=True
#                     )
#                     print(f"✅ Created new salary: ₹{new_salary.gross_ctc_pm}")

#                     # Mark increment as processed
#                     increment.is_processed = True
#                     increment.save()
#                     print(f"🟢 Increment marked as processed for {increment.employee.first_name}")
#                 else:
#                     print(f"⚠️ No active salary found for {increment.employee.first_name}")

#         except IntegrityError as e:
#             print(f"❌ IntegrityError: {e}")
#         except Exception as e:
#             print(f"❌ Unexpected error: {e}")
# @shared_task
# def process_salary_increments():
#     today = date.today()
#     increments = SalaryIncrement.objects.filter(effective_date__lte=today, is_processed=False)

#     for increment in increments:
#         try:
#             with transaction.atomic():
#                 old_salary = SalaryMaster.objects.filter(employee=increment.employee, is_active=True).first()

#                 print('incri', increment.new_gross_ctc_pm)
#                 print('incri1', increment.new_gross_ctc_pa)

#                 if old_salary:
#                     # Deactivate old salary
#                     old_salary.is_active = False
#                     old_salary.save()
#                     print(f"🔄 Deactivated old salary for {increment.employee.first_name}")

#                     # Create new salary record (copy old data + updated CTC)
#                     new_salary = SalaryMaster.objects.create(
#                         employee=increment.employee,
#                         gross_ctc_pm=increment.new_gross_ctc_pm,
#                         gross_ctc_pa=increment.new_gross_ctc_pa,
#                         basic_pm=old_salary.basic_pm,           # Copy from old record
#                         hra_pm=old_salary.hra_pm,               # Copy from old record
#                         sp_allowance_pm=old_salary.sp_allowance_pm, # Copy from old record
#                         sp_allowance_pa=old_salary.sp_allowance_pa, # Copy from old record
#                         effective_date=today,
#                         is_active=True
#                     )
#                     print(f"✅ Created new salary: ₹{new_salary.gross_ctc_pm}")

#                     # Mark increment as processed
#                     increment.is_processed = True
#                     increment.save()
#                     print(f"🟢 Increment marked as processed for {increment.employee.first_name}")
#                 else:
#                     print(f"⚠️ No active salary found for {increment.employee.first_name}")

#         except IntegrityError as e:
#             print(f"❌ IntegrityError: {e}")
#         except Exception as e:
#             print(f"❌ Unexpected error: {e}")





@shared_task
def process_salary_increments():

    today = date.today()

    increments = SalaryIncrement.objects.filter(
        is_processed=False,
        effective_date__lte=today
    )

    # FIELD MAP between increment JSON and SalaryMaster
    FIELD_MAP = {
        # Flags
        "pf_deducted": "pf_deducted",
        "esic_applicable": "esic_applicable",
        "gratuity_applicable": "gratuity_applicable",

        # Monthly Components (PM fields)
        "gross_ctc": "gross_ctc_pm",
        "basic": "basic_pm",
        "hra": "hra_pm",
        "stat_bonus": "stat_bonus_pm",
        "special_allowance": "sp_allowance_pm",
        "allowance1": "allowance1_pm",
        "allowance2": "allowance2_pm",
        "guaranteed_cash": "guaranteed_cash_pm",

        # Contributions
        "pf_er": "pf_er_cont_pm",
        "pf_ee": "pf_ee_cont_pm",
        "esic_er": "esic_er_cont_pm",
        "esic_ee": "esic_ee_cont_pm",

        # Professional Tax
        "professional_tax": "profession_tax_pm",

        # Net salary
        "net_salary": "net_salary_pm",
    }

    for inc in increments:
        emp = inc.employee
        current = SalaryMaster.objects.filter(employee=emp).first()

        # 1️⃣ SAVE CURRENT SALARY TO HISTORY
        if current:
            SalaryHistory.objects.create(
                employee=emp,
                data={
                    "flags": {
                        "pf_deducted": current.pf_deducted,
                        "gratuity_applicable": current.gratuity_applicable,
                        "esic_applicable": current.esic_applicable,
                    },
                    "salary": {
                        "gross_ctc_pm": str(current.gross_ctc_pm),
                        "basic_pm": str(current.basic_pm),
                        "hra_pm": str(current.hra_pm),
                        "stat_bonus_pm": str(current.stat_bonus_pm),
                        "sp_allowance_pm": str(current.sp_allowance_pm),
                        "allowance1_pm": str(current.allowance1_pm),
                        "allowance2_pm": str(current.allowance2_pm),
                        "guaranteed_cash_pm": str(current.guaranteed_cash_pm),
                        "ctc_pm": str(current.ctc_pm),
                        "pf_er_cont_pm": str(current.pf_er_cont_pm),
                        "pf_ee_cont_pm": str(current.pf_ee_cont_pm),
                        "esic_er_cont_pm": str(current.esic_er_cont_pm),
                        "esic_ee_cont_pm": str(current.esic_ee_cont_pm),
                        "profession_tax_pm": str(current.profession_tax_pm),
                        "net_salary_pm": str(current.net_salary_pm),
                    }
                },
                start_date=today - timedelta(days=1),
                end_date=today,
            )

        # 2️⃣ UPDATE SalaryMaster FROM INCREMENT
        if current:

            flags = inc.change_set.get("flags", {})
            monthly = inc.change_set.get("monthly", {})

            # Apply flags
            for key, value in flags.items():
                field = FIELD_MAP.get(key)
                if field:
                    setattr(current, field, value)

            # Apply monthly salary fields
            for key, value in monthly.items():
                field = FIELD_MAP.get(key)
                if field:
                    setattr(current, field, value)

            # 3️⃣ AUTO-GENERATE ANNUAL FIELDS (PA)
            for field in SalaryMaster._meta.get_fields():
                if field.name.endswith("_pa"):
                    pm_field = field.name.replace("_pa", "_pm")
                    pm_value = getattr(current, pm_field, None)
                    if pm_value:
                        setattr(current, field.name, pm_value * 12)

            # 4️⃣ UPDATE final computed CTC if needed
            current.ctc_pm = (
                (current.basic_pm or 0) +
                (current.hra_pm or 0) +
                (current.sp_allowance_pm or 0) +
                (current.allowance1_pm or 0) +
                (current.allowance2_pm or 0) +
                (current.stat_bonus_pm or 0)
            )

            current.ctc_pa = current.ctc_pm * 12

            current.save()

        # 5️⃣ MARK increment processed
        inc.is_processed = True
        inc.save()





# from celery import shared_task
# from website.signals import reset_monthly_leave_balances

# @shared_task
# def reset_monthly_leave_balances_task():
#     """
#     Celery task to trigger monthly leave reset.
#     """
#     print("🕒 Celery Task: Running monthly leave reset...")
#     reset_monthly_leave_balances()
#     print("✅ Celery Task Completed: Leave balances reset successfully.")



"""
Celery tasks for leave balance and employee management
Does NOT import from views.py to avoid circular imports
Instead uses dedicated service functions
"""

from celery import shared_task
from django.db import transaction
from django.db.models import Sum, Min, Max
from datetime import date, timedelta
from decimal import Decimal
from website.models import Employee, PayrollSettings, LeaveBalance, Company, Attendance


# ============================================
# HELPER FUNCTIONS (Moved from views.py)
# ============================================

def get_payroll_period_for_date(payroll_settings, target_date):
    """Determine which payroll period a date falls into"""
    if payroll_settings.is_auto:
        first_day = target_date.replace(day=1)
        if target_date.month == 12:
            last_day = date(target_date.year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = date(target_date.year, target_date.month + 1, 1) - timedelta(days=1)
        return first_day, last_day
    else:
        from_day = payroll_settings.from_date
        to_day = payroll_settings.to_date
        
        if from_day < to_day:
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


def get_all_payroll_periods_from_attendance(company, payroll_settings):
    """Get all unique payroll periods that have attendance data"""
    periods = []
    
    attendance_stats = Attendance.objects.filter(
        employee__company=company
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
        from_d, to_d = get_payroll_period_for_date(payroll_settings, current_date)
        
        period_key = f"{from_d}_{to_d}"
        
        if period_key not in seen_periods:
            seen_periods.add(period_key)
            
            has_attendance = Attendance.objects.filter(
                employee__company=company,
                date__gte=from_d,
                date__lte=to_d
            ).exists()
            
            if has_attendance:
                label = f"{from_d.strftime('%b %d')} - {to_d.strftime('%b %d, %Y')}"
                periods.append({
                    'label': label,
                    'from_date': from_d,
                    'to_date': to_d,
                    'display_date': to_d,
                })
        
        current_date += timedelta(days=1)
    
    periods.sort(key=lambda x: x['to_date'], reverse=True)
    
    return periods


def calculate_leave_balance_for_period(employee, payroll_settings, from_date, to_date):
    """Calculate leave balance for a specific payroll period"""
    
    # STEP 1: Opening Balance - Get PREVIOUS PERIOD's final balance
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
    
    # Handle reset logic
    if not getattr(payroll_settings, 'carry_forward', True):
        reset_month = getattr(payroll_settings, 'reset_month', None)
        if reset_month and reset_month == to_date.month:
            opening_balance = Decimal("0.00")
    
    # STEP 2: Attendance for THIS period
    attendance_records = Attendance.objects.filter(
        employee=employee,
        date__gte=from_date,
        date__lte=to_date
    )
    
    total_days = attendance_records.count()
    
    # STEP 3: Paid Days
    paid_days_sum = attendance_records.aggregate(
        total=Sum("count")
    )["total"]
    paid_days = paid_days_sum if paid_days_sum else Decimal("0.00")
    
    # STEP 4: Leave Taken
    leave_taken = Decimal(str(total_days)) - paid_days
    if leave_taken < 0:
        leave_taken = Decimal("0.00")
    
    # STEP 5: Late
    total_late_minutes = attendance_records.aggregate(
        total=Sum("late")
    )["total"]
    total_late_minutes = total_late_minutes if total_late_minutes else 0
    
    late_days = Decimal(str(total_late_minutes)) / Decimal("480")
    
    # STEP 6: Comp-Off
    from website.models import CompOffRequest
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
    
    # STEP 7: LWP
    balance_before_credit = opening_balance + compoff_total - leave_taken - late_days
    
    if balance_before_credit < 0:
        leave_without_pay = abs(balance_before_credit)
        leave_balance = Decimal("0.00")
    else:
        leave_without_pay = Decimal("0.00")
        leave_balance = balance_before_credit
    
    # STEP 8: Leave Credit Policy
    try:
        policy = employee.company.leave_credit_policy
        present_days_for_credit = int(paid_days)
        
        if present_days_for_credit <= policy.credit_1_limit:
            monthly_credit = policy.credit_low
        elif present_days_for_credit <= policy.credit_2_limit:
            monthly_credit = policy.credit_mid
        else:
            monthly_credit = policy.credit_high
        
        monthly_cap = Decimal(str(payroll_settings.earned_leaves_per_year)) / Decimal("12")
        monthly_credit = min(Decimal(str(monthly_credit)), monthly_cap)
    except:
        monthly_credit = Decimal("1.00")
    
    # STEP 9: Closing Balance
    closing_balance = leave_balance + monthly_credit
    
    final_leave_balance = min(
        closing_balance,
        Decimal(str(payroll_settings.max_leave_balance))
    )
    
    # STEP 10: Save Record
    LeaveBalance.objects.update_or_create(
        employee=employee,
        period_from_date=from_date,
        period_to_date=to_date,
        defaults={
            'opening_balance': opening_balance,
            'leave_taken': leave_taken,
            'number_of_days_present': paid_days,
            'total_number_of_days': total_days,
            'late': total_late_minutes,
            'compoff': compoff_total,
            'leave_without_pay': leave_without_pay,
            'leave_balance': leave_balance,
            'closing_balance': closing_balance,
            'final_leave_balance': final_leave_balance
        }
    )
    
    return final_leave_balance




@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60}
)
def reset_monthly_leave_balances_task(self):
    """
    Reset leave balances for financial year start (usually April 1st)
    Runs MONTHLY on 1st at 2:30 AM
    """
    try:
        today = date.today()
        reset_month = today.month
        
        # Only reset in April (month 4)
        if reset_month == 4:
            companies = Company.objects.all()
            
            for company in companies:
                try:
                    if hasattr(company, 'payrollsettings'):
                        payroll = company.payrollsettings
                        
                        if payroll.reset_month == reset_month:
                            # Delete old leave balance records
                            LeaveBalance.objects.filter(
                                employee__company=company
                            ).delete()
                            
                            print(f"✓ Reset leave balances for {company.name}")
                except Exception as e:
                    print(f"Error resetting {company.name}: {e}")
                    continue
        
        return f"✓ Leave balances reset for month {reset_month}"
        
    except Exception as e:
        print(f"Error in reset_monthly_leave_balances_task: {e}")
        self.retry(exc=e)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60}
)
def auto_process_all_companies_leave_balance(self):
    """
    Auto-process leave balance for ALL periods of ALL employees
    Runs on 25th of month at 11:55 PM
    
    This task:
    1. Gets all companies
    2. For each company, finds all payroll periods with attendance
    3. For each period, calculates leave balance for all employees
    4. Supports multi-period calculation (NOT just current period!)
    """
    try:
        companies = Company.objects.all()
        total_processed = 0
        error_count = 0
        
        for company in companies:
            try:
                if not hasattr(company, 'payrollsettings'):
                    continue
                
                payroll = company.payrollsettings
                employees = Employee.objects.filter(
                    company=company,
                    status="Active"
                )
                
                # Get ALL periods with attendance (not just current!)
                periods = get_all_payroll_periods_from_attendance(company, payroll)
                
                if not periods:
                    print(f"No periods found for {company.name}")
                    continue
                
                # Calculate for each period and each employee
                for period_info in periods:
                    for employee in employees:
                        try:
                            # Use multi-period aware calculation
                            calculate_leave_balance_for_period(
                                employee,
                                payroll,
                                period_info['from_date'],
                                period_info['to_date']
                            )
                            total_processed += 1
                        except Exception as e:
                            error_count += 1
                            print(f"Error for {employee.employee_code} in {period_info}: {e}")
                            continue
                
                print(f"✓ {company.name}: Processed {len(employees)} employees for {len(periods)} periods")
                
            except Exception as e:
                error_count += 1
                print(f"Error processing company {company.id}: {e}")
                continue
        
        return f"✓ Processed {total_processed} leave balances, {error_count} errors"
        
    except Exception as e:
        print(f"Error in auto_process_all_companies_leave_balance: {e}")
        self.retry(exc=e)
















