from django.contrib import admin
from .models import *
# Register your models here.





class EmployeeAdmin(admin.ModelAdmin):
    # Fields to display in the admin list view
    list_display = ('first_name', 'middle_name', 'last_name', 'personal_mobile')
    # Fields to use for search functionality
    search_fields = ('first_name', 'middle_name', 'last_name', 'personal_mobile')

admin.site.register(Employee, EmployeeAdmin)
admin.site.register(EmployeeAttachment)

# Register the model with the customized admin
class PreviousEmployementAdmin(admin.ModelAdmin):
    # Fields to display in the admin list view
    list_display = ('employer_name', 'from_date', 'to_date', 'last_ctc')
    # Fields to use for search functionality
    search_fields = ('employer_name', 'from_date', 'to_date', 'last_ctc')

# Register the model with the customized admin
admin.site.register(PreviousEmployment, PreviousEmployementAdmin)


class OffbaordingAdmin(admin.ModelAdmin):
    # Fields to display in the admin list view
    list_display = ('date_of_resignation', 'employee', 'date_of_relieving')
    # Fields to use for search functionality
    search_fields = ('date_of_resignation', 'employee', 'date_of_relieving')

admin.site.register(Offboarding, OffbaordingAdmin)


class CompanyAdmin(admin.ModelAdmin):
    # Fields to display in the admin list view
    list_display = ('short_name', 'name', 'address')
    # Fields to use for search functionality
    search_fields = ('short_name', 'name', 'address')

# Register the model with the customized admin

admin.site.register(Company, CompanyAdmin)


class BranchAdmin(admin.ModelAdmin):
    # Fields to display in the admin list view
    list_display = ('branch_name',)  # Use a tuple with a trailing comma
    # Fields to use for search functionality
    
    search_fields = ('branch_name',)  # Use a tuple with a trailing comma

# Register the model with the customized admin
admin.site.register(Branch, BranchAdmin)

# class AssetAdmin(admin.ModelAdmin):
#     list_display = ('asset_name', 'assigned_to', 'handed_over_to')
#     search_fields = ('asset_name', 'assigned_to')
#     list_filter = ('asset_name', 'handed_over_to')  # Filter by status or employee

# admin.site.register(Asset, AssetAdmin)

class EmployeeSalarayAdmin(admin.ModelAdmin):
    list_display = ('employee', 'gross_ctc_pm', 'gross_ctc_pa')
    search_fields = ('employee', 'gross_ctc_pm')
    list_filter = ('employee', 'gross_ctc_pm')  # Filter by status or employee

admin.site.register(SalaryMaster, EmployeeSalarayAdmin)
# admin.site.register(CompOffRequest)
admin.site.register(CompOff)
# admin.site.register(PayrollSettings)
admin.site.register(SalaryIncrement)

class CompOffRequestAdmin(admin.ModelAdmin):
    list_display = ('employee','from_date', 'to_date', 'count', 'status', 'rejection_reason')
    search_fields = ('emp__first_name', 'emp__last_name', 'status')
    list_filter = ('status',)
admin.site.register(CompOffRequest, CompOffRequestAdmin)



admin.site.register(Attendance)
# admin.site.register(LeaveBalance)
# admin.site.register(LeaveBalanceHistory)
admin.site.register(AttendanceCorrectionRequest)
admin.site.register(SalaryHistory)
admin.site.register(PreviousEmploymentAttachment)
admin.site.register(PayrollRecord)
admin.site.register(PayrollRun)
admin.site.register(AssetHandover)



@admin.register(LeaveSettings)
class LeaveSettingsAdmin(admin.ModelAdmin):
    list_display = ("id", "carry_forward", "reset_month")  # Add 'id' as the first field
    # list_display = ('id', 'carry_forward', 'reset_month','pf_percentage', 'esic_percentage', 'gratuity_percentage', 'professional_tax', 'bonus_percentage')

    list_display_links = ("id",)  # Make 'id' a clickable link
    list_editable = ("carry_forward", "reset_month")  # Now these fields are editable



@admin.register(PayrollSettings)
class PayrollSettingsAdmin(admin.ModelAdmin):
    list_display = (
        'pf_percentage', 'esic_percentage', 'gratuity_percentage',
        'professional_tax', 'bonus_percentage', 'basic_percentage',
        'hra_percentage', 'basic_cap'
    )



