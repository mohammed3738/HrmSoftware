from django.db import models
from django.utils.timezone import now
import datetime
from django.core.validators import MinValueValidator, MaxValueValidator
from datetime import date, timedelta
from django.conf import settings
import datetime
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.db.models import JSONField  # for PostgreSQL
from decimal import Decimal
from django.contrib.auth.models import User

# Create your models here.
status = {
    'Active':'active',
    'InActive':'inactive',
}
class Company(models.Model):
    short_name = models.CharField(max_length=10, unique=True, verbose_name="Short Name")  # ZC, UI, etc.
    name = models.CharField(max_length=100, verbose_name="Company Name")  # Full company name
    phone = models.CharField(max_length=15, verbose_name="Phone Number")  # Contact phone number
    email = models.EmailField(verbose_name="Email")  # Contact email
    address = models.TextField(verbose_name="Company Address")  # Full address
    tan_number = models.CharField(max_length=20, blank=True, null=True, verbose_name="TAN Number")  # TAN No
    pan_number = models.CharField(max_length=20, blank=True, null=True, verbose_name="PAN Number")  # PAN No
    employer_pf = models.CharField(max_length=20, blank=True, null=True, verbose_name="Employer PF Number")  # Employer PF
    ptrc_number = models.CharField(max_length=20, blank=True, null=True, verbose_name="PTRC Number")  # PTRC
    ptec_number = models.CharField(max_length=20, blank=True, null=True, verbose_name="PTEC Number")  # PTEC
    esic_number = models.CharField(max_length=20, blank=True, null=True, verbose_name="ESIC Number")  # ESIC No
    status = models.CharField(max_length=50, choices=status, default='active')
    def __str__(self):
        return f"{self.short_name} - {self.name}"


class Branch(models.Model):
    branch_name= models.CharField(max_length=100)
    branch_address = models.TextField(verbose_name="Branch Address", blank=True, null=True,)  # Full address
    def __str__(self):
        return f"{self.branch_name}"
    

BLOOD_GROUP_CHOICES = [
    ("A+", "A+"),
    ("A-", "A-"),
    ("B+", "B+"),
    ("B-", "B-"),
    ("AB+", "AB+"),
    ("AB-", "AB-"),
    ("O+", "O+"),
    ("O-", "O-"),
    ("Others", "Others"),
]

SALUTATION_CHOICES = [
    ("Mr.", "Mr."),
    ("Mrs.", "Mrs."),
    ("Ms.", "Ms."),
    ("Dr.", "Dr."),
    ("Prof.", "Prof."),
]


class Employee(models.Model):

    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employee_profile"
    )
    force_password_change = models.BooleanField(default=True)

    # Personal Details
    company = models.ForeignKey("Company",null=True, blank=True, on_delete=models.CASCADE)
    branch = models.ForeignKey("Branch",null=True, blank=True, on_delete=models.CASCADE)
    salutation = models.CharField(max_length=10, choices=SALUTATION_CHOICES, null=True, blank=True, verbose_name="Salutation")
    first_name = models.CharField(max_length=100, null=True, blank=True, verbose_name="First Name")
    middle_name = models.CharField(max_length=100, null=True, blank=True, verbose_name="Middle Name")
    last_name = models.CharField(max_length=100, null=True, blank=True, verbose_name="Last Name")
    father_name = models.CharField(max_length=100, null=True, blank=True, verbose_name="Father's Name")
    gender = models.CharField(max_length=15, choices=[("Male", "Male"), ("Female", "Female")], null=True, blank=True, verbose_name="Gender")
    blood_group = models.CharField(max_length=10, null=True, blank=True, verbose_name="Blood Group", choices=BLOOD_GROUP_CHOICES)
    date_of_birth = models.DateField(null=True, blank=True, verbose_name="Date of Birth")
    place_of_birth = models.CharField(max_length=255, null=True, blank=True, verbose_name="Place of Birth")
    personal_email = models.EmailField(null=True, blank=True, verbose_name="Personal Email ID")
    present_address = models.TextField(null=True, blank=True, verbose_name="Present Address")
    permanent_address = models.TextField(null=True, blank=True, verbose_name="Permanent Address")
    personal_mobile = models.CharField(max_length=30, null=True, blank=True, verbose_name="Personal Mobile No")
    date_of_marriage = models.DateField(blank=True, null=True, verbose_name="Date of Marriage")

    # ZCPL Office Details
    employee_code = models.CharField(max_length=50, unique=True, null=True, blank=True, verbose_name="Employee Code")
    designation = models.CharField(max_length=100, null=True, blank=True, verbose_name="Designation")
    department = models.CharField(max_length=100, null=True, blank=True, verbose_name="Department")
    date_of_joining = models.DateField(null=True, blank=True, verbose_name="Date of Joining")
    date_of_confirmation = models.DateField(blank=True, null=True, verbose_name="Date of Confirmation")
    location = models.CharField(max_length=255, null=True, blank=True, verbose_name="Location")
    shift_start_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Shift Start Time"
    )
    shift_end_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Shift End Time"
    )

    # Statutory Details
    pan_no = models.CharField(max_length=30, null=True, blank=True, verbose_name="PAN No")
    aadhar_no = models.CharField(max_length=30, null=True, blank=True, verbose_name="Aadhar No")
    voter_id = models.CharField(max_length=30, null=True, blank=True, verbose_name="Voter ID")
    passport = models.CharField(max_length=30, null=True, blank=True, verbose_name="Passport")
    uan_no = models.CharField(max_length=30, null=True, blank=True, verbose_name="Universal Account No. (UAN)")
    pf_no = models.CharField(max_length=30, null=True, blank=True, verbose_name="PF No")
    esic_no = models.CharField(max_length=30, null=True, blank=True, verbose_name="ESIC No")

    # Banking Details
    name_as_per_bank = models.CharField(max_length=100, null=True, blank=True, verbose_name="Name As Per Bank Record")
    salary_account_number = models.CharField(max_length=30, null=True, blank=True, verbose_name="Salary Account Number")
    ifsc_code = models.CharField(max_length=30, null=True, blank=True, verbose_name="IFSC Code")
    # assets
    # assets = models.ManyToManyField('Asset', related_name='assigned_employees',null=True, blank=True, verbose_name="Assigned Assets")

    # Emergency Contact Details
    emergency_contact_name1 = models.CharField(max_length=100, null=True, blank=True, verbose_name="Emergency Contact Name 1")
    emergency_contact_relation1 = models.CharField(
        max_length=50,
        choices=[("Spouse", "Spouse"), ("Father", "Father"), ("Mother", "Mother"),
                 ("Brother", "Brother"), ("Sister", "Sister"), ("Son", "Son"),
                 ("Daughter", "Daughter"), ("Other", "Other")],
        null=True, blank=True,
        verbose_name="Emergency Contact Relation 1"
    )
    emergency_contact_mobile1 = models.CharField(max_length=30, null=True, blank=True, verbose_name="Emergency Contact Mobile No 1")
    emergency_contact_name2 = models.CharField(max_length=100, null=True, blank=True, verbose_name="Emergency Contact Name 2")
    emergency_contact_relation2 = models.CharField(
        max_length=50,
        choices=[("Spouse", "Spouse"), ("Father", "Father"), ("Mother", "Mother"),
                 ("Brother", "Brother"), ("Sister", "Sister"), ("Son", "Son"),
                 ("Daughter", "Daughter"), ("Other", "Other")],
        null=True, blank=True,
        verbose_name="Emergency Contact Relation 2"
    )
    emergency_contact_mobile2 = models.CharField(max_length=30, null=True, blank=True, verbose_name="Emergency Contact Mobile No 2")
    status = models.CharField(max_length=50, choices=[("Active", "Active"), ("Pending", "Pending"), ("Left", "Left")] , default='Active')
    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class PreviousEmployment(models.Model):
    employee = models.ForeignKey(Employee, related_name="previous_employments", on_delete=models.CASCADE)
    employer_name = models.CharField(max_length=100, verbose_name="Employer Name")
    from_date = models.DateField(verbose_name="From")
    to_date = models.DateField(verbose_name="To")
    last_ctc = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Last CTC p.a")

    def __str__(self):
        return f"{self.employer_name} ({self.employee})"


