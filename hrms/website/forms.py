from django import forms
from .models import *
from django.forms import inlineformset_factory,DateInput
from django.db.models import Q


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
            'use_department_defaults', 'reporting_person', 'manager',
            'date_of_joining', 'date_of_confirmation', 'location', 'shift_start_time', 'shift_end_time',
            'week_off_day',
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
            'shift_start_time': forms.TimeInput(attrs={'type': 'time'}),
            'shift_end_time': forms.TimeInput(attrs={'type': 'time'}),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
        # Archived branches/companies shouldn't be offered for a new
        # assignment, but an employee already pointing at one (since
        # archived) must keep it selectable so saving the form doesn't
        # silently blank the field out.
        self.fields['branch'].queryset = Branch.objects.filter(
            Q(is_active=True) | Q(pk=self.instance.branch_id)
        )
        self.fields['company'].queryset = Company.objects.filter(
            Q(status='active') | Q(pk=self.instance.company_id)
        )

        # ── Department & reporting line ────────────────────────────────
        # Department is stored as a name (a CharField predating the
        # Department model), so this is a dropdown of defined department
        # names rather than a ModelChoiceField. Any legacy free-text value
        # already on the record stays selectable so editing an employee
        # can't silently blank out their department.
        dept_names = list(
            Department.objects.filter(is_active=True).values_list('name', flat=True)
        )
        current_dept = (self.instance.department or '').strip()
        if current_dept and current_dept.lower() not in {n.lower() for n in dept_names}:
            dept_names.append(current_dept)
        self.fields['department'] = forms.ChoiceField(
            choices=[('', '--- Select Department ---')] + [(n, n) for n in sorted(dept_names)],
            required=False, label='Department',
        )
        self.fields['department'].widget.attrs['class'] = 'form-control'

        # Approvers must be real, currently-employed people, and nobody can
        # approve their own requests.
        approver_qs = Employee.objects.filter(status='Active').order_by('first_name', 'last_name')
        if self.instance.pk:
            approver_qs = approver_qs.exclude(pk=self.instance.pk)
        for field_name in ('reporting_person', 'manager'):
            self.fields[field_name].queryset = approver_qs
            self.fields[field_name].required = False
            self.fields[field_name].widget.attrs['class'] = 'form-control'

        # Rendered as a real checkbox, not a text input.
        self.fields['use_department_defaults'].widget = forms.CheckboxInput(
            attrs={'class': 'form-check-input'}
        )

    def clean(self):
        cleaned = super().clean()
        # A disabled input submits nothing, so when the employee follows
        # their department the posted reporting person/manager is ignored
        # outright and taken from the department instead -- the form must
        # not be the thing that decides this, since the disabled state is
        # only a client-side convenience.
        if cleaned.get('use_department_defaults'):
            department = Department.objects.filter(
                name__iexact=(cleaned.get('department') or '').strip(), is_active=True
            ).first()
            if department is not None:
                cleaned['reporting_person'] = department.reporting_person
                cleaned['manager'] = department.manager
        return cleaned



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
        fields = ['id', 'file_name', 'other_file_name', 'file']
        widgets = {
            'file_name': forms.Select(attrs={
                'class': 'form-control attachment-type',
            }),
            'other_file_name': forms.TextInput(attrs={
                'class': 'form-control',
                'style': 'min-width:260px;',
                'placeholder': 'Enter document name'
            })
        }


EmployeeAttachmentFormSet = inlineformset_factory(
    Employee,
    EmployeeAttachment,
    form=EmployeeAttachmentForm,
    extra=1,
    can_delete=True
)



AttachmentFormSet = inlineformset_factory(
    Employee,
    EmployeeAttachment,
    form=EmployeeAttachmentForm,
    extra=1,
    can_delete=True
)

# AttachmentFormSet = inlineformset_factory(
#     Employee, EmployeeAttachment,
#     fields=['file'], extra=1, can_delete=True
# )


# class PreviousEmploymentAttachmentForm(forms.ModelForm):
#     class Meta:
#         model = PreviousEmploymentAttachment
#         fields = ['file', 'document_name']