admin.site.register(AdvanceMaster)
# admin.site.register(AdvanceInstallment)



# leave credit setting

# @admin.register(LeaveCreditPolicy)
# class LeaveCreditPolicyAdmin(admin.ModelAdmin):
#     list_display = (
#         "company",
#         "credit_1_limit",
#         "credit_2_limit",
#         "credit_low",
#         "credit_mid",
#         "credit_high",
#         "updated_at",
#     )
#     list_filter = ("company",)
#     search_fields = ("company__name",)
#     ordering = ("company",)
#     readonly_fields = ("created_at", "updated_at")

#     fieldsets = (
#         ("Company", {"fields": ("company",)}),
#         ("Credit Thresholds", {
#             "fields": ("credit_1_limit", "credit_2_limit"),
#             "description": "These thresholds are based on 'Days Present' for the month.",
#         }),
#         ("Credit Values", {
#             "fields": ("credit_low", "credit_mid", "credit_high"),
#             "description": (
#                 "Define how many leaves should be credited based on days present.<br>"
#                 "Example: ≤15 = 0 credit, 16–25 = 1 credit, >25 = 2 credit."
#             ),
#         }),
#         ("Timestamps", {"fields": ("created_at", "updated_at")}),
#     )






"""
Django Admin configuration for Leave Balance system
Add this to your admin.py
"""
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import LeaveBalance, LeaveBalanceHistory, LeaveCreditPolicy


@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = [
        'employee_code',
        'employee_name',
        'opening_balance',
        'leave_taken',
        'compoff',
        'lwp_display',
        'final_balance_display',
        'status_badge'
    ]
    list_filter = ['employee__company', 'employee__branch']
    search_fields = [
        'employee__employee_code',
        'employee__first_name',
        'employee__last_name'
    ]
    readonly_fields = [
        'opening_balance',
        'leave_taken',
        'number_of_days_present',
        'total_number_of_days',
        'late',
        'compoff',
        'leave_without_pay',
        'leave_balance',
        'closing_balance',
        'final_leave_balance'
    ]
    
    def employee_code(self, obj):
        return obj.employee.employee_code
    employee_code.short_description = 'Emp Code'
    
    def employee_name(self, obj):
        return f"{obj.employee.first_name} {obj.employee.last_name}"
    employee_name.short_description = 'Employee'
    
    def lwp_display(self, obj):
        if obj.leave_without_pay > 0:
            return format_html(
                '<span style="color: red; font-weight: bold;">{}</span>',
                obj.leave_without_pay
            )
        return obj.leave_without_pay
    lwp_display.short_description = 'LWP'
    
    def final_balance_display(self, obj):
        color = 'green' if obj.final_leave_balance >= 10 else 'orange' if obj.final_leave_balance >= 5 else 'red'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.final_leave_balance
        )
    final_balance_display.short_description = 'Final Balance'
    
    def status_badge(self, obj):
        if obj.final_leave_balance >= 10:
            badge = '<span style="background: #d4edda; color: #155724; padding: 3px 8px; border-radius: 3px;">Good</span>'
        elif obj.final_leave_balance >= 5:
            badge = '<span style="background: #fff3cd; color: #856404; padding: 3px 8px; border-radius: 3px;">Low</span>'
        else:
            badge = '<span style="background: #f8d7da; color: #721c24; padding: 3px 8px; border-radius: 3px;">Critical</span>'
        return mark_safe(badge)
    status_badge.short_description = 'Status'
    
    def has_add_permission(self, request):
        # Prevent manual addition - should be auto-calculated
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Only superusers can delete
        return request.user.is_superuser


