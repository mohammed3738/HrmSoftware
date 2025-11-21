from django import forms
from .models import *
from django.forms import inlineformset_factory,DateInput


# class EmployeeForm(forms.ModelForm):
#     class Meta:
#         model = Employee
#         fields = [
#             # Personal Details
#             'salutation','branch', 'company','first_name', 'middle_name', 'last_name', 'father_name', 
#             'gender', 'blood_group', 'date_of_birth', 'place_of_birth', 'personal_email', 
#             'present_address', 'permanent_address', 'personal_mobile', 'date_of_marriage',
#             #status
#             'status',
#             # ZCPL Office Details
#             'employee_code', 'designation', 'department', 'date_of_joining', 
#             'date_of_confirmation', 'location', 'payroll_of', 'shift',

#             # Statutory Details
#             'pan_no', 'aadhar_no', 'voter_id', 'passport', 'uan_no', 'pf_no', 'esic_no',

#             # Banking Details
#             'name_as_per_bank', 'salary_account_number', 'ifsc_code',
           

#             # Emergency Contact Details
#             'emergency_contact_name1', 'emergency_contact_relation1', 'emergency_contact_mobile1',
#             'emergency_contact_name2', 'emergency_contact_relation2', 'emergency_contact_mobile2'
#         ]



# PreviousEmploymentFormSet = inlineformset_factory(
#     Employee,
#     PreviousEmployment,
#     fields=['employer_name', 'from_date', 'to_date', 'last_ctc'],
#     widgets={
#         'from_date': DateInput(attrs={'type': 'date'}),
#         'to_date': DateInput(attrs={'type': 'date'}),
#     },

#     extra=1,  # Number of empty forms displayed
#     can_delete=True  # Allow deleting previous entries
# )

class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            'company', 'branch', 'salutation', 'first_name', 'middle_name', 'last_name',
            'father_name', 'gender', 'blood_group', 'date_of_birth', 'place_of_birth',
            'personal_email', 'present_address', 'permanent_address', 'personal_mobile',
            'date_of_marriage', 'employee_code', 'designation', 'department',
            'date_of_joining', 'date_of_confirmation', 'location', 'payroll_of', 'shift',
            'pan_no', 'aadhar_no', 'voter_id', 'passport', 'uan_no', 'pf_no', 'esic_no',
            'name_as_per_bank', 'salary_account_number', 'ifsc_code',
            'emergency_contact_name1', 'emergency_contact_relation1', 'emergency_contact_mobile1',
            'emergency_contact_name2', 'emergency_contact_relation2', 'emergency_contact_mobile2',
            'status',
        ]


        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "date_of_joining": forms.DateInput(attrs={"type": "date"}),
            "date_of_confirmation": forms.DateInput(attrs={"type": "date"}),
            "date_of_marriage": forms.DateInput(attrs={"type": "date"}),  # ✅ date picker
        }


# Create an inline formset for PreviousEmployment related to Employee.
PreviousEmploymentFormSet = inlineformset_factory(
    Employee,
    PreviousEmployment,
    fields=['employer_name', 'from_date', 'to_date', 'last_ctc'],
    extra=1,
    can_delete=True,
    widgets={
        'from_date': forms.DateInput(attrs={'type': 'date'}),
        'to_date': forms.DateInput(attrs={'type': 'date'}),
    }
)

class EmployeeAttachmentForm(forms.ModelForm):
    file = forms.FileField(required=False)

    class Meta:
        model = EmployeeAttachment
        fields = ['file']


EmployeeAttachmentFormSet = inlineformset_factory(
    Employee,
    EmployeeAttachment,
    form=EmployeeAttachmentForm,
    extra=1,
    can_delete=True
)





    # assets = forms.ModelMultipleChoiceField(queryset=Asset.objects.all(), widget=forms.CheckboxSelectMultiple, required=False)
    # def save(self, commit=True):
    #     employee = super().save(commit=False)
    #     for asset in self.cleaned_data['assets']:
    #         asset.asset_status = "Returned"
    #         asset.save()
    #     if commit:
    #         employee.save()
    #     return employee


class BranchForm(forms.ModelForm):
    class Meta:
        model= Branch
        fields = [
            'branch_name'
        ]

        
class OffboardingForm(forms.ModelForm):
    class Meta:
        model= Offboarding
        fields = "__all__"