class PreviousEmploymentAttachment(models.Model):
    previous_employment = models.ForeignKey(
        PreviousEmployment,
        related_name="documents",
        on_delete=models.CASCADE
    )
    file = models.FileField(upload_to="previous_employment_docs/")
    document_name = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.document_name or 'Document'} - {self.previous_employment.employer_name}"


class EmployeeAttachment(models.Model):
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="attachments"
    )
    file = models.FileField(upload_to="employee_attachments/")
    FILE_NAME_CHOICES = [
        ('aadhaar', 'Aadhaar'),
        ('pan', 'PAN'),
        ('resume', 'Resume'),
        ('offer_letter', 'Offer Letter'),
        ('other', 'Other'),

        # add more
    ]
    other_file_name = models.CharField(
        max_length=255,
        null=True,
        blank=True
    )

    file_name = models.CharField(max_length=50, choices=FILE_NAME_CHOICES, blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def get_display_name(self):
        if self.file_name == "other" and self.other_file_name:
            return self.other_file_name
        return dict(self.FILE_NAME_CHOICES).get(self.file_name, "Document")

    def __str__(self):
        return f"{self.get_display_name()} - {self.employee}"

 
#     def __str__(self):
#         return f"{self.asset_name} ({self.assigned_to})"


class Offboarding(models.Model):
    employee = models.ForeignKey(Employee, related_name="offboarding", on_delete=models.CASCADE)
    date_of_resignation = models.DateField(verbose_name="Date of Resignation")
    date_of_relieving = models.DateField(verbose_name="Date of Relieving")
    experience_certificate = models.FileField(upload_to="offboarding/certificates/", verbose_name="Experience Certificate", blank=True , null=True)
    relieving_letter = models.FileField(upload_to="offboarding/relieving_letters/", verbose_name="Relieving Letter", blank=True , null=True)
    other_documents = models.FileField(upload_to="offboarding/other_documents/", blank=True, null=True, verbose_name="Other Documents")
    fnf_documents = models.FileField(upload_to="offboarding/fnf/", blank=True, null=True, verbose_name="FNF Document")

    def __str__(self):
        return f"Offboarding for {self.employee}"


# New model for Asset handover
class AssetHandover(models.Model):
    CONDITION_CHOICES = [
        ('Good', 'Good'),
        ('Damaged', 'Damaged'),
        ('Missing', 'Missing'),
    ]

    offboarding = models.ForeignKey(Offboarding, related_name="asset_handovers", on_delete=models.CASCADE)
    asset_type = models.CharField(max_length=100, verbose_name="Asset Type")
    quantity = models.PositiveIntegerField(default=1, verbose_name="Quantity")
    condition_on_return = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='Good', verbose_name="Condition on Return")
    remarks = models.TextField(blank=True, null=True, verbose_name="Remarks")
    asset_photo = models.FileField(upload_to="offboarding/asset_photos/", blank=True, null=True, verbose_name="Asset Photo")
    receipt = models.FileField(upload_to="offboarding/asset_receipts/", blank=True, null=True, verbose_name="Receipt / Proof")
    returned = models.BooleanField(default=True, verbose_name="Returned?")  # checkbox

    def __str__(self):
        return f"{self.asset_type} x{self.quantity} ({self.offboarding})"


    # employee_status = models.CharField(
    #     max_length=10,
    #     choices=[("Active", "Active"), ("Left", "Left")],
    #     default="Left",
    #     verbose_name="Employee Status"
    # )


