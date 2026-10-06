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




from django.db import transaction

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
        try:
            with transaction.atomic():
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

                    for key, value in flags.items():
                        field = FIELD_MAP.get(key)
                        if field:
                            setattr(current, field, value)

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

                    # 4️⃣ UPDATE final computed CTC
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

                # 5️⃣ MARK increment processed (inside atomic — rolls back if any step fails)
                inc.is_processed = True
                inc.save()

        except Exception as e:
            print(f"Error processing increment {inc.id} for {inc.employee}: {e}")
            continue





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



@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60}
)
def reset_monthly_leave_balances_task(self):
    """Runs on the 1st of every month. The yearly reset itself happens
    inside calculate_leave_balance_for_period: with carry_forward off, the
    period ending in the company's reset month opens at 0. This task used to
    *delete* every LeaveBalance row in April -- all past periods' history
    included. Now it only re-runs the normal recalculation for companies
    whose reset month has just started, so the reset shows up straight
    away. Kept under the same name because the beat schedule (stored in
    the database by django-celery-beat) still calls it."""
    from website.signals import recalculate_leave_balance_for_employee

    today = date.today()
    companies = Company.objects.filter(
        payrollsettings__reset_month=today.month, payrollsettings__carry_forward=False,
    )
    recalculated = 0
    for employee in Employee.objects.filter(company__in=companies, status="Active"):
        recalculate_leave_balance_for_employee(employee, today)
        recalculated += 1
    return f"Reset month {today.month}: recalculated {recalculated} employee(s), nothing deleted"


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60}
)
def auto_process_all_companies_leave_balance(self):
    """Runs on the 25th at 23:55: recalculates every payroll period of every
    active employee. Shares recalculate_all_leave_balances() with the
    per-change recalculation, so it also leaves finalized payroll periods
    untouched and covers employees with no company."""
    from website.signals import recalculate_all_leave_balances

    done, skipped = recalculate_all_leave_balances()
    return f"Recalculated {done} leave balance period(s); {skipped} employee(s) skipped (no payroll cycle anywhere)"
















@shared_task
def backfill_holiday_attendance_task():
    """Daily safety net: make sure every recent holiday has 'Holiday'
    attendance rows for the employees it applies to, in case that day's
    attendance file was never uploaded (nobody expected to punch in on a
    holiday) or new employees joined after the holiday was created. Holiday
    creation/edit already does this immediately (see Holiday.backfill_attendance
    and views.add_holiday/edit_holiday) — this just catches anything missed."""
    window_start = now().date() - timedelta(days=90)
    holidays = Holiday.objects.filter(holiday_date__gte=window_start, holiday_date__lte=now().date())

    total_created = 0
    for holiday in holidays:
        try:
            total_created += holiday.backfill_attendance()
        except Exception as e:
            print(f"[backfill_holiday_attendance_task] Holiday {holiday.id} failed: {e}")

    return total_created