# PreviousEmploymentAttachmentFormSet = inlineformset_factory(
#     PreviousEmployment,
#     PreviousEmploymentAttachment,
#     form=PreviousEmploymentAttachmentForm,
#     extra=1,
#     can_delete=True
# )


# class EmployeeEditForm(forms.ModelForm):
#     class Meta:
#         model = Employee
#         fields = "__all__"

#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         for field in self.fields.values():
#             field.widget.attrs['class'] = 'form-control'

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
            'branch_name',
            'branch_address',
        ]
        widgets = {
            'branch_name': forms.TextInput(attrs={'class':'form-control'}),
            'branch_address': forms.Textarea(attrs={'class':'form-control', "rows": 4}),
        }

        
class OffboardingForm(forms.ModelForm):
    class Meta:
        model = Offboarding
        fields = [
            'employee', 'date_of_resignation', 'date_of_relieving',
            'experience_certificate', 'relieving_letter', 'other_documents', 'fnf_documents'
        ]
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-control'}),
            'date_of_resignation': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'date_of_relieving': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'experience_certificate': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'relieving_letter': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'other_documents': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'fnf_documents': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        resignation = cleaned_data.get('date_of_resignation')
        relieving = cleaned_data.get('date_of_relieving')
        if resignation and relieving and relieving < resignation:
            self.add_error('date_of_relieving', 'Date of relieving cannot be before date of resignation.')
        return cleaned_data