class SalaryMaster(models.Model):
    # Dropdowns
    employee = models.ForeignKey(Employee,null=True,blank=True,on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True,null=True, blank=True)  # To flag current active salary
    effective_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    pf_deducted = models.BooleanField(default=False,null=True, blank=True, verbose_name="PF Deducted/Not Deducted")
    gratuity_applicable = models.BooleanField(default=False,null=True, blank=True, verbose_name="Gratuity Applicable")
    esic_applicable = models.BooleanField(default=False,null=True, blank=True, verbose_name="ESIC Applicable")

    # Salary Components (Monthly and Annually)
    gross_ctc_pm = models.DecimalField(max_digits=10, decimal_places=2,null=True, blank=True, verbose_name="Gross CTC (P.M)")
    gross_ctc_pa = models.DecimalField(max_digits=10, decimal_places=2,null=True, blank=True, verbose_name="Gross CTC (P.A)")
    basic_pm = models.DecimalField(max_digits=10, decimal_places=2,null=True, blank=True, verbose_name="Basic (P.M)")
    basic_pa = models.DecimalField(max_digits=10, decimal_places=2,null=True, blank=True, verbose_name="Basic (P.A)")
    hra_pm = models.DecimalField(max_digits=10, decimal_places=2,null=True, blank=True, verbose_name="HRA (P.M)")
    hra_pa = models.DecimalField(max_digits=10, decimal_places=2,null=True, blank=True, verbose_name="HRA (P.A)")
    sp_allowance_pm = models.DecimalField(max_digits=10, decimal_places=2,null=True, blank=True, verbose_name="Special Allowance (P.M)")
    sp_allowance_pa = models.DecimalField(max_digits=10, decimal_places=2,null=True, blank=True, verbose_name="Special Allowance (P.A)")
    allowance1_pm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Allowance 1 (P.M)")
    allowance1_pa = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Allowance 1 (P.A)")
    allowance2_pm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Allowance 2 (P.M)")
    allowance2_pa = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Allowance 2 (P.A)")
    stat_bonus_pm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Stat Bonus (P.M)")
    stat_bonus_pa = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Stat Bonus (P.A)")

    # Guaranteed Cash
    guaranteed_cash_pm = models.DecimalField(max_digits=10, decimal_places=2,null=True, blank=True, verbose_name="Guaranteed Cash (P.M)")
    guaranteed_cash_pa = models.DecimalField(max_digits=10, decimal_places=2,null=True, blank=True, verbose_name="Guaranteed Cash (P.A)")
    gratuity_pm = models.DecimalField(max_digits=10, decimal_places=2,null=True, blank=True, verbose_name="Gratuity (P.M)")
    gratuity_pa = models.DecimalField(max_digits=10, decimal_places=2,null=True, blank=True, verbose_name="Gratuity (P.A)")

    # Cost to Company
    ctc_pm = models.DecimalField(max_digits=10, decimal_places=2,null=True, blank=True, verbose_name="Cost to Company (P.M)")
    ctc_pa = models.DecimalField(max_digits=10, decimal_places=2,null=True, blank=True, verbose_name="Cost to Company (P.A)")

    # Deductions
    pf_er_cont_pm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="PF (Employer Contribution P.M)")
    pf_er_cont_pa = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="PF (Employer Contribution P.A)")
    esic_er_cont_pm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="ESIC (Employer Contribution P.M)")
    esic_er_cont_pa = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="ESIC (Employer Contribution P.A)")
    pf_ee_cont_pm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="PF (Employee Contribution P.M)")
    pf_ee_cont_pa = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="PF (Employee Contribution P.A)")
    esic_ee_cont_pm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="ESIC (Employee Contribution P.M)")
    esic_ee_cont_pa = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="ESIC (Employee Contribution P.A)")
    # Profession Tax
    profession_tax_pm = models.DecimalField(max_digits=10, decimal_places=2,null=True, blank=True,    verbose_name="Profession Tax (P.M)")
    profession_tax_pa = models.DecimalField(max_digits=10, decimal_places=2,null=True, blank=True,    verbose_name="Profession Tax (P.A)")

    # Net Salary
    net_salary_pm = models.DecimalField(max_digits=10, decimal_places=2,null=True, blank=True, verbose_name="Net Salary (P.M)")
    net_salary_pa = models.DecimalField(max_digits=10, decimal_places=2,null=True, blank=True, verbose_name="Net Salary (P.A)")
    def __str__(self):
        return f"Offboarding for {self.employee} - {self.gross_ctc_pm}"




# atul

class LeaveApplication(models.Model):
    LEAVE_TYPES = [
        ("CL", "Casual Leave"),
        ("SL", "Sick Leave"),
        ("PL", "Paid Leave"),
        ("COFF", "Comp-Off Adjustment"),
        ("LWP", "Leave Without Pay"),
    ]

    employee = models.ForeignKey("Employee", on_delete=models.CASCADE)
    leave_type = models.CharField(max_length=10, choices=LEAVE_TYPES)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=10, default="Pending")   # Pending / Approved / Rejected
    applied_on = models.DateTimeField(auto_now_add=True)

    def total_days(self):
        return (self.end_date - self.start_date).days + 1

    def __str__(self):
        return f"{self.employee} - {self.leave_type} ({self.start_date} to {self.end_date})"



# atul



class LeaveRecord(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="leave_records")
    opening_balance = models.FloatField(default=0.0)
    leave_taken = models.FloatField(default=0.0)
    days_present = models.IntegerField(default=0)
    total_days = models.IntegerField(default=0)
    late_days = models.IntegerField(default=0)  
    comp_off = models.FloatField(default=0.0)  # Compensation off days
    leave_without_pay = models.FloatField(default=0.0)
    closing_balance = models.FloatField(default=0.0)  # Computed later
    leave_balance = models.FloatField(default=0.0)  # Computed later

    def __str__(self):
        return f"{self.employee.name} - Leave Record"


class LeaveSettings(models.Model):
    company = models.OneToOneField(
        'Company',
        on_delete=models.CASCADE,
        null=True,   # remove after migration
        blank=True,
    )

    carry_forward = models.BooleanField(default=True)
    reset_month = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        null=True, blank=True    
    )

    # 🕒 Timestamp fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Carry Forward: {'Yes' if self.carry_forward else 'No'} | Reset Month: {self.reset_month or 'N/A'}"


class CompOff(models.Model):
    employee = models.ForeignKey("Employee", on_delete=models.CASCADE)
    from_date = models.DateField()  # Start date of comp-off
    to_date = models.DateField()  # End date of comp-off
    reason = models.TextField()  # Reason for comp-off

    def __str__(self):
        return f"{self.employee.name} ({self.employee.code}) - {self.from_date} to {self.to_date}"


class CompOffRequest(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    # applied_date = models.DateField(auto_now_add=True)  # When the request was made
    # requested_date = models.DateField()  # The date employee wants a comp-off
    from_date = models.DateField(null=True, blank=True)
    to_date = models.DateField(null=True, blank=True)
    reason = models.TextField(null=True, blank=True)
    rejection_reason = models.TextField(null=True, blank=True)
    count = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    status = models.CharField(
        max_length=20,
        choices=[('Pending', 'Pending'), ('Approved', 'Approved'), ('Rejected', 'Rejected')],
        default='Pending'
    )

    def save(self, *args, **kwargs):
        if self.from_date and self.to_date:
            self.count = (self.to_date - self.from_date).days + 1
        super().save(*args, **kwargs)


    def __str__(self):
        return f"CompOff Request - {self.employee.first_name} on {self.from_date}"


class LeaveBalance(models.Model):
    employee = models.ForeignKey("Employee", on_delete=models.CASCADE)
    opening_balance = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    leave_taken = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    number_of_days_present = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    total_number_of_days = models.IntegerField(default=0)
    late = models.IntegerField(default=0)
    # compoff = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    compoff = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    # compoff = models.ForeignKey("CompOffRequest", on_delete=models.CASCADE, null=True, blank=True)
    leave_without_pay = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    closing_balance = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    leave_balance = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    final_leave_balance = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))

    period_from_date = models.DateField(null=True, blank=True)
    period_to_date = models.DateField(null=True, blank=True)

    lwp_overridden = models.BooleanField(
        default=False,
        help_text="If True, LWP was manually set and recalculation will preserve it."
    )

    def __str__(self):
        return f"{self.employee.first_name} {self.employee.employee_code} - Leave Balance"


    # def calculate_leave_data(self, from_date, to_date):
    #     """Calculate leave balances based on attendance and settings."""
    #     attendance_records = Attendance.objects.filter(employee=self.employee, date__range=[from_date, to_date])

    #     # Sum up the count for the selected month range
    #     self.number_of_days_present = attendance_records.aggregate(Sum("count"))["count__sum"] or 0

    #     # Total number of days is derived from the selected range
    #     self.total_number_of_days = (to_date - from_date).days + 1

    #     # Leave taken = Total days - Present days
    #     self.leave_taken = self.total_number_of_days - self.number_of_days_present

    #     # Late days calculation
    #     self.late = attendance_records.aggregate(Sum("late"))["late__sum"] or 0

    #     # Compoff from the CompOff model
    #     self.compoff = CompOff.objects.filter(employee=self.employee, date__range=[from_date, to_date]).aggregate(Sum("days"))["days__sum"] or 0

    #     # Calculate LWP & Closing balance
    #     self.leave_without_pay = max(0, self.opening_balance + self.compoff - self.leave_taken - self.late)
    #     self.closing_balance = max(0, self.opening_balance + self.compoff - self.leave_taken - self.late)

    #     # If closing is positive, LWP = 0, else LWP takes the negative value of closing
    #     if self.closing_balance > 0:
    #         self.leave_without_pay = 0
    #     else:
    #         self.leave_without_pay = abs(self.closing_balance)
    #         self.closing_balance = 0

    #     # Leave balance = Closing balance + 2
    #     self.leave_balance = self.closing_balance + 2

    #     self.save()
    
    def __str__(self):
        return f"{self.employee.first_name} - Balance: {self.leave_balance}"

    @property
    def total_period_days(self):
        if self.period_from_date and self.period_to_date:
            return (self.period_to_date - self.period_from_date).days + 1
        return self.total_number_of_days