@admin.register(LeaveBalanceHistory)
class LeaveBalanceHistoryAdmin(admin.ModelAdmin):
    list_display = [
        'employee_code',
        'employee_name',
        'month_display',
        'opening_balance',
        'leave_taken',
        'compoff',
        'final_leave_balance',
        'created_at'
    ]
    list_filter = ['month', 'employee__company', 'employee__branch']
    search_fields = [
        'employee__employee_code',
        'employee__first_name',
        'employee__last_name'
    ]
    readonly_fields = [
        'employee',
        'month',
        'opening_balance',
        'leave_taken',
        'number_of_days_present',
        'total_number_of_days',
        'late',
        'compoff',
        'leave_without_pay',
        'leave_balance',
        'closing_balance',
        'final_leave_balance',
        'created_at'
    ]
    date_hierarchy = 'month'
    
    def employee_code(self, obj):
        return obj.employee.employee_code
    employee_code.short_description = 'Emp Code'
    
    def employee_name(self, obj):
        return f"{obj.employee.first_name} {obj.employee.last_name}"
    employee_name.short_description = 'Employee'
    
    def month_display(self, obj):
        return obj.month.strftime("%B %Y")
    month_display.short_description = 'Month'
    
    def has_add_permission(self, request):
        # Prevent manual addition
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Only superusers can delete history
        return request.user.is_superuser


@admin.register(LeaveCreditPolicy)
class LeaveCreditPolicyAdmin(admin.ModelAdmin):
    list_display = [
        'company',
        'credit_1_limit',
        'credit_low',
        'credit_2_limit',
        'credit_mid',
        'credit_high',
        'updated_at'
    ]
    list_filter = ['company']
    
    fieldsets = (
        ('Company', {
            'fields': ('company',)
        }),
        ('Attendance Thresholds', {
            'fields': ('credit_1_limit', 'credit_2_limit'),
            'description': 'Define the number of days present for each tier'
        }),
        ('Leave Credits', {
            'fields': ('credit_low', 'credit_mid', 'credit_high'),
            'description': 'Define how many leaves to credit for each tier'
        }),
    )
    
    def has_delete_permission(self, request, obj=None):
        # Prevent deletion - each company should have one policy
        return False


# Optional: Add custom admin actions
@admin.action(description='Recalculate leave balance for selected employees')
def recalculate_selected_employees(modeladmin, request, queryset):
    from .tasks import recalculate_employee_leave_balance
    
    count = 0
    for employee in queryset:
        recalculate_employee_leave_balance.delay(employee.id, employee.company_id)
        count += 1
    
    modeladmin.message_user(
        request,
        f"Leave balance recalculation started for {count} employee(s)."
    )


# Add this action to your Employee admin
# EmployeeAdmin.actions = [recalculate_selected_employees]




from website.models import HolidayType, HolidayCalendar, Holiday, HalfDayScenario, MonthlyEarnedLeaves

@admin.register(HolidayType)
class HolidayTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'type_category', 'color_code']
    list_filter = ['type_category']
    search_fields = ['name']

@admin.register(HolidayCalendar)
class HolidayCalendarAdmin(admin.ModelAdmin):
    list_display = ['branch', 'year', 'name', 'is_active']
    list_filter = ['year', 'branch', 'is_active']
    search_fields = ['name', 'branch__branch_name']

@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ['holiday_date', 'name', 'is_national', 'status']
    list_filter = ['holiday_date', 'is_national', 'status']
    search_fields = ['name']

@admin.register(HalfDayScenario)
class HalfDayScenarioAdmin(admin.ModelAdmin):
    list_display = ['scenario_date', 'branch', 'scenario_type', 'credit_count', 'is_approved']
    list_filter = ['scenario_date', 'branch', 'scenario_type', 'is_approved']
    search_fields = ['description']

@admin.register(MonthlyEarnedLeaves)
class MonthlyEarnedLeavesAdmin(admin.ModelAdmin):
    list_display = ['payroll_settings', 'year', 'month', 'earned_leaves', 'is_auto_generated']
    list_filter = ['year', 'payroll_settings__company', 'is_auto_generated']
    search_fields = ['payroll_settings__company__name']


@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = ['name', 'key', 'category', 'has_view', 'has_edit', 'has_approve', 'sort_order', 'is_active']
    list_filter = ['category', 'is_active']
    search_fields = ['name', 'key']
    ordering = ['category', 'sort_order']


@admin.register(RoleFeaturePermission)
class RoleFeaturePermissionAdmin(admin.ModelAdmin):
    list_display = ['role', 'feature', 'can_view', 'can_edit', 'can_approve', 'updated_at', 'updated_by']
    list_filter = ['role', 'feature__category']
    search_fields = ['role__name', 'feature__name']