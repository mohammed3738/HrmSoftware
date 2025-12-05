from django.shortcuts import render, redirect,get_object_or_404
from .forms import *
from django.http import HttpResponse, Http404
from .tasks import *
# Create your views here.
from django.utils.timezone import make_aware
import datetime
from django.contrib import messages
import pandas as pd
from django.http import HttpResponse
from .models import *  # Import your Employee model

from datetime import datetime,timedelta
from django.http import JsonResponse
from django.utils.timezone import now
import json
from datetime import date, timedelta
from decimal import Decimal
from django.core.paginator import Paginator
from dateutil.relativedelta import relativedelta
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Sum
from .signals import recalculate_leave_balance_for_employee
from django.db.models import Q
import io
import os
from django.http import FileResponse, Http404
import openpyxl

# def parse_time(time_value):
#     """Convert time string or float to a proper datetime.time object."""
#     if pd.isna(time_value) or time_value is None:
#         return None  # Return None if NaN or None
    
#     # If the value is a float (Excel's internal time format)
#     if isinstance(time_value, float):
#         hours = int(time_value * 24)  # Convert float to hours
#         minutes = int((time_value * 24 * 60) % 60)  # Convert to minutes
#         seconds = int((time_value * 24 * 3600) % 60)  # Convert to seconds
#         return timedelta(hours=hours, minutes=minutes, seconds=seconds).time()

#     # If it's a string, use strptime to convert it
#     try:
#         return datetime.strptime(time_value, "%H:%M:%S").time()
#     except ValueError:
#         print(f"⚠️ Invalid time format: {time_value}")
#         return None  # Return None if parsing fails

# atul
def company_details_api(request, pk):
    company = get_object_or_404(Company, pk=pk)

    data = {
        "short_name": company.short_name,
        "name": company.name,
        "phone": company.phone,
        "email": company.email,
        "address": company.address,
        "tan_number": company.tan_number,
        "pan_number": company.pan_number,
        "employer_pf": company.employer_pf,
        "ptrc_number": company.ptrc_number,
        "ptec_number": company.ptec_number,
        "esic_number": company.esic_number,
        "status": company.status,
    }

    return JsonResponse(data)


def delete_employee(request, employee_id):
    employee = get_object_or_404(Employee, id=employee_id)

    if request.method == "POST":
        employee.delete()
        messages.success(request, "Employee deleted successfully.")
        return redirect("create-employee")  

    messages.error(request, "Invalid request.")
    return redirect("create-employee")




# atul

# Vaishu
def branch_details_api(request, pk):
    branch = get_object_or_404(Branch, pk=pk)

    data = {
        "branch_name": branch.branch_name,
        "branch_address": branch.branch_address,
        # "tan_number": company.tan_number,
        # "pan_number": company.pan_number,
        # "employer_pf": company.employer_pf,
        # "ptrc_number": company.ptrc_number,
        # "ptec_number": company.ptec_number,
        # "esic_number": company.esic_number,
        # "status": company.status,
    }

    return JsonResponse(data)
# Vaishu














def parse_time(time_value):
    """Convert time string to a proper datetime.time object."""
    if pd.isna(time_value) or time_value is None:
        return None  # Return None if NaN or None
        
    time_value = str(time_value).strip()  # Convert to string and strip whitespace
    
    if not time_value:  # If empty after strip, return None
        return None

    try:
        return datetime.strptime(time_value, "%H:%M:%S").time()
    except ValueError:
        print(f"⚠️ Invalid time format: {time_value}")
        return None  # Return None if parsing fails
    
    
def upload_attendance_excel(request):
    if request.method == "POST" and request.FILES.get("attendance_file"):
        file = request.FILES["attendance_file"]

        try:
            df = pd.read_excel(file)

            # Clean column names
            df.columns = df.columns.str.strip()

            print(f"Columns in the file: {df.columns}")

            for index, row in df.iterrows():
                employee_code = row.get("Employee Code")
                attendance_date = row.get("Date")

                in_time_raw = row.get("In Time")
                out_time_raw = row.get("Out Time")

                in_time = parse_time(in_time_raw)
                out_time = parse_time(out_time_raw)

                attendance_date = pd.to_datetime(attendance_date).date()

                print(f"Row {index}: {row.to_dict()}")
                print(f"✅ Parsed In: {in_time}, Parsed Out: {out_time}")

                # Get employee
                employee = Employee.objects.filter(employee_code=employee_code).first()
                if not employee:
                    print(f"⚠️ Employee with code {employee_code} not found!")
                    continue

                # Create or update attendance
                attendance, created = Attendance.objects.get_or_create(
                    employee=employee,
                    date=attendance_date,
                    defaults={
                        "count": 0,
                        "late": 0,
                        "in_time": in_time,
                        "out_time": out_time,
                    },
                )

                if not created:
                    if in_time:
                        attendance.in_time = in_time
                    if out_time:
                        attendance.out_time = out_time

                # Calculate working hours if possible
                if attendance.in_time and attendance.out_time:
                    in_dt = datetime.combine(attendance_date, attendance.in_time)
                    out_dt = datetime.combine(attendance_date, attendance.out_time)

                    working_hours = (out_dt - in_dt).total_seconds() / 3600

                    if working_hours >= 9:
                        attendance.count = 1.0
                        attendance.late = 0
                    elif working_hours >= 6:
                        attendance.count = 1.0
                        attendance.late = 1
                    elif working_hours >= 4:
                        attendance.count = 0.5
                        attendance.late = 0
                    else:
                        attendance.count = 0.0
                        attendance.late = 0

                    print(
                        f"✅ Working Hours: {working_hours:.2f}, Count: {attendance.count}, Late: {attendance.late}"
                    )

                # Safe save with debug
                try:
                    attendance.save()
                    print(
                        f"✅ Saved: {employee_code} | {attendance_date} | In: {attendance.in_time} | Out: {attendance.out_time} | Count: {attendance.count} | Late: {attendance.late}"
                    )
                except Exception as e:
                    print(
                        f"❌ Error while saving attendance for {employee_code} on {attendance_date}: {str(e)}"
                    )
                    # Don’t stop loop; skip this record
                    continue

            messages.success(request, "Attendance uploaded successfully!")
            return JsonResponse(
                {"success": True, "message": "Attendance uploaded successfully!"}
            )

        except Exception as e:
            print(f"❌ Error processing file: {str(e)}")
            messages.error(request, f"Error processing file: {str(e)}")
            return JsonResponse(
                {"success": False, "message": f"Error processing file: {str(e)}"}
            )

    return JsonResponse({"success": False, "message": "No file uploaded!"}, status=400)








def attendance_list(request):
    """View attendance by selected date (default: today)"""
    date_str = request.GET.get('date')
    if date_str:
        try:
            selected_date = date.fromisoformat(date_str)
        except ValueError:
            selected_date = now().date()
    else:
        selected_date = now().date()

    attendance_records = Attendance.objects.filter(date=selected_date)

    # For navigation buttons
    prev_date = selected_date - timedelta(days=1)
    next_date = selected_date + timedelta(days=1)

    context = {
        "attendance_records": attendance_records,
        "selected_date": selected_date,
        "prev_date": prev_date,
        "next_date": next_date,
    }
    return render(request, "attendance/today.html", context)



def employee_attendance_detail(request, employee_id):
    employee = get_object_or_404(Employee, id=employee_id)

    selected_year = request.GET.get("year")
    selected_month = request.GET.get("month")

    attendance_records = Attendance.objects.filter(employee=employee)

    if selected_year:
        attendance_records = attendance_records.filter(date__year=selected_year)
    if selected_month:
        attendance_records = attendance_records.filter(date__month=selected_month)

    attendance_records = attendance_records.only(
        "date", "in_time", "out_time", "status"
    ).order_by("-date")

    dates_qs = Attendance.objects.filter(employee=employee)
    years = dates_qs.dates("date", "year", order="DESC")
    months = dates_qs.dates("date", "month", order="DESC")

    paginator = Paginator(attendance_records, 30)
    page = request.GET.get("page")
    attendance_records = paginator.get_page(page)

    context = {
        "employee": employee,
        "attendance_records": attendance_records,
        "years": years,
        "months": months,
        "selected_year": selected_year,
        "selected_month": selected_month,
    }
    return render(request, "attendance/employee_attendance_detail.html", context)


# attendance over rider

def submit_correction_request(request):
    if request.method == "POST":
        attendance_id = request.POST.get("attendance_id")
        new_in_time = request.POST.get("new_in_time")
        new_out_time = request.POST.get("new_out_time")
        reason = request.POST.get("reason")
        
        attendance = get_object_or_404(Attendance, id=attendance_id)
        
        # Create a correction request
        correction_request = AttendanceCorrectionRequest.objects.create(
            attendance=attendance,
            # requested_by=request.user,
            old_in_time=attendance.in_time,
            old_out_time=attendance.out_time,
            new_in_time=new_in_time,
            new_out_time=new_out_time,
            reason=reason,
        )
        
        return JsonResponse({"message": "Correction request submitted successfully!"})



# approval
def approve_correction_request(request, request_id):
    correction_request = get_object_or_404(AttendanceCorrectionRequest, id=request_id)

    # Update attendance record
    attendance = correction_request.attendance
    attendance.in_time = correction_request.new_in_time
    attendance.out_time = correction_request.new_out_time
    attendance.save()

    # Mark request as approved\
    
    # if correction_request.status == "Approved":
    correction_request.status = "Approved"
    # elif correction_request.status == "Rejected":
    #     correction_request.status = "Rejected"
    # correction_request.reviewed_by = request.user
    correction_request.reviewed_at = now()
    correction_request.save()

    return JsonResponse({"message": "Correction Approved!"})



def reject_correction_request(request, request_id):
    correction_request = get_object_or_404(AttendanceCorrectionRequest, id=request_id)

    if request.method == "POST":
        data = json.loads(request.body)
        rejection_reason = data.get("reason", "")

        if not rejection_reason:
            return JsonResponse({"error": "Rejection reason is required."}, status=400)

        # Update request as rejected
        correction_request.status = "Rejected"
        correction_request.rejection_reason = rejection_reason  # Save reason for employee reference
        correction_request.reviewed_at = now()
        correction_request.save()

        return JsonResponse({"message": "Correction Request Rejected!"})

    return JsonResponse({"error": "Invalid request"}, status=400)