"""
Add this model to your models.py
This creates a monthly snapshot for historical tracking
"""

class LeaveBalanceHistory(models.Model):
    """
    Monthly snapshot of leave balance
    Allows viewing historical leave data by month
    """
    employee = models.ForeignKey("Employee", on_delete=models.CASCADE)
    month = models.DateField(help_text="First day of the month")
    
    # Same fields as LeaveBalance for historical tracking
    opening_balance = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    leave_taken = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    number_of_days_present = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    total_number_of_days = models.IntegerField(default=0)
    late = models.IntegerField(default=0)
    compoff = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    leave_without_pay = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    closing_balance = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    leave_balance = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    final_leave_balance = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['employee', 'month']
        ordering = ['-month', 'employee']
        indexes = [
            models.Index(fields=['employee', 'month']),
            models.Index(fields=['month']),
        ]
    
    def __str__(self):
        return f"{self.employee.first_name} - {self.month.strftime('%B %Y')}"




class LeaveCreditPolicy(models.Model):
    """
    Defines monthly leave credit rules for each company.
    HR can configure thresholds directly from the Admin panel.
    """
    company = models.OneToOneField("Company", on_delete=models.CASCADE, related_name="leave_credit_policy")
    credit_1_limit = models.PositiveIntegerField(default=15, help_text="Up to this many days present = 0 credit")
    credit_2_limit = models.PositiveIntegerField(default=25, help_text="Up to this many days present = 1 credit")
    
    credit_low = models.DecimalField(max_digits=4, decimal_places=2, default=0, help_text="Leave credit if ≤ first limit (default 0)")
    credit_mid = models.DecimalField(max_digits=4, decimal_places=2, default=1, help_text="Leave credit if between first & second limit (default 1)")
    credit_high = models.DecimalField(max_digits=4, decimal_places=2, default=2, help_text="Leave credit if above second limit (default 2)")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Leave Credit Policy"
        verbose_name_plural = "Leave Credit Policies"

    def __str__(self):
        return f"{self.company.name} Leave Credit Policy"



# class AdvanceMaster(models.Model):
#     employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="advances")
#     total_amount = models.DecimalField(max_digits=10, decimal_places=2)
#     start_month = models.DateField(blank=True, null=True)
#     remarks = models.TextField(blank=True, null=True)
#     created_on = models.DateTimeField(auto_now_add=True)
#     is_closed = models.BooleanField(default=False)

#     def __str__(self):
#         return f"{self.employee} - ₹{self.total_amount}"

#     @property
#     def paid_amount_db(self):
#         return sum(i.amount for i in self.installments.filter(is_paid=True))

#     @property
#     def remaining_amount_db(self):
#         remaining = self.total_amount - self.paid_amount_db
#         return remaining if remaining > 0 else 0


# class AdvanceInstallment(models.Model):
#     advance = models.ForeignKey(AdvanceMaster, on_delete=models.CASCADE, related_name='installments')
#     month = models.DateField()
#     amount = models.DecimalField(max_digits=10, decimal_places=2)
#     is_paid = models.BooleanField(default=False)
#     is_skipped = models.BooleanField(default=False)  #  NEW FIELD
#     paid_on = models.DateField(blank=True, null=True)
#     remarks = models.TextField(blank=True, null=True)

    # def __str__(self):
    #     status = "Paid" if self.is_paid else ("Skipped" if self.is_skipped else "Pending")
    #     return f"{self.advance.employee.first_name} - {self.month} ({status})"



class PayrollSettings(models.Model):
    company = models.OneToOneField("Company", on_delete=models.CASCADE)
    is_auto = models.BooleanField(default=True)
    from_date = models.IntegerField(null=True, blank=True)
    to_date = models.IntegerField(null=True, blank=True)
    max_leave_balance = models.IntegerField(default=15)
    earned_leaves_per_year = models.PositiveIntegerField(default=24)
    grace_period_minutes = models.IntegerField(default=15)


    branch_specific_holidays = models.BooleanField(
        default=True,
        help_text="When True, regional holidays only apply to their specific branch. "
                  "When False, all holidays apply to all branches."
    )

    WEEKEND_CHOICES = [
        ('sat_sun', 'Saturday & Sunday'),
        ('sun', 'Sunday Only'),
    ]
    weekend_days = models.CharField(
        max_length=10,
        choices=WEEKEND_CHOICES,
        default='sat_sun',
        verbose_name="Weekend Days",
        help_text="Which days count as weekends (not worked)."
    )

    financial_year_start_month = models.PositiveIntegerField(
        default=4,  # April (month number 1-12)
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="Financial year start month (1=January, 4=April, etc.)"
    )


    carry_forward = models.BooleanField(default=True)
    reset_month = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        null=True, blank=True
    )

    late_marks_affect_lwp = models.BooleanField(
        default=True,
        help_text="If unchecked, late marks will never deduct from leave balance / cause LWP, regardless of count."
    )

    # Salary master settings
    pf_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=12.00)
    esic_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=3.67)
    gratuity_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=4.61)
    professional_tax = models.DecimalField(max_digits=10, decimal_places=2, default=200.00)
    bonus_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=8.33)

    basic_percentage = models.FloatField(default=50.0)
    hra_percentage = models.FloatField(default=60.0)
    basic_cap = models.FloatField(default=21000.0)

    # 🕒 Timestamp fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_payroll_period(self):
        """
        Return (from_date, to_date) for the current payroll period.
        If from_date and to_date day numbers are set, they take priority over
        is_auto.  is_auto is only the fallback when no day numbers are configured.
        """
        today = date.today()

        from_day = self.from_date
        to_day = self.to_date

        if from_day and to_day:
            # Custom period (e.g. 27 → 26 cross-month, or 1 → 31 same-month)
            if today.day >= from_day:
                start_month = today.month
                start_year = today.year
            else:
                start_month = today.month - 1
                start_year = today.year
                if start_month == 0:
                    start_month = 12
                    start_year -= 1

            if from_day <= to_day:
                end_month = start_month
                end_year = start_year
            else:
                end_month = start_month + 1
                end_year = start_year
                if end_month == 13:
                    end_month = 1
                    end_year += 1

            return date(start_year, start_month, from_day), date(end_year, end_month, to_day)

        # Fallback: calendar month
        first_day = today.replace(day=1)
        next_month = first_day.replace(day=28) + timedelta(days=4)
        last_day = next_month - timedelta(days=next_month.day)
        return first_day, last_day

    def __str__(self):
        return f"Payroll Settings for {self.company.name}"
    


