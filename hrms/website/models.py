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
    salutation = models.CharField(max_length=10, verbose_name="Salutation")
    first_name = models.CharField(max_length=100, verbose_name="First Name")
    middle_name = models.CharField(max_length=100, blank=True, verbose_name="Middle Name")
    last_name = models.CharField(max_length=100, verbose_name="Last Name")
    father_name = models.CharField(max_length=100, verbose_name="Father's Name")
    gender = models.CharField(max_length=10, choices=[("Male", "Male"), ("Female", "Female")], verbose_name="Gender")
    blood_group = models.CharField(max_length=10, verbose_name="Blood Group", choices=BLOOD_GROUP_CHOICES)
    date_of_birth = models.DateField(verbose_name="Date of Birth")
    place_of_birth = models.CharField(max_length=255, verbose_name="Place of Birth")
    personal_email = models.EmailField(verbose_name="Personal Email ID")
    present_address = models.TextField(verbose_name="Present Address")
    permanent_address = models.TextField(verbose_name="Permanent Address")
    personal_mobile = models.CharField(max_length=15, verbose_name="Personal Mobile No")
    date_of_marriage = models.DateField(blank=True, null=True, verbose_name="Date of Marriage")

    # ZCPL Office Details
    employee_code = models.CharField(max_length=50, unique=True, verbose_name="Employee Code")
    designation = models.CharField(max_length=100, verbose_name="Designation")
    department = models.CharField(max_length=100, verbose_name="Department")
    date_of_joining = models.DateField(verbose_name="Date of Joining")
    date_of_confirmation = models.DateField(blank=True, null=True, verbose_name="Date of Confirmation")
    location = models.CharField(max_length=255, verbose_name="Location")
    payroll_of = models.CharField(max_length=50, verbose_name="On Payroll Of", null=True, blank=True)
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
    pan_no = models.CharField(max_length=10, verbose_name="PAN No")
    aadhar_no = models.CharField(max_length=12, verbose_name="Aadhar No")
    voter_id = models.CharField(max_length=15, blank=True, verbose_name="Voter ID")
    passport = models.CharField(max_length=15, blank=True, verbose_name="Passport")
    uan_no = models.CharField(max_length=15, blank=True, verbose_name="Universal Account No. (UAN)")
    pf_no = models.CharField(max_length=15, blank=True, verbose_name="PF No")
    esic_no = models.CharField(max_length=15, blank=True, verbose_name="ESIC No")

    # Banking Details
    name_as_per_bank = models.CharField(max_length=100, verbose_name="Name As Per Bank Record")
    salary_account_number = models.CharField(max_length=20, verbose_name="Salary Account Number")
    ifsc_code = models.CharField(max_length=11, verbose_name="IFSC Code")
    # assets
    # assets = models.ManyToManyField('Asset', related_name='assigned_employees',null=True, blank=True, verbose_name="Assigned Assets")

    # Emergency Contact Details
    emergency_contact_name1 = models.CharField(max_length=100, verbose_name="Emergency Contact Name 1")
    emergency_contact_relation1 = models.CharField(
        max_length=50,
        choices=[("Spouse", "Spouse"), ("Father", "Father"), ("Mother", "Mother"), 
                 ("Brother", "Brother"), ("Sister", "Sister"), ("Son", "Son"), 
                 ("Daughter", "Daughter"), ("Other", "Other")],
        verbose_name="Emergency Contact Relation 1"
    )
    emergency_contact_mobile1 = models.CharField(max_length=15, verbose_name="Emergency Contact Mobile No 1")
    emergency_contact_name2 = models.CharField(max_length=100, blank=True, verbose_name="Emergency Contact Name 2")
    emergency_contact_relation2 = models.CharField(
        max_length=50,
        choices=[("Spouse", "Spouse"), ("Father", "Father"), ("Mother", "Mother"), 
                 ("Brother", "Brother"), ("Sister", "Sister"), ("Son", "Son"), 
                 ("Daughter", "Daughter"), ("Other", "Other")],
        blank=True,
        verbose_name="Emergency Contact Relation 2"
    )
    emergency_contact_mobile2 = models.CharField(max_length=15, blank=True, verbose_name="Emergency Contact Mobile No 2")
    status = models.CharField(max_length=50, choices=[("Active", "Active"), ("Pending", "Pending"), ("Left", "Left")] , default='Active'
)
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
    other_documents = models.FileField(upload_to="offboarding/other_documents/", blank=True, verbose_name="Other Documents")
    fnf_documents = models.FileField(upload_to="offboarding/fnf/", blank=True, verbose_name="FNF Document")

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