def admin_dashboard(request):
    requests = AttendanceCorrectionRequest.objects.filter(status='Pending')  # Attendance approvals
    compoff_requests = CompOffRequest.objects.filter(status='Pending')  # CompOff approvals
    today = date.today()
    current_month = date.today().month

    # Get the first day of the current month
    first_day_of_month = today.replace(day=1)
    employee = Employee.objects.first()
    # Calculate the number of days
    total_days = (today - first_day_of_month).days + 1  # Adding 1 to include today
    compoff1 = CompOffRequest.objects.filter(employee=employee ,from_date__month=current_month, to_date__month = current_month)

    compoff = 0
    for i in compoff1:
        from_date = i.from_date
        to_date = i.to_date
        compoff = compoff + (to_date-from_date).days +1 
        print(compoff,'ppppppp')
        print(i.from_date,'jjjjj')
        print(i.to_date,'llll')
    print(compoff,'aaaaaa') 
    return render(request, 'd/f.html', {
        "requests": requests,
        "compoff_requests": compoff_requests
    })



@csrf_exempt
def approve_compoff(request, compoff_id):
    try:
        compoff = CompOffRequest.objects.get(id=compoff_id)
        compoff.status = "Approved"
        compoff.save()
        return JsonResponse({"message": "CompOff request approved successfully!"})
    except CompOffRequest.DoesNotExist:
        return JsonResponse({"message": "Request not found!"}, status=404)

@csrf_exempt
def reject_compoff(request, compoff_id):
    if request.method == "POST":
        try:
            compoff = CompOffRequest.objects.get(id=compoff_id)
            data = json.loads(request.body)
            compoff.status = "Rejected"
            compoff.rejection_reason = data.get("reason", "No reason provided")
            compoff.save()
            return JsonResponse({"message": "CompOff request rejected successfully!"})
        except CompOffRequest.DoesNotExist:
            return JsonResponse({"message": "Request not found!"}, status=404)