# class SalaryIncrement(models.Model):
#     employee = models.ForeignKey("Employee", on_delete=models.CASCADE)
#     new_gross_ctc_pm = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="New Gross CTC (P.M)")
#     new_gross_ctc_pa = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="New Gross CTC (P.A)")
#     effective_date = models.DateField(null=True, blank=True)
#     is_processed = models.BooleanField(default=False,null=True, blank=True)
#     created_at = models.DateTimeField(auto_now_add=True,null=True, blank=True)

#     def __str__(self):
#         return f"{self.employee} - ₹{self.new_gross_ctc_pm} from {self.effective_date}"

class SalaryIncrement(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)

    effective_date = models.DateField()  
    created_at = models.DateTimeField(auto_now_add=True)

    # Main field: stores all salary values (exact snapshot)
    change_set = JSONField()

    is_processed = models.BooleanField(default=False)

    def __str__(self):
        return f"Increment for {self.employee} effective {self.effective_date}"


class SalaryHistory(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE,null=True, blank=True)
    data = models.JSONField(null=True, blank=True)   # store all salary fields here
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.employee} - {self.start_date} to {self.end_date}"





class AdvanceMaster(models.Model):
    STATUS_ACTIVE = 'active'
    STATUS_COMPLETED = 'completed'
    STATUS_CHOICES = [(STATUS_ACTIVE, 'Active'), (STATUS_COMPLETED, 'Completed')]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='advances')
    advance_amount = models.PositiveIntegerField()  # store in rupees (int)
    start_date = models.DateField(default=timezone.now)
    default_months = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    outstanding_amount = models.IntegerField()  # updated as payments happen

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Advance {self.id} - {self.employee} - ₹{self.advance_amount}"

class AdvanceSchedule(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_PAID = 'paid'
    STATUS_SKIPPED = 'skipped'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PAID, 'Paid'),
        (STATUS_SKIPPED, 'Skipped'),
    ]

    advance = models.ForeignKey(AdvanceMaster, on_delete=models.CASCADE, related_name='schedules')
    due_month = models.DateField()  # use first day of month for the EMI month
    scheduled_amount = models.PositiveIntegerField()  # rupees
    paid_amount = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)

    class Meta:
        ordering = ['due_month']

    def remaining(self):
        return max(0, self.scheduled_amount - self.paid_amount)

    def __str__(self):
        return f"{self.advance} | {self.due_month:%Y-%m} - ₹{self.scheduled_amount} ({self.status})"

class AdvancePayment(models.Model):
    advance = models.ForeignKey(AdvanceMaster, on_delete=models.CASCADE, related_name='payments')
    amount = models.PositiveIntegerField()
    date = models.DateTimeField(default=timezone.now)
    note = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Payment {self.amount} on {self.date.date()} for {self.advance}"






# models.py (append)
from decimal import Decimal
from django.db import models
from django.utils import timezone

class PayrollRun(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_FINALIZED = "finalized"
    STATUS_CHOICES = [(STATUS_DRAFT, "Draft"), (STATUS_FINALIZED, "Finalized")]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True)
    month = models.DateField(help_text="First day of month representing payroll month")
    start_date = models.DateField()
    end_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    class Meta:
        ordering = ["-month"]

    def __str__(self):
        return f"{self.company.short_name if self.company else 'Company'} - Payroll {self.month:%b %Y} [{self.status}]"


class PayrollRecord(models.Model):
    payroll = models.ForeignKey("PayrollRun", on_delete=models.CASCADE, related_name="records")
    employee = models.ForeignKey("Employee", on_delete=models.CASCADE)

    # SECTION 1 - employee master snapshot
    employee_code = models.CharField(max_length=50, blank=True)
    employee_name = models.CharField(max_length=255, blank=True)
    company_name = models.CharField(max_length=255, blank=True)
    designation = models.CharField(max_length=255, blank=True)
    branch_name = models.CharField(max_length=255, blank=True)
    date_of_joining = models.DateField(null=True, blank=True)
    month_display = models.CharField(max_length=20, blank=True)

    # SECTION 2 - salary breakup (monthly)
    gross_ctc = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    opted_for_pf = models.BooleanField(default=False)
    basic_pm = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    hra_pm = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    sp_allowance_pm = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    stat_bonus_pm = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    allowance1_pm = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    allowance2_pm = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    total_gross_salary = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    # SECTION 3 - attendance & leave
    total_days = models.IntegerField(default=0)
    present_days = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    leave_taken = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))

    # NEW: leave_without_pay from LeaveBalance (LWP)
    leave_without_pay = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))

    # SECTION 4 - processed salary (prorated using LWP)
    basic_processed = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    hra_processed = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    sp_allowance_processed = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    stat_bonus_processed = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    allowance1_processed = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    allowance2_processed = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    gross_processed = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    # SECTION 5 - deductions (employee-side editable)
    pf_employee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    professional_tax = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    advance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    esic_employee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    tds = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    other_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    # SECTION 6 - net pay
    net_salary = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    # audit/manual
    manual_override = models.JSONField(default=dict, blank=True)
    calculation_breakdown = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["employee__first_name"]

    def __str__(self):
        # avoid referencing removed fields
        return f"{self.employee} - {self.payroll.month:%b %Y}"
    









