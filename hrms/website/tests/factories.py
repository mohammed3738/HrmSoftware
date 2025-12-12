from datetime import date
from website.models import Employee, Company, Branch

def create_test_employee():
    # Create optional FK objects
    company = Company.objects.create(name="Test Company")
    branch = Branch.objects.create(branch_name="Main Branch")

    emp = Employee.objects.create(
        company=company,
        branch=branch,
        salutation="Mr",
        first_name="Test",
        middle_name="",
        last_name="Employee",
        father_name="Test Father",
        gender="Male",
        blood_group="A+",
        date_of_birth=date(1990, 1, 1),
        place_of_birth="Test City",
        personal_email="test@example.com",
        present_address="Present Address",
        permanent_address="Permanent Address",
        personal_mobile="9999999999",
        date_of_marriage=None,

        employee_code="EMP001",
        designation="Developer",
        department="IT",
        date_of_joining=date(2020, 1, 1),
        date_of_confirmation=None,
        location="Office",
        payroll_of="Company",
        shift="Morning",

        pan_no="ABCDE1234F",
        aadhar_no="123412341234",
        voter_id="",
        passport="",
        uan_no="",
        pf_no="",
        esic_no="",

        name_as_per_bank="Test Employee",
        salary_account_number="123456789012",
        ifsc_code="SBIN0000001",

        emergency_contact_name1="Father",
        emergency_contact_relation1="Father",
        emergency_contact_mobile1="9999999999",
        emergency_contact_name2="",
        emergency_contact_relation2="Father",
        emergency_contact_mobile2="",

        status="Active",
    )
    
    return emp