class AssetHandoverForm(forms.ModelForm):
    class Meta:
        model = AssetHandover
        fields = [
            'asset_type', 'quantity', 'condition_on_return',
            'remarks', 'asset_photo', 'receipt', 'returned'
        ]
        widgets = {
            'asset_type': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Laptop'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'condition_on_return': forms.Select(attrs={'class': 'form-control'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'asset_photo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'receipt': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'returned': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

AssetHandoverFormSet = inlineformset_factory(
    Offboarding,
    AssetHandover,
    form=AssetHandoverForm,
    extra=1,
    can_delete=True
)


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = "__all__"
        widgets = {
            "short_name": forms.TextInput(attrs={"class": "form-control"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
         "phone": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "tan_number": forms.TextInput(attrs={"class": "form-control"}),
            "pan_number": forms.TextInput(attrs={"class": "form-control"}),
            "employer_pf": forms.TextInput(attrs={"class": "form-control"}),
            "ptrc_number": forms.TextInput(attrs={"class": "form-control"}),
            "ptec_number": forms.TextInput(attrs={"class": "form-control"}),
            "esic_number": forms.TextInput(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }




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



class LeaveApplicationForm(forms.ModelForm):
    class Meta:
        model = LeaveApplication
        fields = ['employee', 'leave_type', 'start_date', 'end_date', 'reason']
        widgets = {
            'employee': forms.Select(attrs={'class':'form-control'}),
            'leave_type': forms.Select(attrs={'class':'form-control'}),
            'start_date': forms.DateInput(attrs={'type':'date','class':'form-control'}),
            'end_date': forms.DateInput(attrs={'type':'date','class':'form-control'}),
            'reason': forms.Textarea(attrs={'class':'form-control','rows':3}),
        }





class AdvanceCreateForm(forms.ModelForm):
    class Meta:
        model = AdvanceMaster
        fields = ['employee', 'advance_amount', 'default_months', 'start_date']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
        }

class PaymentForm(forms.Form):
    amount = forms.IntegerField(min_value=1, label="Amount (₹)")
    note = forms.CharField(widget=forms.Textarea(attrs={'rows':2}), required=False)

class SkipMonthForm(forms.Form):
    # expects due_month in YYYY-MM-DD (first of month)
    due_month = forms.DateField(widget=forms.HiddenInput())











# forms.py - Holiday Calendar Forms

from django import forms
from django.forms import inlineformset_factory
from .models import (
    Holiday,
    HolidayCalendar,
    HolidayType,
    MonthlyEarnedLeaves,
    HalfDayScenario,
    PayrollSettings,
)
from datetime import date


class HolidayForm(forms.ModelForm):
    """Form for creating/editing holidays"""
    
    class Meta:
        model = Holiday
        fields = ['holiday_date', 'name', 'holiday_type', 'status', 'description', 'is_national', 'applies_to_all_employees']
        widgets = {
            'holiday_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control',
                'min': date.today().isoformat(),
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Republic Day',
            }),
            'holiday_type': forms.Select(attrs={
                'class': 'form-control',
            }),
            'status': forms.Select(attrs={
                'class': 'form-control',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Add any additional details...',
            }),
            'is_national': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'applies_to_all_employees': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Archived holiday types shouldn't be offered for a new holiday, but
        # one already using an archived type must stay selectable so saving
        # the form doesn't silently blank the field out.
        self.fields['holiday_type'].queryset = HolidayType.objects.filter(
            Q(is_active=True) | Q(pk=self.instance.holiday_type_id)
        )

    def clean_holiday_date(self):
        holiday_date = self.cleaned_data.get('holiday_date')

        if holiday_date and holiday_date < date.today():
            raise forms.ValidationError(
                'Holiday date cannot be in the past.'
            )

        # Check if an active holiday already exists for this date -- an
        # archived one on the same date is fine to co-exist with (matches
        # the unique_active_holiday_date DB constraint).
        existing = Holiday.objects.filter(
            holiday_date=holiday_date, is_active=True
        ).exclude(id=self.instance.id)

        if existing.exists():
            raise forms.ValidationError(
                f'A holiday already exists for {holiday_date.strftime("%B %d, %Y")}.'
            )
        
        return holiday_date
    
    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        
        if not name:
            raise forms.ValidationError('Holiday name is required.')
        
        if len(name) < 3:
            raise forms.ValidationError('Holiday name must be at least 3 characters long.')
        
        if len(name) > 200:
            raise forms.ValidationError('Holiday name must not exceed 200 characters.')
        
        return name


class HolidayCalendarForm(forms.ModelForm):
    """Form for creating/editing holiday calendars"""
    
    class Meta:
        model = HolidayCalendar
        fields = ['branch', 'year', 'name', 'description', 'is_active']
        widgets = {
            'branch': forms.Select(attrs={
                'class': 'form-control',
            }),
            'year': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': date.today().year,
                'max': date.today().year + 10,
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Mumbai Holiday Calendar 2025',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }
    
    def clean_year(self):
        year = self.cleaned_data.get('year')
        
        if year < date.today().year:
            raise forms.ValidationError('Year cannot be in the past.')
        
        if year > date.today().year + 10:
            raise forms.ValidationError('Year must be within the next 10 years.')
        
        return year


class MonthlyEarnedLeavesForm(forms.ModelForm):
    """Form for editing monthly earned leaves"""
    
    class Meta:
        model = MonthlyEarnedLeaves
        fields = ['earned_leaves', 'is_auto_generated']
        widgets = {
            # ✅ FIXED: Use NumberInput instead of DecimalInput
            'earned_leaves': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.5',
                'min': '0',
                'max': '31',
                'type': 'number',  # Explicitly set type
            }),
            'is_auto_generated': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }
    
    def clean_earned_leaves(self):
        earned_leaves = self.cleaned_data.get('earned_leaves')
        
        if earned_leaves < 0:
            raise forms.ValidationError('Earned leaves cannot be negative.')
        
        if earned_leaves > 31:
            raise forms.ValidationError('Earned leaves cannot exceed 31 days per month.')
        
        return earned_leaves



class HalfDayScenarioForm(forms.ModelForm):
    """Form for creating/editing half-day scenarios"""
    
    class Meta:
        model = HalfDayScenario
        fields = ['scenario_date', 'scenario_type', 'description', 'credit_count', 'is_approved']
        widgets = {
            'scenario_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control',
            }),
            'scenario_type': forms.Select(attrs={
                'class': 'form-control',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'e.g., Heavy rain closure',
            }),
            # ✅ FIXED: Use NumberInput instead of DecimalInput
            'credit_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.5',
                'min': '0.5',
                'max': '1.0',
                'type': 'number',
            }),
            'is_approved': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }
    
    def clean_scenario_date(self):
        scenario_date = self.cleaned_data.get('scenario_date')
        
        if scenario_date and scenario_date < date.today():
            raise forms.ValidationError(
                'Scenario date cannot be in the past.'
            )
        
        return scenario_date
    
    def clean_description(self):
        description = self.cleaned_data.get('description', '').strip()
        
        if not description:
            raise forms.ValidationError('Description is required.')
        
        if len(description) > 500:
            raise forms.ValidationError('Description must not exceed 500 characters.')
        
        return description
    
    def clean_credit_count(self):
        credit_count = self.cleaned_data.get('credit_count')
        
        if credit_count not in [0.5, 1.0]:
            raise forms.ValidationError('Credit count must be either 0.5 or 1.0 days.')
        
        return credit_count


