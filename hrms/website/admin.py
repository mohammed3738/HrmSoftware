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
admin.site.register(CompOffRequest)
admin.site.register(CompOff)
# admin.site.register(PayrollSettings)
admin.site.register(SalaryIncrement)



admin.site.register(Attendance)
admin.site.register(LeaveBalance)
admin.site.register(LeaveBalanceHistory)
admin.site.register(AttendanceCorrectionRequest)
admin.site.register(SalaryHistory)
admin.site.register(PreviousEmploymentAttachment)



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
admin.site.register(AdvanceInstallment)



# leave credit setting

@admin.register(LeaveCreditPolicy)
class LeaveCreditPolicyAdmin(admin.ModelAdmin):
    list_display = (
        "company",
        "credit_1_limit",
        "credit_2_limit",
        "credit_low",
        "credit_mid",
        "credit_high",
        "updated_at",
    )
    list_filter = ("company",)
    search_fields = ("company__name",)
    ordering = ("company",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("Company", {"fields": ("company",)}),
        ("Credit Thresholds", {
            "fields": ("credit_1_limit", "credit_2_limit"),
            "description": "These thresholds are based on 'Days Present' for the month.",
        }),
        ("Credit Values", {
            "fields": ("credit_low", "credit_mid", "credit_high"),
            "description": (
                "Define how many leaves should be credited based on days present.<br>"
                "Example: ≤15 = 0 credit, 16–25 = 1 credit, >25 = 2 credit."
            ),
        }),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