class HolidayType(models.Model):
    """
    Holiday type/category for classification
    
    Examples:
    - National Holiday (all branches)
    - Regional/State Holiday (branch-specific)
    - Company Holiday (all branches)
    - Emergency Holiday (branch-specific, add anytime)
    """
    TYPES = [
        ('national', 'National Holiday'),
        ('regional', 'Regional/State Holiday'),
        ('company', 'Company Holiday'),
        ('emergency', 'Emergency Holiday'),
        ('other', 'Other'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    type_category = models.CharField(max_length=20, choices=TYPES, default='national')
    description = models.TextField(blank=True)
    color_code = models.CharField(max_length=7, default='#2196F3',
                                 help_text="Hex color for calendar display")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name_plural = "Holiday Types"
        indexes = [models.Index(fields=['type_category'])]
    
    def __str__(self):
        return self.name


# ============================================
# NEW MODEL 2: HolidayCalendar
# ============================================

class HolidayCalendar(models.Model):
    """
    Holiday calendar specific to a branch and year
    
    Example:
    - Mumbai Branch, 2025
    - Chennai Branch, 2025
    - Delhi Branch, 2025
    
    Each branch has its own holiday calendar!
    """
    branch = models.ForeignKey('Branch', on_delete=models.CASCADE,
                              related_name='holiday_calendars')
    year = models.IntegerField()
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    
    class Meta:
        unique_together = ('branch', 'year')
        ordering = ['-year']
        indexes = [models.Index(fields=['branch', 'year'])]
    
    def __str__(self):
        return f"{self.branch.branch_name} - {self.year}"


# ============================================
# NEW MODEL 3: Holiday
# ============================================

class Holiday(models.Model):
    """
    Individual holidays in a branch calendar
    
    Examples:
    1. National Holiday (all branches):
       - Independence Day (Aug 15)
       - is_national = True
    
    2. Regional Holiday (specific branch):
       - Pongal (Chennai branch only)
       - is_national = False
       - applicable_branches = [Chennai]
    
    3. Ad-hoc Holiday (add anytime, e.g., today/tomorrow):
       - Heavy Rain Closure (Mumbai, today)
       - status = 'emergency'
    """
    HOLIDAY_STATUS = [
        ('declared', 'Declared'),
        ('optional', 'Optional'),
        ('emergency', 'Emergency'),
    ]
    
    holiday_calendar = models.ForeignKey(HolidayCalendar, on_delete=models.SET_NULL,
                                        related_name='holidays', null=True, blank=True)
    holiday_date = models.DateField()
    name = models.CharField(max_length=200)  # e.g., "Pongal", "Heavy Rain"
    holiday_type = models.ForeignKey(HolidayType, on_delete=models.PROTECT)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=HOLIDAY_STATUS, default='declared')
    
    # Applicability (BRANCH-BASED ONLY)
    is_national = models.BooleanField(default=False,
                                     help_text="True = all branches get this")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    
    class Meta:
        ordering = ['holiday_date']
        indexes = [
            models.Index(fields=['holiday_date']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['holiday_date'], name='unique_holiday_date'),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.holiday_date}"
    
    def is_applicable_to_branch(self, branch):
        if self.is_national or self.holiday_calendar is None:
            return True
        return self.holiday_calendar.branch == branch


# ============================================
# NEW MODEL 4: MonthlyEarnedLeaves
# ============================================

class MonthlyEarnedLeaves(models.Model):
    """
    Monthly earned leave credits auto-generated from PayrollSettings
    
    Flow:
    1. Admin creates PayrollSettings with financial_year_start_month = 4 (April)
    2. MonthlyEarnedLeaves auto-generated with 12 months
    3. Each month has default credit value
    4. Admin can customize per month
    5. Leave balance calculation reads from here
    
    Example for April-March year:
    - April: 2 leaves
    - May: 1 leave
    - June: 2 leaves
    - ...
    - March: 1 leave
    """
    MONTHS = [
        (1, 'January'),
        (2, 'February'),
        (3, 'March'),
        (4, 'April'),
        (5, 'May'),
        (6, 'June'),
        (7, 'July'),
        (8, 'August'),
        (9, 'September'),
        (10, 'October'),
        (11, 'November'),
        (12, 'December'),
    ]
    
    payroll_settings = models.ForeignKey(PayrollSettings, on_delete=models.CASCADE,
                                        related_name='monthly_earned_leaves')
    month = models.IntegerField(choices=MONTHS)
    year = models.IntegerField()
    earned_leaves = models.DecimalField(max_digits=5, decimal_places=2,
                                       default=Decimal('0.00'))
    
    is_auto_generated = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('payroll_settings', 'month', 'year')
        ordering = ['year', 'month']
        indexes = [
            models.Index(fields=['payroll_settings', 'year', 'month']),
        ]
    
    def __str__(self):
        month_name = dict(self.MONTHS).get(self.month, 'Month')
        return f"{self.payroll_settings.company.name} - {month_name} {self.year}: {self.earned_leaves} leaves"
    
    @classmethod
    def generate_for_payroll_settings(cls, payroll_settings, start_year=None):
        """
        Auto-generate earned leaves for ONE financial year
        Example: Apr 2025 → Mar 2026
        """

        if not payroll_settings.financial_year_start_month:
            return 0

        fy_start_month = payroll_settings.financial_year_start_month
        earned_per_year = payroll_settings.earned_leaves_per_year or 0
        earned_per_month = (
            Decimal(str(earned_per_year)) / Decimal('12')
        ).quantize(Decimal('0.01'))

        if not start_year:
            today = date.today()
            start_year = today.year if today.month >= fy_start_month else today.year - 1

        created_count = 0

        for i in range(12):
            month = fy_start_month + i
            year = start_year

            if month > 12:
                month -= 12
                year += 1

            obj, created = cls.objects.get_or_create(
                payroll_settings=payroll_settings,
                month=month,
                year=year,
                defaults={
                    'earned_leaves': earned_per_month,
                    'is_auto_generated': True
                }
            )

            if created:
                created_count += 1

        return created_count
    
    @classmethod
    def sync_with_payroll_settings(cls, payroll_settings):
        """
        Update auto-generated monthly leaves when payroll policy changes
        """
        annual = payroll_settings.earned_leaves_per_year
        monthly = (Decimal(annual) / Decimal('12')).quantize(Decimal('0.01'))

        cls.objects.filter(
            payroll_settings=payroll_settings,
            is_auto_generated=True
        ).update(earned_leaves=monthly)


# ============================================
# NEW MODEL 5: HalfDayScenario
# ============================================

class HalfDayScenario(models.Model):
    """
    Handle half-day scenarios per branch
    
    Examples:
    - Rain/Flood (Chennai branch, today/tomorrow)
    - Election Day (Delhi branch, today)
    - Office maintenance (Mumbai branch)
    
    Branch-based only (not religion-based)
    Can be added anytime (even today!)
    """
    SCENARIO_TYPES = [
        ('rain_closure', 'Rain/Flood Closure'),
        ('election_day', 'Election Day'),
        ('emergency_closure', 'Emergency Closure'),
        ('office_maintenance', 'Office Maintenance'),
        ('safety_emergency', 'Safety Emergency'),
        ('other', 'Other'),
    ]
    
    branch = models.ForeignKey('Branch', on_delete=models.SET_NULL,
                              related_name='half_day_scenarios', null=True, blank=True)
    scenario_date = models.DateField()
    scenario_type = models.CharField(max_length=30, choices=SCENARIO_TYPES)
    description = models.TextField(help_text="e.g., Heavy rain, Election voting")
    
    credit_count = models.DecimalField(max_digits=3, decimal_places=2,
                                      default=Decimal('0.50'),
                                      help_text="Count: 0.5=half day, 1.0=full day")
    
    is_approved = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    approved_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name='approved_half_day_scenarios')
    
    class Meta:
        ordering = ['-scenario_date']
        indexes = [
            models.Index(fields=['branch', 'scenario_date'], name='hal_branch_scenario_idx'),
            models.Index(fields=['is_approved', 'scenario_date'], name='website_hal_is_appr_7f6ba9_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['branch', 'scenario_date'],
                condition=models.Q(branch__isnull=False),
                name='unique_branch_scenario_date',
            ),
            models.UniqueConstraint(
                fields=['scenario_date'],
                condition=models.Q(branch__isnull=True),
                name='unique_allbranch_scenario_date',
            ),
        ]

    def __str__(self):
        branch_name = self.branch.branch_name if self.branch else 'All Branches'
        return f"{branch_name} - {self.scenario_date}: {self.scenario_type}"