def download_employees_excel(request):
    # Fetch active employees
    employees = Employee.objects.filter(status="Active").values(
        "employee_code", "first_name", "middle_name", "last_name", "father_name",
        "gender", "blood_group", "date_of_birth", "place_of_birth",
        "personal_email", "personal_mobile", "present_address", "permanent_address",
        "date_of_marriage", "designation", "department", "date_of_joining",
        "date_of_confirmation", "location", "payroll_of", "shift",
        "pan_no", "aadhar_no", "voter_id", "passport", "uan_no", "pf_no", "esic_no",
        "name_as_per_bank", "salary_account_number", "ifsc_code",
        "emergency_contact_name1", "emergency_contact_relation1", "emergency_contact_mobile1",
        "emergency_contact_name2", "emergency_contact_relation2", "emergency_contact_mobile2"
    )

    # Convert QuerySet to Pandas DataFrame
    df = pd.DataFrame(list(employees))

    # Rename columns for better readability
    df.rename(columns={
        "employee_code": "Employee Code",
        "first_name": "First Name",      
        "middle_name": "Middle Name",
        "last_name": "Last Name",
        "father_name": "Father's Name",
        "gender": "Gender",
        "blood_group": "Blood Group",
        "date_of_birth": "Date of Birth",
        "place_of_birth": "Place of Birth",
        "personal_email": "Personal Email",
        "personal_mobile": "Personal Mobile",
        "present_address": "Present Address",
        "permanent_address": "Permanent Address",
        "date_of_marriage": "Date of Marriage",
        "designation": "Designation",
        "department": "Department",
        "date_of_joining": "Date of Joining",
        "date_of_confirmation": "Date of Confirmation",
        "location": "Location",
        "payroll_of": "On Payroll Of",
        "shift": "Shift",
        "pan_no": "PAN Number",
        "aadhar_no": "Aadhar Number",
        "voter_id": "Voter ID",
        "passport": "Passport",
        "uan_no": "UAN Number",
        "pf_no": "PF Number",
        "esic_no": "ESIC Number",
        "name_as_per_bank": "Bank Name",
        "salary_account_number": "Salary Account Number",
        "ifsc_code": "IFSC Code",
        "emergency_contact_name1": "Emergency Contact Name 1",
        "emergency_contact_relation1": "Emergency Contact Relation 1",
        "emergency_contact_mobile1": "Emergency Contact Mobile 1",
        "emergency_contact_name2": "Emergency Contact Name 2",
        "emergency_contact_relation2": "Emergency Contact Relation 2",
        "emergency_contact_mobile2": "Emergency Contact Mobile 2",
    }, inplace=True)

    # Create HTTP response with Excel content type
    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="active_employees.xlsx"'

    # Save DataFrame to Excel in response
    with pd.ExcelWriter(response, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Active Employees", index=False)

    return response


def download_leave_excel(request):
    # Fetch active leave balances along with related employee info
    leave_balances = LeaveBalance.objects.select_related("employee").filter(employee__status="Active")

    data = []
    for lb in leave_balances:
        emp = lb.employee
        data.append({
            "Employee Code": emp.employee_code,
            "First Name": emp.first_name,
            "Middle Name": emp.middle_name,
            "Last Name": emp.last_name,
            "Father's Name": emp.father_name,
            "Gender": emp.gender,
            "Blood Group": emp.blood_group,
            "Date of Birth": emp.date_of_birth,
            "Place of Birth": emp.place_of_birth,
            "Personal Email": emp.personal_email,
            "Personal Mobile": emp.personal_mobile,
            "Present Address": emp.present_address,
            "Permanent Address": emp.permanent_address,
            "Date of Marriage": emp.date_of_marriage,
            "Designation": emp.designation,
            "Department": emp.department,
            "Date of Joining": emp.date_of_joining,
            "Date of Confirmation": emp.date_of_confirmation,
            "Location": emp.location,
            "On Payroll Of": emp.payroll_of,
            "Shift": emp.shift,
            "PAN Number": emp.pan_no,
            "Aadhar Number": emp.aadhar_no,
            "Voter ID": emp.voter_id,
            "Passport": emp.passport,
            "UAN Number": emp.uan_no,
            "PF Number": emp.pf_no,
            "ESIC Number": emp.esic_no,
            "Bank Name": emp.name_as_per_bank,
            "Salary Account Number": emp.salary_account_number,
            "IFSC Code": emp.ifsc_code,
            "Emergency Contact Name 1": emp.emergency_contact_name1,
            "Emergency Contact Relation 1": emp.emergency_contact_relation1,
            "Emergency Contact Mobile 1": emp.emergency_contact_mobile1,
            "Emergency Contact Name 2": emp.emergency_contact_name2,
            "Emergency Contact Relation 2": emp.emergency_contact_relation2,
            "Emergency Contact Mobile 2": emp.emergency_contact_mobile2,
            # Leave-specific fields
            "Opening Balance": lb.opening_balance,
            "Leave Taken": lb.leave_taken,
            "Number of Days Present": lb.number_of_days_present,
            "Total Number of Days": lb.total_number_of_days,
            "Late": lb.late,
            "Comp Off": lb.compoff,
            "Leave Without Pay": lb.leave_without_pay,
            "Closing Balance": lb.closing_balance,
            "Leave Balance": lb.leave_balance,
        })

    # Convert to DataFrame
    df = pd.DataFrame(data)

    # Create response with Excel
    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="leave_balance.xlsx"'

    with pd.ExcelWriter(response, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Active Leave Balance", index=False)

    return response









def test(request):
    test_func.delay()

    employees = Employee.objects.filter(status='Active')
    return HttpResponse("Done")


def home(request):
    return render(request, 'base2.html')


# working code 
# def create_employee(request):
#     if request.method == 'POST':
#         form = EmployeeForm(request.POST, request.FILES)
#         if form.is_valid():
#             # Get unsaved employee instance
#             employee = form.save(commit=False)
#             # Get branch id from POST and assign the branch if valid
#             branch_id = request.POST.get('branch')
#             if branch_id:
#                 try:
#                     branch = Branch.objects.get(id=branch_id)
#                     employee.branch = branch
#                 except Branch.DoesNotExist:
#                     pass
#             # Instantiate formset with the employee instance
#             formset = PreviousEmploymentFormSet(request.POST, instance=employee)
#             if formset.is_valid():
#                 employee.save()       # Save the employee first
#                 formset.save()        # Then save all previous employment records
#                 messages.success(request, "Employee created successfully!")
#                 return redirect('home')
#             else:
#                 messages.error(request, "There were errors in the previous employment details.")
#                 print("Formset errors:", formset.errors)
#                 print("Formset non-form errors:", formset.non_form_errors())
#         else:
#             messages.error(request, "There were errors in the employee details.")
#             print("Form errors:", form.errors)
#             # Instantiate formset with POST data to re-render errors
#             formset = PreviousEmploymentFormSet(request.POST)
#     else:
#         form = EmployeeForm()
#         formset = PreviousEmploymentFormSet(instance=Employee())

#     # For context, also retrieve all employees and branches if needed in the template.
#     employees = Employee.objects.all()
#     branches = Branch.objects.all()
#     active_employees = Employee.objects.filter(status="Active")
#     employee_count = active_employees.count()
#     inactive_employees = Employee.objects.filter(status="Left ")
#     employee_count_inactive = inactive_employees.count()
#     companies = Company.objects.all()
#     context = {
#         'form': form,
#         'formset': formset,
#         'employees': employees,
#         'branches': branches,
#         'employee_count': employee_count,
#         'employee_count_inactive': employee_count_inactive,
#         'companies': companies,
#     }
#     return render(request, 'employee/create_employee2.html', context)





# working
# def create_employee(request):
#     if request.method == 'POST':
#         form = EmployeeForm(request.POST, request.FILES)
        
#         if form.is_valid():
#             employee = form.save(commit=False)

#             # Assign branch if selected
#             branch_id = request.POST.get("branch")
#             if branch_id:
#                 try:
#                     employee.branch = Branch.objects.get(id=branch_id)
#                 except Branch.DoesNotExist:
#                     pass

#             # Formset for previous employments
#             prev_formset = PreviousEmploymentFormSet(request.POST, request.FILES, instance=employee)

#             # ---- NEW: Prepare Attachment Formsets for each previous employment row ----
#             attachment_sets = []  # store child formsets

#             if prev_formset.is_valid():
#                 # Save employee first, then previous rows
#                 employee.save()
#                 prev_instances = prev_formset.save(commit=False)

#                 for index, prev_obj in enumerate(prev_instances):
#                     prev_obj.employee = employee  # attach FK
#                     prev_obj.save()

#                     # Detect nested attachment forms by prefix
#                     prefix = f"attach-{index}"

#                     attach_formset = AttachmentFormSet(
#                         request.POST,
#                         request.FILES,
#                         prefix=prefix,
#                         instance=prev_obj
#                     )

#                     attachment_sets.append(attach_formset)

#                 # Validate all nested attachment formsets
#                 if all([fs.is_valid() for fs in attachment_sets]):
#                     # Save attachments
#                     for fs in attachment_sets:
#                         fs.save()

#                     messages.success(request, "Employee created successfully with nested attachments!")
#                     return redirect('home')
#                 else:
#                     messages.error(request, "Error in nested attachments")
#                     print("Attachment errors:", [fs.errors for fs in attachment_sets])

#             else:
#                 messages.error(request, "There were validation errors in previous employment.")
#                 print("Previous Employment Errors:", prev_formset.errors)

#         else:
#             messages.error(request, "Employee form has errors.")
#             print("Employee Form Errors:", form.errors)

#         # If failing validation → rebuild formsets for re-render
#         prev_formset = PreviousEmploymentFormSet(request.POST, request.FILES)

#     else:
#         # GET request → empty forms
#         form = EmployeeForm()
#         prev_formset = PreviousEmploymentFormSet(instance=Employee())

#     # Context
#     context = {
#         'form': form,
#         'formset': prev_formset,
#         'employees': Employee.objects.all(),
#         'branches': Branch.objects.all(),
#         'employee_count': Employee.objects.filter(status="Active").count(),
#         'employee_count_inactive': Employee.objects.filter(status="Left ").count(),
#         'companies': Company.objects.all(),
#     }

#     return render(request, 'employee/create_employee2.html', context)



def create_employee(request):
    if request.method == 'POST':
        form = EmployeeForm(request.POST, request.FILES)

        # Main Attachments (already working guest attachments)
        attachment_formset = AttachmentFormSet(request.POST, request.FILES)

        # Previous Employment records formset
        formset = PreviousEmploymentFormSet(request.POST)

        if form.is_valid() and formset.is_valid() and attachment_formset.is_valid():

            # Create Employee instance
            employee = form.save(commit=False)

            # Assign selected branch
            branch_id = request.POST.get('branch')
            if branch_id:
                employee.branch = Branch.objects.filter(id=branch_id).first()

            employee.save()

            # -------------------------------
            # Save Previous Employment records
            # -------------------------------
            previous_records = formset.save(commit=False)

            for idx, emp_record in enumerate(previous_records):
                emp_record.employee = employee
                emp_record.save()

                prefix = f"attach-{idx}-"
                file_keys = [k for k in request.FILES.keys() if k.startswith(prefix)]

                for key in file_keys:
                    index = key.split("-")[2]
                    doc_name = request.POST.get(f"attach-{idx}-{index}-document_name", "")

                    PreviousEmploymentAttachment.objects.create(
                        previous_employment=emp_record,
                        file=request.FILES[key],
                        document_name=doc_name
                    )

            # Delete removed rows
            for obj in formset.deleted_objects:
                obj.delete()

            # -------------------------------
            # Save Main Attachments (not nested)
            # -------------------------------
            attachment_formset.instance = employee
            attachment_formset.save()

            messages.success(request, "Employee created successfully!")
            return redirect('home')

        else:
            messages.error(request, "Some fields are missing or invalid. Please check again.")

    else:
        form = EmployeeForm()
        formset = PreviousEmploymentFormSet(instance=Employee())
        attachment_formset = AttachmentFormSet()

    context = {
        "form": form,
        "formset": formset,
        "attachment_formset": attachment_formset,
        "employees": Employee.objects.all(),
        "branches": Branch.objects.all(),
        "companies": Company.objects.all(),
        "employee_count": Employee.objects.filter(status="Active").count(),
        "employee_count_inactive": Employee.objects.filter(status="Left").count(),
    }

    return render(request, 'employee/create_employee2.html', context)









# def employee_detail(request, pk):
#     employee = get_object_or_404(Employee, pk=pk)
#     employeement= PreviousEmployment.objects.filter(employee=employee)
#     first_name = getattr(employee, "first_name", None) or (getattr(user, "first_name", None) if user else None)
#     # last_name  = getattr(employee, "last_name", None)  or (getattr(user, "last_name", None) if user else None)
#     context = {
#         'employee': employee,
#         'employeement': employeement,
#         'display': {
#             'first_name': first_name,
#         }
#     }
#     print('Employee Details:', employee)
#     print('Previous Employeement Details:', employeement)
#     return render(request, 'employee/employee_detail.html', context)

from django.shortcuts import get_object_or_404, render

def employee_detail(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    # employeement = PreviousEmployment.objects.filter(employee=employee)
    # previous_employments = employee.previous_employments.all().order_by('-to_date')
    previous_employments = PreviousEmployment.objects.filter(employee=employee).order_by('-to_date')
    # attachments = employee.attachments.all().order_by('-uploaded_at')
    attachments = EmployeeAttachment.objects.filter(employee=employee).order_by('-uploaded_at')

    # safe related user (if Employee has a user FK/OneToOne)
    user = getattr(employee, "user", None)

    # safe lookups with fallbacks
    first_name = getattr(employee, "first_name", None) or (getattr(user, "first_name", None) if user else None)
    last_name  = getattr(employee, "last_name", None)  or (getattr(user, "last_name", None) if user else None)
    email      = getattr(employee, "email", None)      or (getattr(user, "email", None) if user else None)
    phone      = getattr(employee, "phone", None)      or getattr(employee, "contact", None) or ""

    full_name = " ".join(filter(None, [first_name, last_name])) or getattr(employee, "full_name", None) or str(employee)

    # photo url safe
    photo_url = None
    photo_field = getattr(employee, "photo", None) or getattr(employee, "avatar", None)
    if photo_field:
        try:
            photo_url = photo_field.url
        except Exception:
            photo_url = None

    context = {
        'employee': employee,
        'previous_employments': previous_employments,
        'attachments': attachments,
        'display': {
            'first_name': first_name,
            'last_name': last_name,
            'full_name': full_name,
            'email': email,
            'phone': phone,
            'photo_url': photo_url,
        }
    }

    # debug prints (ok to remove later)
    print('Employee Details:', employee)
    print('Previous Employment Details:', previous_employments)
    print('Display dict:', context['display'])

    return render(request, 'employee/employee_detail.html', context)


def download_attachment(request, pk):
    attachment = get_object_or_404(EmployeeAttachment, pk=pk)

    # OPTIONAL: extra permission checks
    # if not request.user.has_perm('yourapp.view_attachment') or attachment.owner != request.user:
    #     raise Http404()

    if not attachment.file:
        raise Http404("File not found")

    # open file for streaming
    try:
        file_handle = attachment.file.open('rb')
    except Exception:
        raise Http404("Unable to open file")

    filename = os.path.basename(attachment.file.name)
    response = FileResponse(file_handle, as_attachment=True, filename=filename)
    return response


def edit_employee(request, employee_id):
    employee = get_object_or_404(Employee, id=employee_id)

    if request.method == "POST":
        form = EmployeeForm(request.POST, request.FILES, instance=employee)
        formset = PreviousEmploymentFormSet(request.POST, instance=employee)
        attachment_formset = EmployeeAttachmentFormSet(request.POST, request.FILES, instance=employee)

        if form.is_valid() and formset.is_valid() and attachment_formset.is_valid():
            form.save()
            formset.save()
            attachment_formset.save()
            return JsonResponse({"success": True})
    else:
        form = EmployeeForm(instance=employee)
        formset = PreviousEmploymentFormSet(instance=employee)
        attachment_formset = EmployeeAttachmentFormSet(instance=employee)

    return render(request, "employee/edit_employee_form.html", {
        "form": form,
        "formset": formset,
        "attachment_formset": attachment_formset,
        "employee": employee,
    })


# def create_offboarding(request):
#     if request.method == 'POST':
#         print('POST data:', request.POST)  # Debugging line
#         form = OffboardingForm(request.POST, request.FILES)
#         if form.is_valid():
#             form.save()
#             return redirect('home')  # Redirect after successful save
#         else:
#             print(form.errors)  # Debugging validation errors
#     else:
#         form = OffboardingForm()
#     employees = Employee.objects.all() 
#     offboarding = Offboarding.objects.all() 
#     context = {
#         'form': form,
#         'employees': employees,
#         'offboarding': offboarding,
#     }
#     return render(request, 'employee/offboarding2.html', context)

def create_offboarding(request):
    if request.method == 'POST':
        form = OffboardingForm(request.POST, request.FILES)
        formset = AssetHandoverFormSet(request.POST, request.FILES)
        # print('formset',formset)
        print('form',form)                                  
        # must bind formset to the parent only after parent is saved,
        # but to validate all at once we can pass prefix-less data and call is_valid() afterwards
        if form.is_valid():
            off = form.save(commit=False)
            # If you want to set any fields before saving, do here
            off.save()

            # bind formset to saved parent and passed POST/FILES
            formset = AssetHandoverFormSet(request.POST, request.FILES, instance=off)
            if formset.is_valid():
                formset.save()
                messages.success(request, "Offboarding saved successfully.")
                return redirect('create-offboarding')  # change to your url
            else:
                # formset invalid: delete saved off to prevent incomplete parent?
                # Usually better to leave parent and show errors (but you may delete)
                # off.delete()  # uncomment if you want to rollback
                messages.error(request, "Please fix asset handover errors.")
        else:
            messages.error(request, "Please fix the offboarding form errors.")

        # If errors, fall through and re-render template with both form & formset (form already bound)
        # Note: if the parent was saved and we didn't delete, re-render with bound formset we made
        # Ensure formset is bound to instance for rendering errors
        # If off was saved above, instance variable is `off`. If not saved, instance should be None
        if 'off' in locals():
            formset = AssetHandoverFormSet(request.POST, request.FILES, instance=off)
        else:
            formset = AssetHandoverFormSet(request.POST, request.FILES)
    else:
        form = OffboardingForm()
        formset = AssetHandoverFormSet()

    employees = Employee.objects.filter(status='Active')
    offboarding = Offboarding.objects.all()

    return render(request, 'employee/offboarding2.html', {
        'form': form,
        'formset': formset,
        'employees': employees,
        'offboarding': offboarding,

    })


def delete_offboarding(request, pk):
    if request.method == 'POST':
        offboarding = get_object_or_404(Offboarding, pk=pk)
        offboarding.delete()
        return JsonResponse({'success': True, 'message': 'Offboarding deleted successfully!'})
    return JsonResponse({'success': False, 'message': 'Invalid request.'})


# def create_branch(request):
#     if request.method == 'POST':
#         form = BranchForm(request.POST)
#         if form.is_valid():
#             form.save()
#             return redirect('admin-dashboard')  # Redirect after successful save
#         else:
#             print(form.errors)  # Debugging validation errors
#     else:
#         form = BranchForm()

#     context = {
#         'form': form,
#     }
#     return render(request, 'branch/create-branch.html', context)

def create_branchs(request):
    if request.method == "POST":
        branch_name = request.POST.get("branch_name")
        branch_address = request.POST.get("branch_address")
       
        # Save company to database
        branch = Branch.objects.create(
            branch_name=branch_name,
            branch_address=branch_address,          
        )
        messages.success(request, "Branch added successfully!")
        return redirect("create-branch")  # Redirect to company list page
    branches = Branch.objects.all()
    return render(request, "branch/create-branch.html",{"branches": branches})


def edit_branch(request, branch_id):
    branch = get_object_or_404(Branch, id=branch_id)

    if request.method == "POST":
        form = BranchForm(request.POST, instance=branch)
        if form.is_valid():
            form.save()
            messages.success(request, "Branch Updated successfully!")
            return redirect("create-branch")
    else:
        form = BranchForm(instance=branch)

    return render(request, "branch/_edit_branch_form.html", {"form": form, "branch": branch})


def get_branch(request, branch_id):
    branch = Branch.objects.get(id=branch_id)
    return JsonResponse({
        "branch_name": branch.branch_name,
        "branch_address": branch.branch_address,
        # "tan_number": company.tan_number,
        # "pan_number": company.pan_number,
        # "employer_pf": company.employer_pf,
        # "ptrc_number": company.ptrc_number,
        # "ptec_number": company.ptec_number,
        # "esic_number": company.esic_number,
        # "status": company.status,
    })

def delete_branch(request, branch_id):
    branch = get_object_or_404(Branch, id=branch_id)

    if request.method == "POST":
        branch.delete()
        messages.success(request, "Branch deleted successfully.")
        return redirect("create-branch")

    messages.error(request, "Invalid request.")
    return redirect("create-branch")

# def create_company(request):
#     if request.method == 'POST':
#         form = CompanyForm(request.POST)
#         if form.is_valid():
#             form.save()
#             return redirect('admin-dashboard')  # Redirect after successful save
#         else:
#             print(form.errors)  # Debugging validation errors
#     else:
#         form = CompanyForm()

#     context = {
#         'form': form,
#     }
#     return render(request, 'company/home2.html', context)
def create_company(request):
    if request.method == "POST":
        short_name = request.POST.get("short_name")
        name = request.POST.get("name")
        phone = request.POST.get("phone")
        email = request.POST.get("email")
        address = request.POST.get("address")
        tan_number = request.POST.get("tan_number")
        pan_number = request.POST.get("pan_number")
        employer_pf = request.POST.get("employer_pf")
        ptrc_number = request.POST.get("ptrc_number")
        ptec_number = request.POST.get("ptec_number")
        esic_number = request.POST.get("esic_number")

        if not short_name or not name or not address:
            messages.error(request, "Short Name, Company Name, and Address are required.")
            return redirect("add_company")  # Redirect back if validation fails

        # Save company to database
        company = Company.objects.create(
            short_name=short_name,
            name=name,
            phone=phone,
            email=email,
            address=address,
            tan_number=tan_number,
            pan_number=pan_number,
            employer_pf=employer_pf,
            ptrc_number=ptrc_number,
            ptec_number=ptec_number,
            esic_number=esic_number,
        )
        messages.success(request, "Company added successfully!")
        return redirect("create-company")  # Redirect to company list page
    companies = Company.objects.all()
    return render(request, "company/home2.html",{"companies": companies})




def edit_company(request, company_id):
    company = get_object_or_404(Company, id=company_id)

    if request.method == "POST":
        form = CompanyForm(request.POST, instance=company)   # ← IMPORTANT
        if form.is_valid():
            form.save()
            messages.success(request, "Company updated successfully.")
            return redirect("create-company")   # your listing page
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = CompanyForm(instance=company)   # ← IMPORTANT

    return render(request, "company/_edit_company_form.html", {"form": form, "company": company})


def get_company(request, company_id):
    company = Company.objects.get(id=company_id)
    return JsonResponse({
        "short_name": company.short_name,
        "name": company.name,
        "address": company.address,
        "tan_number": company.tan_number,
        "pan_number": company.pan_number,
        "employer_pf": company.employer_pf,
        "ptrc_number": company.ptrc_number,
        "ptec_number": company.ptec_number,
        "esic_number": company.esic_number,
        "status": company.status,
    })



def delete_company(request, company_id):
    company = get_object_or_404(Company, id=company_id)

    if request.method == "POST":
        company.delete()
        messages.success(request, "Company deleted successfully.")
        return redirect("create-company")

    messages.error(request, "Invalid request.")
    return redirect("create-company")


# def create_salary(request):
#     form = SalaryMasterForm()
#     return render(request,'employee/create_employee.html',{'form':form})




# def leave_balance_view(request):
#     employees = LeaveBalance.objects.all()  # Get all leave balances

#     if request.method == "POST":
#         employee_id = request.POST.get("employee_id")
#         from_date = request.POST.get("from_date")
#         to_date = request.POST.get("to_date")

#         # Convert input dates to datetime objects
#         from_date = datetime.strptime(from_date, "%Y-%m-%d").date()
#         to_date = datetime.strptime(to_date, "%Y-%m-%d").date()

#         # Get employee's leave balance record
#         leave_balance = get_object_or_404(LeaveBalance, employee_id=employee_id)

#         # Calculate leave details
#         leave_balance.calculate_leave_data(from_date, to_date)

#         return JsonResponse({
#             "status": "success",
#             "leave_balance": leave_balance.leave_balance,
#             "leave_taken": leave_balance.leave_taken,
#             "lwp": leave_balance.leave_without_pay,
#             "closing_balance": leave_balance.closing_balance
#         })

#     return render(request, "leave_balance/leave_balance.html", {"employees": employees})



def leave_balance_view(request):
    from datetime import date, timedelta
    from dateutil.relativedelta import relativedelta
    from django.db.models import Sum, F, OuterRef, Subquery, IntegerField

    today = date.today()
    start_of_month = today.replace(day=1)
    end_of_month = (start_of_month + relativedelta(months=1)) - timedelta(days=1)

    # ✅ Subquery to count approved comp-off days per employee
    compoff_subquery = CompOffRequest.objects.filter(
        employee=OuterRef('employee'),
        status="Approved",
        from_date__lte=end_of_month,
        to_date__gte=start_of_month
    ).annotate(
        total_days=(F('to_date') - F('from_date') + timedelta(days=1))
    ).values('total_days')[:1]

    # ✅ Get leave balances and comp-off count
    leave_balances = LeaveBalance.objects.select_related('employee').annotate(
        compoff_days=Subquery(compoff_subquery, output_field=IntegerField())
    )


    month_filter = request.GET.get("month")

    if month_filter:
        # If a month is selected, load history for that month
        leave_balances = LeaveBalanceHistory.objects.select_related("employee").filter(month=month_filter)
    else:
        # Default: show current month live balances
        leave_balances = LeaveBalance.objects.select_related("employee").all()
    months = LeaveBalanceHistory.objects.values_list("month", flat=True).distinct()

    return render(request, "leave_balance/leave_balance3.html", {
        "leave_balances": leave_balances,
        # "month": today.strftime("%B %Y"),
        "month": months,
        "selected_month": month_filter or "Current Month"
    })




def employee_leave_history(request, employee_id):
    """Return HTML for the employee’s month-by-month leave history."""
    history = LeaveBalanceHistory.objects.filter(employee_id=employee_id).order_by("-recorded_on")
    html = render_to_string("leave_balance/_leave_history_table.html", {"history": history})
    return JsonResponse({"html": html})

from website.signals import update_leave_balance_on_attendance
from django.views.decorators.http import require_POST

@require_POST
def recalculate_leave_balances(request):
    """
    Manually triggers recalculation of all leave balances.
    Uses the SAME attendance-based logic as the signal.
    """
    from website.models import LeaveBalance, Attendance

    records = LeaveBalance.objects.select_related("employee")

    for record in records:
        employee = record.employee
        last_att = Attendance.objects.filter(employee=employee).order_by("-date").first()

        if last_att:
            # call your existing signal method
            update_leave_balance_on_attendance(Attendance, last_att, created=False)

    return JsonResponse({"status": "ok", "message": "Leave balances recalculated successfully!"})


# def leave_credit_policy_view(request):
#     """Display the current company's leave credit policy."""
#     # Assuming HR is logged in and linked to a company
#     company = getattr(request.user, "company", None)
#     if not company:
#         return render(request, "leave_policy/leave_credit_policy.html", {"error": "No company found for user."})

#     policy, _ = LeaveCreditPolicy.objects.get_or_create(company=company)

#     return render(request, "leave_policy/leave_credit_policy.html", {
#         "policy": policy
#     })


def update_leave_credit_policy(request):
    """Handle policy updates from the HR UI (AJAX or form submit)."""
    if request.method == "POST":
        company = getattr(request.user, "company", None)
        if not company:
            return JsonResponse({"status": "error", "message": "No company found for user."})

        policy, _ = LeaveCreditPolicy.objects.get_or_create(company=company)

        policy.credit_1_limit = int(request.POST.get("credit_1_limit", 15))
        policy.credit_2_limit = int(request.POST.get("credit_2_limit", 25))
        policy.credit_low = Decimal(request.POST.get("credit_low", 0))
        policy.credit_mid = Decimal(request.POST.get("credit_mid", 1))
        policy.credit_high = Decimal(request.POST.get("credit_high", 2))
        policy.save()

        return JsonResponse({
            "status": "success",
            "message": "Leave Credit Policy updated successfully!"
        })

    return JsonResponse({"status": "error", "message": "Invalid request."})



# def recalc_leave_balances_view(request):
#     recalculate_all_leave_balances()
#     messages.success(request, "Leave balances recalculated successfully!")
#     return redirect("leave_balance")



def leave_credit_policy_view(request):
    # Assume HR selects the company or logged-in user company
    company = Company.objects.first()  # You can customise this

    policy, created = LeaveCreditPolicy.objects.get_or_create(company=company)

    if request.method == "POST":
        form = LeaveCreditPolicyForm(request.POST, instance=policy)
        if form.is_valid():
            form.save()
            messages.success(request, "Leave Credit Policy updated successfully!")
            return redirect("leave-credit-policy")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = LeaveCreditPolicyForm(instance=policy)

    return render(request, "leave_policy/leave_credit_policy.html", {
        "form": form,
        "company": company
    })








# def leave_balance_view(request):
#     month_filter = request.GET.get("month")

#     if month_filter:
#         # If a month is selected, load history for that month
#         leave_balances = LeaveBalanceHistory.objects.select_related("employee").filter(month=month_filter)
#     else:
#         # Default: show current month live balances
#         leave_balances = LeaveBalance.objects.select_related("employee").all()

#     # List of all months available for dropdown
#     months = LeaveBalanceHistory.objects.values_list("month", flat=True).distinct()

#     return render(request, "leave_balance/leave_balance2.html", {
#         "leave_balances": leave_balances,
#         "months": months,
#         "selected_month": month_filter or "Current Month"
#     })



def employee_compoff_details(request, employee_id):
    """Return comp-off details for a given employee (for modal)."""
    today = date.today()
    company = Company.objects.first()
    payroll_settings = PayrollSettings.objects.filter(company=company).first()
    
    print(payroll_settings.__dict__, "kkkkkk")
    print(company, "companiess")
    if payroll_settings:
        from_date, to_date = payroll_settings.get_payroll_period()
    else:
        from_date = today.replace(day=1)
        to_date = (today.replace(day=1) + relativedelta(months=1)) - timedelta(days=1)

    compoffs = CompOffRequest.objects.filter(
        employee_id=employee_id,
        status="Approved",
        from_date__gte=from_date,
        to_date__lte=to_date
    )

    total_days = 0 # Initialize total counter

    # ✅ Compute total days in Python so template stays simple
    for c in compoffs:
        if c.from_date and c.to_date:
            # Calculate days for this individual request
            c.days = (c.to_date - c.from_date).days + 1
            # Add to the running total
            total_days += c.days 
        else:
            c.days = 0

    html = render_to_string(
        "leave_balance/_compoff_modal_table.html", 
        {
            "compoffs": compoffs, 
            "total_compoff_days": total_days # Pass the total
        }
    )
    # The JsonResponse is usually for the modal itself, not the main page number.
    # It seems your issue is with the number on the *main* page.
    # If the main page number needs to be updated after this call, you'll need to modify the JS.
    return JsonResponse({"html": html, "total_days": total_days})


# @csrf_exempt
# def submit_comp_off_request(request):
#     if request.method == "POST":
#         data = json.loads(request.body)
#         employee_id = data.get("employee_id")
#         from_date = data.get("from_date")
#         to_date = data.get("to_date")
#         reason = data.get("reason")

#         employee = Employee.objects.get(id=employee_id)
#         comp_off = CompOff.objects.create(
#             employee=employee, 
#             from_date=from_date, 
#             to_date=to_date, 
#             reason=reason
#         )
#         return JsonResponse({"message": "Comp-Off request submitted successfully!"})
#     return JsonResponse({"error": "Invalid request"}, status=400)







@csrf_exempt
def submit_comp_off_request(request):
    if request.method == "POST":
        try:
            employee_id = request.POST.get("employee_id")
            from_date = request.POST.get("from_date")
            to_date = request.POST.get("to_date")
            reason = request.POST.get("reason")

            if not all([employee_id, from_date, to_date, reason]):
                return JsonResponse({"message": "Missing required fields"}, status=400)

            # Convert to date objects
            from_date_obj = datetime.strptime(from_date, "%Y-%m-%d").date()
            to_date_obj = datetime.strptime(to_date, "%Y-%m-%d").date()

            # ✅ Calculate count
            count = (to_date_obj - from_date_obj).days + 1

            employee = Employee.objects.get(id=employee_id)
            comp_off = CompOffRequest.objects.create(
                employee=employee, 
                from_date=from_date_obj, 
                to_date=to_date_obj, 
                reason=reason,
                count=count
            )

            return JsonResponse({"message": "Comp-Off request submitted successfully!"})

        except Exception as e:
            return JsonResponse({"message": f"Error: {str(e)}"}, status=400)
    return JsonResponse({"message": "Invalid request"}, status=400)






# def create_salary(request):
#     """A view to create a new SalaryMaster record with calculations in the view."""
#     if request.method == 'POST':
#         # 1. Parse form data (from request.POST)
#         employee_id = request.POST.get('employee')
#         pf_deducted = request.POST.get('pf_deducted') == 'on'  # checkbox
#         gratuity_applicable = request.POST.get('gratuity_applicable') == 'on'
#         esic_applicable = request.POST.get('esic_applicable') == 'on'

#         # Convert numeric inputs to Decimal safely
#         gross_ctc_pm = Decimal(request.POST.get('gross_ctc_pm') or '0')
#         basic_pm = Decimal(request.POST.get('basic_pm') or '0')
#         hra_pm = Decimal(request.POST.get('hra_pm') or '0')
#         guaranteed_cash_pm = Decimal(request.POST.get('guaranteed_cash_pm') or '0')

#         # 2. Perform calculations
#         # -- PF (Employer Contribution) --
#         # If PF is deducted: minimum of 1800 or 12% of basic
#         if pf_deducted:
#             pf_er_cont_pm = min(Decimal('1800'), basic_pm * Decimal('0.12'))
#         else:
#             pf_er_cont_pm = Decimal('0')

#         # -- Gratuity --
#         # 4.81% of Basic if applicable
#         gratuity_pm = Decimal('0')
#         if gratuity_applicable:
#             gratuity_pm = basic_pm * Decimal('0.0481')

#         # -- ESIC (Employer) --
#         # If guaranteed_cash <= 21000, 3.75% of guaranteed_cash
#         esic_er_cont_pm = Decimal('0')
#         if esic_applicable and guaranteed_cash_pm <= Decimal('21000'):
#             esic_er_cont_pm = guaranteed_cash_pm * Decimal('0.0375')

#         # -- ESIC (Employee) --
#         # If guaranteed_cash <= 21000, 0.25% (example from your sheet)
#         esic_ee_cont_pm = Decimal('0')
#         if esic_applicable and guaranteed_cash_pm <= Decimal('21000'):
#             esic_ee_cont_pm = guaranteed_cash_pm * Decimal('0.0025')

#         # -- Profession Tax (example logic) --
#         profession_tax_pm = Decimal('0')
#         if guaranteed_cash_pm > Decimal('10000'):
#             profession_tax_pm = Decimal('200')  # example threshold

#         # -- Net Salary PM --
#         # net_salary_pm = guaranteed_cash_pm - (PF(EE) + ESIC(EE) + profession tax)
#         # Suppose PF(EE) = same as PF(ER) or 12%? You can define your logic:
#         pf_ee_cont_pm = min(Decimal('1800'), basic_pm * Decimal('0.12')) if pf_deducted else Decimal('0')
#         net_salary_pm = guaranteed_cash_pm - (pf_ee_cont_pm + esic_ee_cont_pm + profession_tax_pm)

#         # 3. Create the SalaryMaster object
#         salary = SalaryMaster(
#             employee_id=employee_id,
#             pf_deducted=pf_deducted,
#             gratuity_applicable=gratuity_applicable,
#             esic_applicable=esic_applicable,

#             gross_ctc_pm=gross_ctc_pm,
#             gross_ctc_pa=gross_ctc_pm * Decimal('12'),
#             basic_pm=basic_pm,
#             basic_pa=basic_pm * Decimal('12'),
#             hra_pm=hra_pm,
#             hra_pa=hra_pm * Decimal('12'),
#             guaranteed_cash_pm=guaranteed_cash_pm,
#             guaranteed_cash_pa=guaranteed_cash_pm * Decimal('12'),

#             pf_er_cont_pm=pf_er_cont_pm,
#             pf_er_cont_pa=pf_er_cont_pm * Decimal('12'),
#             esic_er_cont_pm=esic_er_cont_pm,
#             esic_er_cont_pa=esic_er_cont_pm * Decimal('12'),
#             pf_ee_cont_pm=pf_ee_cont_pm,
#             pf_ee_cont_pa=pf_ee_cont_pm * Decimal('12'),
#             esic_ee_cont_pm=esic_ee_cont_pm,
#             esic_ee_cont_pa=esic_ee_cont_pm * Decimal('12'),
#             profession_tax_pm=profession_tax_pm,
#             profession_tax_pa=profession_tax_pm * Decimal('12'),

#             net_salary_pm=net_salary_pm,
#             net_salary_pa=net_salary_pm * Decimal('12'),
#         )
#         salary.save()

#         messages.success(request, f"Salary created for employee {salary.employee}!")
#         # return redirect('salary_list')  # or wherever you want

#     # If GET request, render a form
#     employees = Employee.objects.all()
#     context = {
#         'employees': employees
#     }
#     return render(request, 'salary/create_salary.html', context)

from django.conf import settings
from decimal import Decimal

# def create_salary(request):
#     if request.method == "POST":
#         employee_id = request.POST.get('employee')
#         employee = Employee.objects.get(pk=employee_id) if employee_id else None

#         # ✅ These come as 'yes'/'no' strings
#         pf_deducted = request.POST.get('pf_deducted', '').lower() == 'yes'
#         gratuity_applicable = request.POST.get('gratuity_applicable', '').lower() == 'yes'
#         esic_applicable = request.POST.get('esic_applicable', '').lower() == 'yes'

#         def get_decimal(field_name):
#             try:
#                 return Decimal(request.POST.get(field_name, '0') or '0')
#             except:
#                 return Decimal('0')

#         # ✅ Match the actual POST keys
#         gross_ctc_pm = get_decimal('gross_ctc_pm')
#         basic_pm = get_decimal('basic_pm')
#         hra_pm = get_decimal('hra_pm')
#         stat_bonus_pm = get_decimal('stat_bonus_pm')
#         allowance1_pm = get_decimal('allowance1_pm')
#         allowance2_pm = get_decimal('allowance2_pm')
#         special_allowance_pm = get_decimal('sp_allowance_pm')
#         guaranteed_cash_pm = get_decimal('guaranteed_cash_pm')
#         prof_tax_pm = get_decimal('profession_tax_pm')

#         pf_er_cont_pm = get_decimal('pf_er_cont_pm')
#         pf_ee_cont_pm = get_decimal('pf_ee_cont_pm')
#         esic_er_cont_pm = get_decimal('esic_er_cont_pm')
#         esic_ee_cont_pm = get_decimal('esic_ee_cont_pm')
#         gratuity_pm = get_decimal('gratuity_pm')
#         net_salary_pm = get_decimal('net_salary_pm')
#         cost_to_company_pm = get_decimal('ctc_pm')

#         instance = SalaryMaster(
#             employee=employee,
#             pf_deducted=pf_deducted,
#             gratuity_applicable=gratuity_applicable,
#             esic_applicable=esic_applicable,
#             gross_ctc_pm=gross_ctc_pm,
#             gross_ctc_pa=gross_ctc_pm * 12,
#             basic_pm=basic_pm,
#             basic_pa=basic_pm * 12,
#             hra_pm=hra_pm,
#             hra_pa=hra_pm * 12,
#             stat_bonus_pm=stat_bonus_pm,
#             stat_bonus_pa=stat_bonus_pm * 12,
#             sp_allowance_pm=special_allowance_pm,
#             sp_allowance_pa=special_allowance_pm * 12,
#             allowance1_pm=allowance1_pm,
#             allowance1_pa=allowance1_pm * 12,
#             allowance2_pm=allowance2_pm,
#             allowance2_pa=allowance2_pm * 12,
#             guaranteed_cash_pm=guaranteed_cash_pm,
#             guaranteed_cash_pa=guaranteed_cash_pm * 12,
#             gratuity_pm=gratuity_pm,
#             gratuity_pa=gratuity_pm * 12,
#             ctc_pm=cost_to_company_pm,
#             ctc_pa=cost_to_company_pm * 12,
#             pf_er_cont_pm=pf_er_cont_pm,
#             pf_er_cont_pa=pf_er_cont_pm * 12,
#             pf_ee_cont_pm=pf_ee_cont_pm,
#             pf_ee_cont_pa=pf_ee_cont_pm * 12,
#             esic_er_cont_pm=esic_er_cont_pm,
#             esic_er_cont_pa=esic_er_cont_pm * 12,
#             esic_ee_cont_pm=esic_ee_cont_pm,
#             esic_ee_cont_pa=esic_ee_cont_pm * 12,
#             profession_tax_pm=prof_tax_pm,
#             profession_tax_pa=prof_tax_pm * 12,
#             net_salary_pm=net_salary_pm,
#             net_salary_pa=net_salary_pm * 12,
#         )
#         instance.save()

#         return redirect('create-salary')

#     employees = Employee.objects.all()
#     salary = SalaryMaster.objects.all()
#     return render(request, 'salary/create_salary4.html', {'employees': employees, 'salary': salary})

def extract_decimal(request, key):
    """Safe decimal extraction helper."""
    try:
        return Decimal(request.POST.get(key, "0") or "0")
    except:
        return Decimal("0")


def create_salary(request):
    if request.method == "POST":

        # --------------------------
        # 🔹 1. BASIC FIELD EXTRACTION
        # --------------------------
        employee_id = request.POST.get('employee')
        employee = Employee.objects.get(pk=employee_id)

        pf_deducted = request.POST.get('pf_deducted', '').lower() == 'yes'
        gratuity_applicable = request.POST.get('gratuity_applicable', '').lower() == 'yes'
        esic_applicable = request.POST.get('esic_applicable', '').lower() == 'yes'

        # Extract all numbers
        data = {
            'gross_ctc_pm': extract_decimal(request, 'gross_ctc_pm'),
            'basic_pm': extract_decimal(request, 'basic_pm'),
            'hra_pm': extract_decimal(request, 'hra_pm'),
            'stat_bonus_pm': extract_decimal(request, 'stat_bonus_pm'),
            'allowance1_pm': extract_decimal(request, 'allowance1_pm'),
            'allowance2_pm': extract_decimal(request, 'allowance2_pm'),
            'sp_allowance_pm': extract_decimal(request, 'sp_allowance_pm'),
            'guaranteed_cash_pm': extract_decimal(request, 'guaranteed_cash_pm'),
            'profession_tax_pm': extract_decimal(request, 'profession_tax_pm'),

            'pf_er_cont_pm': extract_decimal(request, 'pf_er_cont_pm'),
            'pf_ee_cont_pm': extract_decimal(request, 'pf_ee_cont_pm'),
            'esic_er_cont_pm': extract_decimal(request, 'esic_er_cont_pm'),
            'esic_ee_cont_pm': extract_decimal(request, 'esic_ee_cont_pm'),

            'gratuity_pm': extract_decimal(request, 'gratuity_pm'),
            'net_salary_pm': extract_decimal(request, 'net_salary_pm'),
            'ctc_pm': extract_decimal(request, 'ctc_pm'),
        }

        # --------------------------
        # 🔹 2. SAVE SalaryMaster ENTRY
        # --------------------------

        sm = SalaryMaster.objects.create(
            employee=employee,
            pf_deducted=pf_deducted,
            gratuity_applicable=gratuity_applicable,
            esic_applicable=esic_applicable,

            gross_ctc_pm=data['gross_ctc_pm'],
            gross_ctc_pa=data['gross_ctc_pm'] * 12,
            basic_pm=data['basic_pm'],
            basic_pa=data['basic_pm'] * 12,
            hra_pm=data['hra_pm'],
            hra_pa=data['hra_pm'] * 12,
            stat_bonus_pm=data['stat_bonus_pm'],
            stat_bonus_pa=data['stat_bonus_pm'] * 12,
            allowance1_pm=data['allowance1_pm'],
            allowance1_pa=data['allowance1_pm'] * 12,
            allowance2_pm=data['allowance2_pm'],
            allowance2_pa=data['allowance2_pm'] * 12,
            sp_allowance_pm=data['sp_allowance_pm'],
            sp_allowance_pa=data['sp_allowance_pm'] * 12,
            guaranteed_cash_pm=data['guaranteed_cash_pm'],
            guaranteed_cash_pa=data['guaranteed_cash_pm'] * 12,

            gratuity_pm=data['gratuity_pm'],
            gratuity_pa=data['gratuity_pm'] * 12,
            pf_er_cont_pm=data['pf_er_cont_pm'],
            pf_er_cont_pa=data['pf_er_cont_pm'] * 12,
            pf_ee_cont_pm=data['pf_ee_cont_pm'],
            pf_ee_cont_pa=data['pf_ee_cont_pm'] * 12,
            esic_er_cont_pm=data['esic_er_cont_pm'],
            esic_er_cont_pa=data['esic_er_cont_pm'] * 12,
            esic_ee_cont_pm=data['esic_ee_cont_pm'],
            esic_ee_cont_pa=data['esic_ee_cont_pm'] * 12,

            profession_tax_pm=data['profession_tax_pm'],
            profession_tax_pa=data['profession_tax_pm'] * 12,
            net_salary_pm=data['net_salary_pm'],
            net_salary_pa=data['net_salary_pm'] * 12,
            ctc_pm=data['ctc_pm'],
            ctc_pa=data['ctc_pm'] * 12,
        )

        messages.success(request, "Salary created successfully.")
        return redirect('create-salary')

    # GET Request
    employees = Employee.objects.all()
    salary = SalaryMaster.objects.all()

    return render(request, 'salary/create_salary4.html', {
        'employees': employees,
        'salary': salary
    })




# salary detail view

def salary_details(request, pk):
    try:
        salary = SalaryMaster.objects.select_related('employee').get(pk=pk)
        data = {
            "employee_name": str(salary.employee),
            "gross_ctc_pm": float(salary.gross_ctc_pm),
            "gross_ctc_pa": float(salary.gross_ctc_pa),
            "basic_pm": float(salary.basic_pm),
            "hra_pm": float(salary.hra_pm),
            "stat_bonus_pm": float(salary.stat_bonus_pm),
            "sp_allowance_pm": float(salary.sp_allowance_pm),
            "guaranteed_cash_pm": float(salary.guaranteed_cash_pm),
            "pf_er_cont_pm": float(salary.pf_er_cont_pm),
            "pf_ee_cont_pm": float(salary.pf_ee_cont_pm),
            "esic_er_cont_pm": float(salary.esic_er_cont_pm),
            "esic_ee_cont_pm": float(salary.esic_ee_cont_pm),
            "gratuity_pm": float(salary.gratuity_pm),
            "profession_tax_pm": float(salary.profession_tax_pm),
            "net_salary_pm": float(salary.net_salary_pm),
            "net_salary_pa": float(salary.net_salary_pa),
            "ctc_pm": float(salary.ctc_pm),
            "ctc_pa": float(salary.ctc_pa),
            "pf_deducted": salary.pf_deducted,
            "esic_applicable": salary.esic_applicable,
            "gratuity_applicable": salary.gratuity_applicable,
        }
        return JsonResponse(data)
    except SalaryMaster.DoesNotExist:
        raise Http404("Salary not found")




# employee advance





def advances_list(request):
    advances = AdvanceMaster.objects.all().order_by('-created_on')
    employees = Employee.objects.all()
    return render(request, 'advance/advance_list.html', {'advances': advances, 'employees': employees})


@csrf_exempt
def create_advance(request):
    if request.method == "POST":
        emp_id = request.POST.get("employee")
        total_amount = request.POST.get("total_amount")
        start_month = request.POST.get("start_month")
        remarks = request.POST.get("remarks", "")

        employee = get_object_or_404(Employee, id=emp_id)
        adv = AdvanceMaster.objects.create(
            employee=employee,
            total_amount=total_amount,
            start_month=start_month + "-01",  # convert YYYY-MM to full date
            remarks=remarks
        )
        return JsonResponse({"status": "success", "message": "Advance created successfully!"})


@csrf_exempt
def add_installment(request, advance_id):
    advance = get_object_or_404(AdvanceMaster, id=advance_id)

    month = request.POST.get("month")
    amount = float(request.POST.get("amount"))
    remarks = request.POST.get("remarks", "")
    is_paid = request.POST.get("is_paid") == "on"

    AdvanceInstallment.objects.create(
        advance=advance,
        month=month + "-01",
        amount=amount,
        is_paid=is_paid,
        paid_on=timezone.now().date() if is_paid else None,
        remarks=remarks
    )

    if advance.remaining_amount_db <= 0:
        advance.is_closed = True
        advance.save()

    return JsonResponse({"status": "success", "message": "Installment recorded successfully!"})


def view_installments(request, advance_id):
    advance = get_object_or_404(AdvanceMaster, id=advance_id)
    installments = advance.installments.order_by('month')
    html = render_to_string("partials/installments_table.html", {"installments": installments})
    return JsonResponse({"html": html})


@csrf_exempt
def mark_paid(request, installment_id):
    inst = get_object_or_404(AdvanceInstallment, id=installment_id)
    inst.is_paid = True
    inst.is_skipped = False
    inst.paid_on = timezone.now().date()
    inst.save()

    advance = inst.advance
    if advance.remaining_amount_db <= 0:
        advance.is_closed = True
        advance.save()

    return JsonResponse({"message": "Installment marked as paid!"})


@csrf_exempt
def undo_paid(request, installment_id):
    inst = get_object_or_404(AdvanceInstallment, id=installment_id)
    inst.is_paid = False
    inst.paid_on = None
    inst.save()

    inst.advance.is_closed = False
    inst.advance.save()

    return JsonResponse({"message": "Installment reverted to pending!"})


@csrf_exempt
def skip_installment(request, installment_id):
    """✅ Mark this month's installment as skipped."""
    inst = get_object_or_404(AdvanceInstallment, id=installment_id)
    inst.is_skipped = True
    inst.is_paid = False
    inst.paid_on = None
    inst.save()
    return JsonResponse({"message": "Installment skipped for this month!"})



# Salary Increment****************




def D(request, key):
    try:
        return Decimal(request.POST.get(key, "0") or "0")
    except:
        return Decimal("0")

def to_float(v):
    try:
        return float(v)
    except:
        return 0.0

def create_salary_increment(request):

    if request.method == "POST":

        employee = Employee.objects.get(id=request.POST.get("employee"))
        effective_date = datetime.strptime(request.POST.get("effective_date"), "%Y-%m-%d").date()

        # Flags
        pf = request.POST.get("pf_deducted") == "yes"
        esic = request.POST.get("esic_applicable") == "yes"
        gratuity = request.POST.get("gratuity_applicable") == "yes"

        # Monthly Values
        m = {
            "gross_ctc": to_float(D(request, "gross_ctc_pm")),
            "basic": to_float(D(request, "basic_pm")),
            "hra": to_float(D(request, "hra_pm")),
            "stat_bonus": to_float(D(request, "stat_bonus_pm")),
            "allowance1": to_float(D(request, "allowance1_pm")),
            "allowance2": to_float(D(request, "allowance2_pm")),
            "special_allowance": to_float(D(request, "sp_allowance_pm")),
            "guaranteed_cash": to_float(D(request, "guaranteed_cash_pm")),
            "professional_tax": to_float(D(request, "profession_tax_pm")),

            "pf_er": to_float(D(request, "pf_er_cont_pm")),
            "pf_ee": to_float(D(request, "pf_ee_cont_pm")),
            "esic_er": to_float(D(request, "esic_er_cont_pm")),
            "esic_ee": to_float(D(request, "esic_ee_cont_pm")),

            "gratuity": to_float(D(request, "gratuity_pm")),
            "net_salary": to_float(D(request, "net_salary_pm")),
            "ctc": to_float(D(request, "ctc_pm")),
        }

        # Annual Values
        a = {k: float(v * 12) for k, v in m.items()}

        # Final JSON
        change_set = {
            "flags": {
                "pf_deducted": pf,
                "esic_applicable": esic,
                "gratuity_applicable": gratuity,
            },
            "monthly": m,
            "annual": a,
        }

        SalaryIncrement.objects.create(
            employee=employee,
            effective_date=effective_date,
            change_set=change_set,
            is_processed=False
        )

        messages.success(request, "Increment created successfully.")
        return redirect("salary_increment")

    return render(request, "salary_increment/create_increment.html", {
        "employees": Employee.objects.all(),
        "increments": SalaryIncrement.objects.all(),
    })








def increment_details(request, pk):
    inc = SalaryIncrement.objects.get(id=pk)

    monthly = inc.change_set.get("monthly", {})
    flags = inc.change_set.get("flags", {})

    data = {
        "employee": str(inc.employee),
        "effective_date": inc.effective_date.strftime("%Y-%m-%d"),

        # monthly
        "gross_ctc_pm": monthly.get("gross_ctc"),
        "net_salary_pm": monthly.get("net_salary"),

        # extras
        "reason": inc.change_set.get("reason", ""),
        "is_processed": inc.is_processed,
        "flags": flags,
        "all_data": inc.change_set,
    }

    return JsonResponse(data)





# -------------------------
# Salary History list view
# -------------------------
def salary_history(request):
    qs = SalaryHistory.objects.select_related("employee").order_by("-end_date")

    # filters
    emp = request.GET.get("employee", "")
    date_from = request.GET.get("from", "")
    date_to = request.GET.get("to", "")

    if emp:
        qs = qs.filter(employee__employee_code__icontains=emp)

    if date_from:
        qs = qs.filter(start_date__gte=date_from)

    if date_to:
        qs = qs.filter(end_date__lte=date_to)

    employees = Employee.objects.all().order_by("employee_code")

    return render(request, "salary_increment/salary_history_list.html", {
        "history": qs,
        "employees": employees,
        "get": request.GET,
    })


# -------------------------
# AJAX: SalaryHistory detail (used by modal)
# -------------------------
def salary_history_detail(request, pk):
    entry = get_object_or_404(SalaryHistory, pk=pk)
    html = render_to_string("partials/salary_history_detail.html", {"entry": entry})
    return JsonResponse({"html": html})

# -------------------------
# Export to Excel
# -------------------------
def salary_history_export_excel(request):
    qs = SalaryHistory.objects.select_related("employee").order_by("-end_date")
    # apply same filters as list (to keep export consistent)
    q = request.GET.get("q", "").strip()
    emp_code = request.GET.get("employee_code", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    if q:
        qs = qs.filter(
            Q(employee__first_name__icontains=q) |
            Q(employee__last_name__icontains=q) |
            Q(employee__employee_code__icontains=q)
        )

    if emp_code:
        qs = qs.filter(
            Q(employee__employee_code__icontains=emp_code) |
            Q(employee__first_name__icontains=emp_code) |
            Q(employee__last_name__icontains=emp_code)
        )

    if date_from:
        try:
            d1 = datetime.strptime(date_from, "%Y-%m-%d").date()
            qs = qs.filter(end_date__gte=d1)
        except ValueError:
            pass

    if date_to:
        try:
            d2 = datetime.strptime(date_to, "%Y-%m-%d").date()
            qs = qs.filter(start_date__lte=d2)
        except ValueError:
            pass

    # Create workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Salary History"

    headers = [
        "Employee Code", "Employee Name", "Start Date", "End Date",
        "Gross CTC (PM)", "Basic (PM)", "HRA (PM)", "Net Salary (PM)",
        "PF Deducted", "ESIC Applicable", "Gratuity Applicable", "Raw JSON"
    ]
    ws.append(headers)

    for e in qs:
        emp = e.employee
        salary = (e.data or {}).get("salary", {})
        row = [
            getattr(emp, "employee_code", ""),
            f"{getattr(emp,'first_name','') or ''} {getattr(emp,'last_name','') or ''}".strip(),
            e.start_date.isoformat() if e.start_date else "",
            e.end_date.isoformat() if e.end_date else "",
            salary.get("gross_ctc_pm", ""),
            salary.get("basic_pm", ""),
            salary.get("hra_pm", ""),
            salary.get("net_salary_pm", ""),
            e.data.get("pf_deducted", "") if e.data else "",
            e.data.get("esic_applicable", "") if e.data else "",
            e.data.get("gratuity_applicable", "") if e.data else "",
            str(e.data) if e.data else "",
        ]
        ws.append(row)

    # Prepare response
    f = io.BytesIO()
    wb.save(f)
    f.seek(0)
    filename = "salary_history.xlsx"
    resp = HttpResponse(f.read(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


# -------------------------
# Export to PDF (WeasyPrint)
# -------------------------
# from xhtml2pdf import pisa

# def salary_history_export_pdf(request):
#     qs = SalaryHistory.objects.select_related("employee").order_by("-end_date")

#     # Apply same filters used in list page
#     q = request.GET.get("q", "").strip()
#     emp_code = request.GET.get("employee_code", "").strip()
#     date_from = request.GET.get("date_from", "").strip()
#     date_to = request.GET.get("date_to", "").strip()

#     if q:
#         qs = qs.filter(
#             Q(employee__first_name__icontains=q) |
#             Q(employee__last_name__icontains=q) |
#             Q(employee__employee_code__icontains=q)
#         )

#     if emp_code:
#         qs = qs.filter(
#             Q(employee__employee_code__icontains=emp_code) |
#             Q(employee__first_name__icontains=emp_code) |
#             Q(employee__last_name__icontains=emp_code)
#         )

#     if date_from:
#         try:
#             d1 = datetime.strptime(date_from, "%Y-%m-%d").date()
#             qs = qs.filter(end_date__gte=d1)
#         except ValueError:
#             pass

#     if date_to:
#         try:
#             d2 = datetime.strptime(date_to, "%Y-%m-%d").date()
#             qs = qs.filter(start_date__lte=d2)
#         except ValueError:
#             pass

#     # Render HTML
#     html_string = render(request,"website/salary_history_pdf.html", {
#         "history": qs
#     })

#     # Generate PDF
#     response = HttpResponse(content_type="application/pdf")
#     response['Content-Disposition'] = 'attachment; filename="salary_history.pdf"'

#     pisa_status = pisa.CreatePDF(
#         html_string,
#         dest=response
#     )

#     if pisa_status.err:
#         return HttpResponse("Error creating PDF", status=500)

#     return response


# -------------------------
# Compare: return JSON of compare table (modal)
# -------------------------
def salary_compare(request, history_id, employee_id):
    history = SalaryHistory.objects.get(id=history_id)
    employee = Employee.objects.get(id=employee_id)
    current = SalaryMaster.objects.filter(employee=employee).first()

    # Convert SalaryMaster model → dict like history.data["salary"]
    current_salary = {}
    if current:
        for field in [
            "gross_ctc_pm", "basic_pm", "hra_pm", "stat_bonus_pm",
            "sp_allowance_pm", "allowance1_pm", "allowance2_pm",
            "guaranteed_cash_pm", "ctc_pm",
            "pf_er_cont_pm", "pf_ee_cont_pm",
            "esic_er_cont_pm", "esic_ee_cont_pm",
            "profession_tax_pm", "net_salary_pm"
        ]:
            current_salary[field] = str(getattr(current, field, 0) or 0)

    components = {
        "gross_ctc_pm": "Gross CTC",
        "basic_pm": "Basic",
        "hra_pm": "HRA",
        "stat_bonus_pm": "Stat Bonus",
        "sp_allowance_pm": "Special Allowance",
        "allowance1_pm": "Allowance 1",
        "allowance2_pm": "Allowance 2",
        "guaranteed_cash_pm": "Guaranteed Cash",
        "ctc_pm": "CTC",
        "pf_er_cont_pm": "PF Employer",
        "pf_ee_cont_pm": "PF Employee",
        "esic_er_cont_pm": "ESIC Employer",
        "esic_ee_cont_pm": "ESIC Employee",
        "profession_tax_pm": "Profession Tax",
        "net_salary_pm": "Net Salary",
    }

    html = render_to_string("partials/salary_compare.html", {
        "employee": employee,
        "old": history.data["salary"],
        "current": current_salary,      # 👉 FIXED
        "components": components
    })

    return JsonResponse({"html": html})

# -------------------------
# Chart data endpoint for timeline
# -------------------------
def salary_timeline_data(request, employee_id):
    # Return JSON data: labels = list of end_date, data = net_salary_pm values
    entries = SalaryHistory.objects.filter(employee_id=employee_id).order_by("end_date")
    labels = [e.end_date.isoformat() if e.end_date else "" for e in entries]
    data_points = [float((e.data or {}).get("salary", {}).get("net_salary_pm") or 0) for e in entries]
    return JsonResponse({"labels": labels, "data": data_points})


from django.core.files.storage import default_storage

def upload_salary_increment(request):
    if request.method == "POST" and request.FILES.get("excel_file"):
        excel_file = request.FILES["excel_file"]
        file_path = default_storage.save(f"temp/{excel_file.name}", excel_file)
        
        try:
            df = pd.read_excel(file_path)
            for _, row in df.iterrows():
                try:
                    employee = Employee.objects.get(pk=int(row["employee_id"]))
                    
                    new_increment = SalaryIncrement(
                        employee=employee,
                        pf_deducted=str(row["pf_deducted"]).lower() == 'yes',
                        gratuity_applicable=str(row["gratuity_applicable"]).lower() == 'yes',
                        esic_applicable=str(row["esic_applicable"]).lower() == 'yes',
                        
                        gross_ctc_pm=Decimal(row["gross_ctc_pm"]),
                        gross_ctc_pa=Decimal(row["gross_ctc_pm"]) * 12,
                        basic_pm=Decimal(row["basic_pm"]),
                        basic_pa=Decimal(row["basic_pm"]) * 12,
                        hra_pm=Decimal(row["hra_pm"]),
                        hra_pa=Decimal(row["hra_pm"]) * 12,
                        stat_bonus_pm=Decimal(row["stat_bonus_pm"]),
                        stat_bonus_pa=Decimal(row["stat_bonus_pm"]) * 12,
                        sp_allowance_pm=Decimal(row["special_allowance_pm"]),
                        sp_allowance_pa=Decimal(row["special_allowance_pm"]) * 12,
                        allowance1_pm=Decimal(row["allowance1_pm"]),
                        allowance1_pa=Decimal(row["allowance1_pm"]) * 12,
                        allowance2_pm=Decimal(row["allowance2_pm"]),
                        allowance2_pa=Decimal(row["allowance2_pm"]) * 12,
                        guaranteed_cash_pm=Decimal(row["guaranteed_cash_pm"]),
                        guaranteed_cash_pa=Decimal(row["guaranteed_cash_pm"]) * 12,
                        ctc_pm=Decimal(row["cost_to_company_pm"]),
                        ctc_pa=Decimal(row["cost_to_company_pm"]) * 12,
                        pf_er_cont_pm=Decimal(row["pf_er_cont_pm"]),
                        pf_er_cont_pa=Decimal(row["pf_er_cont_pm"]) * 12,
                        esic_er_cont_pm=Decimal(row["esic_er_cont_pm"]),
                        esic_er_cont_pa=Decimal(row["esic_er_cont_pm"]) * 12,
                        pf_ee_cont_pm=Decimal(row["pf_ee_cont_pm"]),
                        pf_ee_cont_pa=Decimal(row["pf_ee_cont_pm"]) * 12,
                        esic_ee_cont_pm=Decimal(row["esic_ee_cont_pm"]),
                        esic_ee_cont_pa=Decimal(row["esic_ee_cont_pm"]) * 12,
                        profession_tax_pm=Decimal(row["profession_tax_pm"]),
                        profession_tax_pa=Decimal(row["profession_tax_pm"]) * 12,
                        net_salary_pm=Decimal(row["net_salary_pm"]),
                        net_salary_pa=Decimal(row["net_salary_pm"]) * 12,
                    )
                    new_increment.save()
                except Exception as e:
                    messages.error(request, f"Error processing row {row}: {str(e)}")
        except Exception as e:
            messages.error(request, f"Error reading file: {str(e)}")
        finally:
            default_storage.delete(file_path)
        
        messages.success(request, "Salary increments uploaded successfully!")
        return redirect("upload_salary_increment")

    return render(request, "salary_increment/upload_increment.html")



def get_payroll_settings(request):
    settings = PayrollSettings.objects.first()
    if settings is None:
        # Handle the case where no payroll settings exist
        return JsonResponse({
            'error': 'Payroll settings not found. Please configure them.',
            'pf_percentage': 0.0, # Provide default values or handle as needed
            'esic_percentage': 0.0,
            'gratuity_percentage': 0.0,
            'professional_tax': 0.0,
            'bonus_percentage': 0.0,
            'basic_percentage': 0.0,
            'hra_percentage': 0.0,
            'basic_cap': 0.0,
            # ... other fields
        }, status=404) # Return a 404 Not Found status
    else:
        return JsonResponse({
            'pf_percentage': float(settings.pf_percentage),
            'esic_percentage': float(settings.esic_percentage),
            'gratuity_percentage': float(settings.gratuity_percentage),
            'professional_tax': float(settings.professional_tax),
            'bonus_percentage': float(settings.bonus_percentage),
            'basic_percentage': float(settings.basic_percentage),
            'hra_percentage': float(settings.hra_percentage),
            'basic_cap': float(settings.basic_cap)
        })




# setting

# @login_required
# def settings_page(request):
#     company = Company.objects.first()  # adjust per your logic
#     company_id = company.id if company else None
#     payroll_settings, _ = PayrollSettings.objects.get_or_create(company=company_id)
#     leave_settings, _ = LeaveSettings.objects.get_or_create(id=1)

#     payroll_form = PayrollSettingsForm(instance=payroll_settings)
#     leave_form = LeaveSettingsForm(instance=leave_settings)

#     return render(request, "settings/settings_page.html", {
#         "payroll_form": payroll_form,
#         "leave_form": leave_form,
#     })



def settings_page(request):
    # Assuming you have a logged-in user's company (adjust as needed)
    company = Company.objects.first()  # or request.user.company
    # company_id = company.id if company else None

    # Get or create default settings
    payroll_settings, _ = PayrollSettings.objects.get_or_create(company=company)
    leave_settings, _ = LeaveSettings.objects.get_or_create()

    context = {
        "payroll_settings": payroll_settings,
        "leave_settings": leave_settings,
    }
    return render(request, "settings/settings_page.html", context)


# @login_required
@csrf_exempt
def save_payroll_settings(request):
    if request.method == "POST":
        company = Company.objects.first()  # or request.user.company
        settings, _ = PayrollSettings.objects.get_or_create(company=company)

        settings.is_auto = request.POST.get("is_auto") == "on"
        settings.from_date = request.POST.get("from_date") or None
        settings.to_date = request.POST.get("to_date") or None
        settings.grace_period_minutes = request.POST.get("grace_period_minutes") or 15
        settings.basic_percentage = request.POST.get("basic_percentage") or 50
        settings.hra_percentage = request.POST.get("hra_percentage") or 60
        settings.basic_cap = request.POST.get("basic_cap") or 21000
        settings.pf_percentage = request.POST.get("pf_percentage") or 12
        settings.esic_percentage = request.POST.get("esic_percentage") or 3.67
        settings.gratuity_percentage = request.POST.get("gratuity_percentage") or 4.61
        settings.professional_tax = request.POST.get("professional_tax") or 200
        settings.bonus_percentage = request.POST.get("bonus_percentage") or 8.33

        settings.save()
        return JsonResponse({"success": True, "message": "Payroll settings saved successfully!"})
    return JsonResponse({"success": False, "message": "Invalid request"})


# @login_required
@csrf_exempt
def save_leave_settings(request):
    if request.method == "POST":
        settings, _ = LeaveSettings.objects.get_or_create()

        settings.carry_forward = request.POST.get("carry_forward") == "on"
        reset_month = request.POST.get("reset_month")
        settings.reset_month = int(reset_month) if reset_month else None

        settings.save()
        return JsonResponse({"success": True, "message": "Leave settings saved successfully!"})
    return JsonResponse({"success": False, "message": "Invalid request"})
