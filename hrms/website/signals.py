from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import *
from django.db.models import Sum
from dateutil.relativedelta import relativedelta
from datetime import date, timedelta
from django.db.models.signals import post_delete
from django.db.models import Q

from decimal import Decimal

def D(val):
    return Decimal(str(val or "0"))


@receiver(post_save, sender=Offboarding)
def update_status_in_model_a(sender, instance, created, **kwargs):
    if created:  # Only update when a new ModelB instance is created
        print('working')
        model_a_instance = instance.employee  # Get related ModelA instance
        model_a_instance.status = 'Pending'  # Change status value
        model_a_instance.save()  # Save the ModelA instance with the new status



@receiver(post_delete, sender=Offboarding)
def revert_status_in_model_a(sender, instance, **kwargs):
    model_a_instance = instance.employee  # Get related ModelA instance
    model_a_instance.status = 'Active'  # Revert status value
    model_a_instance.save()  # Save the ModelA instance with the reverted status

# from django.db.models.signals import post_save
# from django.dispatch import receiver
# from .models import Employee, LeaveBalance

# @receiver(post_save, sender=Employee)
# def create_leave_balance(sender, instance, created, **kwargs):
#     """Automatically create a leave balance record when an employee is created."""
#     if created:
#         LeaveBalance.objects.create(employee=instance)  # Default 10 leaves






from django.db.models import Sum
from django.utils.timezone import now
from datetime import date








# -----------------------
# Helper utilities
# -----------------------
# def _to_date(d):
#     """Ensure 'd' is a date object (not datetime)."""
#     if d is None:
#         return None
#     if hasattr(d, "date"):
#         return d.date()
#     return d


# -----------------------
# 1) Create a LeaveBalance for new employees (initialized to zero)
# -----------------------
# @receiver(post_save, sender=Employee)
# def create_leave_balance(sender, instance, created, **kwargs):
#     if created:
#         LeaveBalance.objects.create(
#             employee=instance,
#             opening_balance=Decimal("0.00"),
#             leave_taken=Decimal("0.00"),
#             number_of_days_present=Decimal("0.00"),
#             total_number_of_days=0,
#             late=0,
#             compoff=0.0,
#             leave_without_pay=Decimal("0.00"),
#             closing_balance=Decimal("0.00"),
#             leave_balance=Decimal("0.00"),
#             final_leave_balance=Decimal("0.00"),
#         )
#         print(f"[signals] Initialized LeaveBalance = 0 for {instance.first_name}")













# signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User, Group
# from .models import Employee

@receiver(post_save, sender=Employee)
def sync_user(sender, instance, created, **kwargs):
    if created and not instance.user:
        user = User.objects.create_user(
            username=instance.employee_code,
            email=instance.personal_email,
            first_name=instance.first_name,
            last_name=instance.last_name,
            password="Temp@123"
        )
        # Give every auto-provisioned login a baseline role immediately --
        # without this, the account has no group at all until someone
        # separately assigns one via the employee form, and in the
        # meantime login_view's fallback sends them to admin-dashboard,
        # which they have no permission for -> 403 on first login. HR can
        # still upgrade them to HR/Admin/Manager later as usual.
        employee_group, _ = Group.objects.get_or_create(name="Employee")
        user.groups.add(employee_group)
        instance.user = user
        instance.force_password_change = True
        instance.save()

    if instance.status == "Left" and instance.user:
        instance.user.is_active = False
        instance.user.save()




@receiver(post_save, sender=PayrollSettings)
def generate_monthly_earned_leaves(sender, instance, created, **kwargs):
    """
    Auto-generate monthly earned leaves whenever PayrollSettings
    is created or updated.
    """

    MonthlyEarnedLeaves.generate_for_payroll_settings(instance)