class CompanyForm(forms.ModelForm):
    class Meta:
        model= Company
        fields = "__all__"




class SalaryMasterForm(forms.ModelForm):
    class Meta:
        model = SalaryMaster
        fields = [
            # Dropdowns
            'pf_deducted', 
            'gratuity_applicable', 
            'esic_applicable',

            # Salary Components (Monthly and Annually)
            'gross_ctc_pm', 
            'gross_ctc_pa', 
            'basic_pm', 
            'basic_pa', 
            'hra_pm', 
            'hra_pa', 
            'sp_allowance_pm', 
            'sp_allowance_pa', 
            'allowance1_pm', 
            'allowance1_pa', 
            'allowance2_pm', 
            'allowance2_pa',

            # Guaranteed Cash
            'guaranteed_cash_pm', 
            'guaranteed_cash_pa',

            # Cost to Company
            'ctc_pm', 
            'ctc_pa',

            # Deductions
            'pf_er_cont_pm', 
            'pf_er_cont_pa', 
            'esic_er_cont_pm', 
            'esic_er_cont_pa', 
            'pf_ee_cont_pm', 
            'pf_ee_cont_pa', 
            'esic_ee_cont_pm', 
            'esic_ee_cont_pa',

            # Profession Tax
            'profession_tax_pm', 
            'profession_tax_pa',

            # Net Salary
            'net_salary_pm', 
            'net_salary_pa',
        ]

        # Adding widgets for better customization
        widgets = {
            'pf_deducted': forms.Select(choices=[(True, "Yes"), (False, "No")]),
            'gratuity_applicable': forms.Select(choices=[(True, "Yes"), (False, "No")]),
            'esic_applicable': forms.Select(choices=[(True, "Yes"), (False, "No")]),
            'gross_ctc_pm': forms.NumberInput(attrs={'step': '0.01'}),
            'gross_ctc_pa': forms.NumberInput(attrs={'step': '0.01'}),
            # Add similar widgets for other fields as required...
        }



class AttendanceForm(forms.ModelForm):
    class Meta:
        model = Attendance
        fields = ["employee", "date", "in_time", "out_time","status","count","late"]





class PayrollSettingsForm(forms.ModelForm):
    class Meta:
        model = PayrollSettings
        exclude = ['company']
        widgets = {
            'is_auto': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'from_date': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'From Date (e.g. 27)'}),
            'to_date': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'To Date (e.g. 26)'}),
            'max_leave_balance': forms.NumberInput(attrs={'class': 'form-control'}),
            'earned_leaves_per_year': forms.NumberInput(attrs={'class': 'form-control'}),
            'grace_period_minutes': forms.NumberInput(attrs={'class': 'form-control'}),
            'pf_percentage': forms.NumberInput(attrs={'class': 'form-control'}),
            'esic_percentage': forms.NumberInput(attrs={'class': 'form-control'}),
            'gratuity_percentage': forms.NumberInput(attrs={'class': 'form-control'}),
            'professional_tax': forms.NumberInput(attrs={'class': 'form-control'}),
            'bonus_percentage': forms.NumberInput(attrs={'class': 'form-control'}),
            'basic_percentage': forms.NumberInput(attrs={'class': 'form-control'}),
            'hra_percentage': forms.NumberInput(attrs={'class': 'form-control'}),
            'basic_cap': forms.NumberInput(attrs={'class': 'form-control'}),
        }


class LeaveSettingsForm(forms.ModelForm):
    class Meta:
        model = LeaveSettings
        fields = '__all__'
        widgets = {
            'carry_forward': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'reset_month': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Month (1-12)'}),
        }




class LeaveCreditPolicyForm(forms.ModelForm):
    class Meta:
        model = LeaveCreditPolicy
        fields = [
            "credit_1_limit", "credit_2_limit",
            "credit_low", "credit_mid", "credit_high"
        ]
        widgets = {
            "credit_1_limit": forms.NumberInput(attrs={"class": "form-control"}),
            "credit_2_limit": forms.NumberInput(attrs={"class": "form-control"}),
            "credit_low": forms.NumberInput(attrs={"class": "form-control"}),
            "credit_mid": forms.NumberInput(attrs={"class": "form-control"}),
            "credit_high": forms.NumberInput(attrs={"class": "form-control"}),
        }
