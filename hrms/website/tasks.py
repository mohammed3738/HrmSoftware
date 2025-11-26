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
        is_active=True,
        is_processed=False,
        effective_date__lte=today
    )

    for inc in increments:
        emp = inc.employee

        # 1️⃣ Move current salary to history
        current = SalaryMaster.objects.filter(employee=emp).first()

        if current:
            SalaryHistory.objects.create(
                employee=emp,
                data={
                    "pf_deducted": current.pf_deducted,
                    "gratuity_applicable": current.gratuity_applicable,
                    "esic_applicable": current.esic_applicable,
                    
                    # store all salary values cleanly
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
                        "esic_er_cont_pm": str(current.esic_er_cont_pm),
                        "pf_ee_cont_pm": str(current.pf_ee_cont_pm),
                        "esic_ee_cont_pm": str(current.esic_ee_cont_pm),
                        "profession_tax_pm": str(current.profession_tax_pm),
                        "net_salary_pm": str(current.net_salary_pm),
                        
                    }
                },
                start_date=today - timedelta(days=1),
                end_date=today,
            )

        # 2️⃣ Replace SalaryMaster with increment values
        if current:
            for field in [
                "gross_ctc_pm", "gross_ctc_pa",
                "basic_pm", "basic_pa",
                "hra_pm", "hra_pa",
                "stat_bonus_pm", "stat_bonus_pa",
                "allowance1_pm", "allowance1_pa",
                "allowance2_pm", "allowance2_pa",
                "sp_allowance_pm", "sp_allowance_pa",
                "guaranteed_cash_pm", "guaranteed_cash_pa",
                "pf_er_cont_pm", "pf_er_cont_pa",
                "pf_ee_cont_pm", "pf_ee_cont_pa",
                "esic_er_cont_pm", "esic_er_cont_pa",
                "esic_ee_cont_pm", "esic_ee_cont_pa",
                "profession_tax_pm", "profession_tax_pa",
                "gratuity_pm", "gratuity_pa",
                "net_salary_pm", "net_salary_pa",
                "ctc_pm", "ctc_pa",
                "pf_deducted", "esic_applicable", "gratuity_applicable"
            ]:
                setattr(current, field, getattr(inc, field))

            current.save()

        # 3️⃣ Mark increment processed
        inc.is_processed = True
        inc.save()




from celery import shared_task
from website.signals import reset_monthly_leave_balances

@shared_task
def reset_monthly_leave_balances_task():
    """
    Celery task to trigger monthly leave reset.
    """
    print("🕒 Celery Task: Running monthly leave reset...")
    reset_monthly_leave_balances()
    print("✅ Celery Task Completed: Leave balances reset successfully.")