class Attendance(models.Model):
    employee = models.ForeignKey("Employee", on_delete=models.CASCADE)
    date = models.DateField(default=now)  # Store attendance date
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
    # count = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # 1.0, 0.5, 0
    count = models.DecimalField( max_digits=5, decimal_places=2, default=Decimal("0.00")
)

    late = models.IntegerField(default=0)  # Minutes late

    class Meta:
        indexes = [
            models.Index(fields=["employee", "date"]),  # Composite index
            models.Index(fields=["date"]),  # Index for date-based queries
        ]

    def __str__(self):
        return f"{self.employee.first_name} {self.employee.employee_code} - {self.date}"

    def calculate_lateness(self):
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
        if not self.in_time or not self.out_time:
            self.status = "Absent"
            self.count = Decimal("0.00")
            return

        shift_start = self.employee.shift_start_time
        shift_end = self.employee.shift_end_time

        if not shift_start or not shift_end:
            self.status = "Absent"
            self.count = Decimal("0.00")
            return

        # Build datetime
        in_dt = datetime.datetime.combine(self.date, self.in_time)
        out_dt = datetime.datetime.combine(self.date, self.out_time)

        shift_start_dt = datetime.datetime.combine(self.date, shift_start)
        shift_end_dt = datetime.datetime.combine(self.date, shift_end)

        # Night shift handling
        if shift_end_dt <= shift_start_dt:
            shift_end_dt += datetime.timedelta(days=1)
        if out_dt <= in_dt:
            out_dt += datetime.timedelta(days=1)

        worked_hours = Decimal(
            (out_dt - in_dt).total_seconds()
        ) / Decimal("3600")

        expected_hours = Decimal(
            (shift_end_dt - shift_start_dt).total_seconds()
        ) / Decimal("3600")

        self.late = self.calculate_lateness()

        # Dynamic rules
        if worked_hours >= expected_hours:
            self.status = "Present" if self.late == 0 else "Late Present"
            self.count = Decimal("1.00")

        elif worked_hours >= expected_hours * Decimal("0.7"):
            self.status = "Late Present"
            self.count = Decimal("1.00")

        elif worked_hours >= expected_hours * Decimal("0.5"):
            self.status = "Half Day"
            self.count = Decimal("0.50")

        else:
            self.status = "Absent"
            self.count = Decimal("0.00")
            
    def save(self, *args, **kwargs):
        # Always calculate before saving
        self.calculate_status()
        super().save(*args, **kwargs)
        
    # def save(self, *args, **kwargs):
    #     """Auto calculate count based on in_time and out_time"""
    #     if self.in_time and self.out_time:
    #         work_duration = datetime.datetime.combine(datetime.date.today(), self.out_time) - datetime.datetime.combine(datetime.date.today(), self.in_time)
    #         total_hours = work_duration.total_seconds() / 3600  # Convert seconds to hours

    #         # Assuming 8 hours is a full working day
    #         self.count = round(min(total_hours / 9, 1), 2)  # Max count = 1 (full day)
    #     else:
    #         self.count = 0  # If out_time is missing, count remains 0

    #     super().save(*args, **kwargs)


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


class LeaveBalanceHistory(models.Model):
    employee = models.ForeignKey("Employee", on_delete=models.CASCADE)
    month = models.CharField(max_length=20)  # e.g. 'November 2025'
    opening_balance = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    days_present = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    leave_taken = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    late = models.IntegerField(default=0)
    compoff = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    leave_without_pay = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    closing_balance = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    leave_balance = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    final_leave_balance = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    recorded_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-recorded_on']


    def __str__(self):
        return f"{self.employee.first_name} - {self.month}"


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
        today = date.today()
        if self.is_auto:
            first_day_of_month = today.replace(day=1)
            next_month = first_day_of_month.replace(day=28) + timedelta(days=4)
            last_day_of_month = next_month - timedelta(days=next_month.day)
            return first_day_of_month, last_day_of_month
        else:
            current_month = today.month
            current_year = today.year
            start_month = current_month if today.day >= self.from_date else current_month - 1
            end_month = start_month if self.from_date <= self.to_date else start_month + 1
            from_date = date(current_year, start_month, self.from_date)
            to_date = date(current_year, end_month, self.to_date)
            return from_date, to_date

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
    