class Attendance(models.Model):
    employee = models.ForeignKey("Employee", on_delete=models.CASCADE)
    date = models.DateField(default=now)
    in_time = models.TimeField(null=True, blank=True)
    out_time = models.TimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ("Present", "Present"),
            ("Late Present", "Late Present"),
            ("Half Day", "Half Day"),
            ("Absent", "Absent"),
            ("Holiday", "Holiday"),
            ("Weekend", "Weekend"),
            ("Present (Half-Day)", "Present (Half-Day)"),

        ],
        default="Absent"
    )
    count = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    late = models.IntegerField(default=0)  # Minutes late


    is_holiday = models.BooleanField(default=False)
    holiday = models.ForeignKey(Holiday, null=True, blank=True, on_delete=models.SET_NULL)

    is_half_day = models.BooleanField(default=False)
    half_day_scenario = models.ForeignKey(HalfDayScenario, null=True, blank=True, on_delete=models.SET_NULL)

    status_overridden = models.BooleanField(
        default=False,
        help_text="If True, status/count was manually set (e.g. payroll late-day forgiveness) "
                   "and calculate_status() will preserve it instead of recomputing from in/out time.",
    )

    class Meta:
        unique_together = [('employee', 'date')]
        indexes = [
            models.Index(fields=["employee", "date"]),
            models.Index(fields=["date"]),
        ]

    def __str__(self):
        return f"{self.employee.first_name} {self.employee.employee_code} - {self.date}"
    
    def get_grace_period_minutes(self):
        """Company-configured grace period (PayrollSettings.grace_period_minutes), defaulting to 15."""
        from django.apps import apps
        PayrollSettings = apps.get_model('website', 'PayrollSettings')
        try:
            ps = PayrollSettings.objects.filter(company=self.employee.company).first()
            return ps.grace_period_minutes if ps else 15
        except Exception:
            return 15

    def calculate_lateness(self, grace_period_minutes=None):
        """
        Flexible/floating shift: duty is expected to run 9 hours from actual
        check-in time (e.g. in at 10:00 -> out by 19:00; in at 09:00 -> out by
        18:00). Returns how many minutes short of that 9-hour mark the
        employee left, or 0 if they met it or fell within the grace period.
        """
        if not self.in_time or not self.out_time:
            return 0

        in_dt = datetime.datetime.combine(self.date, self.in_time)
        out_dt = datetime.datetime.combine(self.date, self.out_time)
        if out_dt <= in_dt:
            out_dt += datetime.timedelta(days=1)

        expected_out_dt = in_dt + datetime.timedelta(hours=9)

        if grace_period_minutes is None:
            grace_period_minutes = self.get_grace_period_minutes()

        shortfall = (expected_out_dt - out_dt).total_seconds() / 60

        return int(shortfall) if shortfall > grace_period_minutes else 0

    def get_worked_minutes(self):
        """Total minutes actually worked (out_time - in_time, handling
        overnight shifts), or None if either time is missing."""
        if not self.in_time or not self.out_time:
            return None
        in_dt = datetime.datetime.combine(self.date, self.in_time)
        out_dt = datetime.datetime.combine(self.date, self.out_time)
        if out_dt <= in_dt:
            out_dt += datetime.timedelta(days=1)
        return int((out_dt - in_dt).total_seconds() // 60)

    def get_worked_duration_display(self):
        """Human-readable worked duration, e.g. '8h 10m'. Empty string if
        either time is missing."""
        total_minutes = self.get_worked_minutes()
        if total_minutes is None:
            return ""
        hours, minutes = divmod(total_minutes, 60)
        return f"{hours}h {minutes}m"

    @property
    def working_hours(self):
        """Numeric hours worked (e.g. 8.17), or None if either time is
        missing."""
        total_minutes = self.get_worked_minutes()
        if total_minutes is None:
            return None
        return round(total_minutes / 60, 2)

    @property
    def working_hours_display(self):
        """Worked duration as 'H:MM' (clock style), e.g. 8h30m -> '8:30'.
        Empty string if either time is missing."""
        total_minutes = self.get_worked_minutes()
        if total_minutes is None:
            return ""
        hours, minutes = divmod(total_minutes, 60)
        return f"{hours}:{minutes:02d}"


    def get_applicable_holiday(self, branch):
        '''Get the first holiday on this date that applies to the given branch.'''
        from django.apps import apps
        PayrollSettings = apps.get_model('website', 'PayrollSettings')

        try:
            _company = branch.company if hasattr(branch, 'company') else None
            ps = PayrollSettings.objects.filter(company=_company).first() if _company else None
            branch_specific = getattr(ps, 'branch_specific_holidays', True) if ps else True
        except Exception:
            branch_specific = True

        for holiday in Holiday.objects.filter(holiday_date=self.date).select_related('holiday_calendar__branch'):
            if not branch_specific or holiday.is_applicable_to_branch(branch):
                return holiday
        return None

    def get_half_day_scenario(self, branch):
        '''Get half-day scenario for this branch on this date'''
        scenario = HalfDayScenario.objects.filter(
            branch=branch,
            scenario_date=self.date,
            is_approved=True
        ).first()
        
        return scenario
    
    def calculate_status(self):
            """
            Calculate attendance status with branch-aware holidays and half-days
            """
            # Manager manually overrode status/count (e.g. forgiving a late day
            # at payroll time) — preserve it instead of recomputing.
            if self.status_overridden:
                return

            # STEP 0: Check if weekend — respects PayrollSettings.weekend_days
            try:
                ps = PayrollSettings.objects.filter(company=self.employee.company).first()
            except Exception:
                ps = None
            sunday_only = ps is not None and ps.weekend_days == 'sun'

            is_weekend = (self.date.weekday() == 6) if sunday_only else (self.date.weekday() >= 5)
            if is_weekend:
                self.status = "Weekend"
                self.count = Decimal("0.00")
                self.late = 0
                return
            
            # Get employee's branch
            branch = self.employee.branch
            
            # STEP 1: Check for half-day scenario (branch-specific)
            if branch:
                half_day = self.get_half_day_scenario(branch)
                if half_day:
                    self.is_half_day = True
                    self.half_day_scenario = half_day
                    self.status = "Present (Half-Day)"
                    self.count = half_day.credit_count
                    self.late = 0
                    return
                
                # STEP 2: Check for holiday (branch-specific!)
                holiday = self.get_applicable_holiday(branch)
                if holiday:
                    self.is_holiday = True
                    self.holiday = holiday
                    self.status = "Holiday"
                    self.count = Decimal("1.00")
                    self.late = 0
                    return
            
            # STEP 3: Normal attendance calculation (EXISTING CODE - DON'T CHANGE)
            # If no in_time or out_time, mark as Absent
            if not self.in_time or not self.out_time:
                self.status = "Absent"
                self.count = Decimal("0.00")
                self.late = 0
                return
            
            # Build datetime objects
            in_dt = datetime.datetime.combine(self.date, self.in_time)
            out_dt = datetime.datetime.combine(self.date, self.out_time)
            
            # Handle overnight shifts (if out_time is before in_time, add a day)
            if out_dt <= in_dt:
                out_dt += datetime.timedelta(days=1)
            
            # Calculate total hours worked
            worked_hours = Decimal((out_dt - in_dt).total_seconds()) / Decimal("3600")

            # Flexible/floating duty: expected checkout = check-in + 9 hours,
            # regardless of any fixed shift start time. Company-configured
            # grace period (PayrollSettings.grace_period_minutes) covers
            # falling short of that 9-hour mark.
            grace_period_minutes = ps.grace_period_minutes if ps else 15
            grace_hours = Decimal(grace_period_minutes) / Decimal("60")

            self.late = self.calculate_lateness(grace_period_minutes)

            # Define expected hours (9 hours)
            expected_hours = Decimal("9.0")

            # Apply rules based on hours worked
            if worked_hours >= expected_hours - grace_hours:
                # Worked the full 9 hours, or fell short only within the grace period
                self.status = "Present"
                self.count = Decimal("1.00")

            elif worked_hours >= expected_hours * Decimal("0.7"):
                # Worked 6.3+ hours (70% of 9 hours) but beyond the grace period
                self.status = "Late Present"
                self.count = Decimal("1.00")

            elif worked_hours >= expected_hours * Decimal("0.5"):
                # Worked 4.5+ hours (50% of 9 hours)
                self.status = "Half Day"
                self.count = Decimal("0.50")

            else:
                # Worked less than 4.5 hours
                self.status = "Absent"
                self.count = Decimal("0.00")

    def save(self, *args, **kwargs):
        # Always calculate status before saving
        self.calculate_status()
        super().save(*args, **kwargs)


# Alternative version with configurable hours
class AttendanceConfigurable(models.Model):
    """
    Version with configurable working hours
    You can set REQUIRED_WORK_HOURS in settings.py
    """
    employee = models.ForeignKey("Employee", on_delete=models.CASCADE)
    date = models.DateField(default=now)
    in_time = models.TimeField(null=True, blank=True)
    out_time = models.TimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ("Present", "Present"),
            ("Late Present", "Late Present"),
            ("Half Day", "Half Day"),
            ("Absent", "Absent"),
        ],
        default="Absent"
    )
    count = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    late = models.IntegerField(default=0)
    
    class Meta:
        indexes = [
            models.Index(fields=["employee", "date"]),
            models.Index(fields=["date"]),
        ]
    
    def __str__(self):
        return f"{self.employee.first_name} {self.employee.employee_code} - {self.date}"
    
    def calculate_lateness(self):
        """Calculate lateness based on shift start time"""
        if not self.in_time:
            return 0
        
        shift_start = self.employee.shift_start_time
        if not shift_start:
            return 0
        
        in_dt = datetime.datetime.combine(self.date, self.in_time)
        shift_dt = datetime.datetime.combine(self.date, shift_start)
        
        lateness = (in_dt - shift_dt).total_seconds() // 60
        grace = getattr(settings, "GRACE_PERIOD_MINUTES", 15)
        
        return int(lateness) if lateness > grace else 0
    
    def calculate_status(self):
        """
        Calculate status based on configurable working hours
        Set REQUIRED_WORK_HOURS in settings.py (default: 9)
        """
        if not self.in_time or not self.out_time:
            self.status = "Absent"
            self.count = Decimal("0.00")
            self.late = 0
            return
        
        # Build datetime
        in_dt = datetime.datetime.combine(self.date, self.in_time)
        out_dt = datetime.datetime.combine(self.date, self.out_time)
        
        # Handle overnight shifts
        if out_dt <= in_dt:
            out_dt += datetime.timedelta(days=1)
        
        # Calculate hours worked
        worked_hours = Decimal((out_dt - in_dt).total_seconds()) / Decimal("3600")
        
        # Get required hours from settings (default 9)
        required_hours = Decimal(str(getattr(settings, "REQUIRED_WORK_HOURS", 9)))
        
        # Calculate lateness
        self.late = self.calculate_lateness()
        
        # Apply rules
        if worked_hours >= required_hours:
            self.status = "Present" if self.late == 0 else "Late Present"
            self.count = Decimal("1.00")
        elif worked_hours >= required_hours * Decimal("0.7"):
            self.status = "Late Present"
            self.count = Decimal("1.00")
        elif worked_hours >= required_hours * Decimal("0.5"):
            self.status = "Half Day"
            self.count = Decimal("0.50")
        else:
            self.status = "Absent"
            self.count = Decimal("0.00")
    
    def save(self, *args, **kwargs):
        self.calculate_status()
        super().save(*args, **kwargs)





class AttendanceUpload(models.Model):
    file = models.FileField(upload_to="attendance_uploads/")
    total_rows = models.IntegerField(default=0)
    processed_rows = models.IntegerField(default=0)
    created_count = models.IntegerField(default=0)
    updated_count = models.IntegerField(default=0)
    skipped_count = models.IntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ("processing", "Processing"),
            ("completed", "Completed"),
            ("failed", "Failed"),
        ],
        default="processing"
    )
    created_at = models.DateTimeField(auto_now_add=True)


class AttendanceCorrectionRequest(models.Model):
    attendance = models.ForeignKey(Attendance, on_delete=models.CASCADE, related_name="correction_requests")
    # requested_by = models.ForeignKey(Employee, on_delete=models.CASCADE)  # The employee requesting the change
    old_in_time = models.TimeField(null=True, blank=True)
    old_out_time = models.TimeField(null=True, blank=True)
    new_in_time = models.TimeField(null=True, blank=True)
    new_out_time = models.TimeField(null=True, blank=True)

    reason = models.TextField()
    rejection_reason = models.TextField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[("Pending", "Pending"), ("Approved", "Approved"), ("Rejected", "Rejected")],
        default="Pending",
    )
    # reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="approvals")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Correction Request {self.id} - {self.status}"