class BulkHolidayImportForm(forms.Form):
    """Form for bulk importing holidays from CSV/Excel"""
    
    csv_file = forms.FileField(
        label='CSV/Excel File',
        help_text='File should contain columns: holiday_date, name, holiday_type, status',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.csv,.xlsx,.xls',
        })
    )
    
    year = forms.IntegerField(
        label='Year',
        initial=date.today().year,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': date.today().year,
        })
    )
    
    is_national = forms.BooleanField(
        label='Apply to All Branches (National)',
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
        })
    )
    
    def clean_csv_file(self):
        csv_file = self.cleaned_data.get('csv_file')
        
        if csv_file:
            # Check file size (max 5MB)
            if csv_file.size > 5 * 1024 * 1024:
                raise forms.ValidationError('File size must not exceed 5MB.')
            
            # Check file extension
            allowed_extensions = ['.csv', '.xlsx', '.xls']
            file_name = csv_file.name
            if not any(file_name.endswith(ext) for ext in allowed_extensions):
                raise forms.ValidationError('File must be CSV or Excel format.')
        
        return csv_file


class PayrollSettingsForm(forms.ModelForm):
    """Form for configuring payroll settings"""
    
    class Meta:
        model = PayrollSettings
        fields = [
            'is_auto',
            'from_date',
            'to_date',
            'grace_period_minutes',
            'max_leave_balance',
            'earned_leaves_per_year',
            'financial_year_start_month',
            'carry_forward',
            'reset_month',
            'pf_percentage',
            'esic_percentage',
            'gratuity_percentage',
            'professional_tax',
            'basic_percentage',
            'hra_percentage',
            'basic_cap',
        ]
        widgets = {
            'is_auto': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'from_date': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'max': '31',
                'placeholder': 'Day of month',
            }),
            'to_date': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'max': '31',
                'placeholder': 'Day of month',
            }),
            'grace_period_minutes': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': 'Minutes',
            }),
            'max_leave_balance': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
            }),
            'earned_leaves_per_year': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '365',
            }),
            'financial_year_start_month': forms.Select(
                choices=[(i, ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][i-1]) for i in range(1, 13)],
                attrs={
                    'class': 'form-control',
                }
            ),
            'carry_forward': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'reset_month': forms.Select(
                choices=[(None, 'None')] + [(i, ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][i-1]) for i in range(1, 13)],
                attrs={
                    'class': 'form-control',
                }
            ),
            # ✅ FIXED: Use NumberInput with step for decimal values
            'pf_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '100',
                'type': 'number',
            }),
            'esic_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '100',
                'type': 'number',
            }),
            'gratuity_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '100',
                'type': 'number',
            }),
            'professional_tax': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'type': 'number',
            }),
            'basic_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '100',
                'type': 'number',
            }),
            'hra_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '100',
                'type': 'number',
            }),
            'basic_cap': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'type': 'number',
            }),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        
        is_auto = cleaned_data.get('is_auto')
        from_date = cleaned_data.get('from_date')
        to_date = cleaned_data.get('to_date')
        
        if not is_auto:
            if not from_date or not to_date:
                raise forms.ValidationError(
                    'From Date and To Date are required for manual payroll periods.'
                )
            
            if from_date >= to_date:
                raise forms.ValidationError(
                    'To Date must be after From Date.'
                )
        
        return cleaned_data
