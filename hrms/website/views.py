from urllib import request

from django.shortcuts import render, redirect,get_object_or_404
from .forms import *
from django.http import HttpResponse, Http404
# from .tasks import *
# Create your views here.
from django.utils.timezone import make_aware
import datetime
from django.contrib import messages
import pandas as pd
from django.http import HttpResponse
from .models import *  # Import your Employee model
from datetime import datetime,timedelta,time
from django.http import JsonResponse, HttpResponseBadRequest
from django.utils.timezone import now
import json
from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate, login, logout
from datetime import date, timedelta
from decimal import Decimal
from django.core.paginator import Paginator
from dateutil.relativedelta import relativedelta
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Sum
# from .signals import recalculate_leave_balance_for_employee
from django.db.models import Q
import io
import os
from django.http import FileResponse, Http404
import openpyxl
from .services import *  # from previous services.py
from django.forms.models import model_to_dict
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import permission_required
from .utils.decorators import group_required

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
@login_required
@group_required("Admin", "HR")

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


@login_required
@group_required("Admin", "HR")
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
@login_required
@group_required("Admin", "HR")
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
    """
    Convert time value to a proper datetime.time object.
    Handles multiple formats:
    - Excel time format (decimal 0-1)
    - String format "HH:MM:SS" or "HH:MM"
    - datetime.time objects
    - Pandas Timestamp objects
    """
    if pd.isna(time_value) or time_value is None:
        return None
    
    # If it's already a time object, return it
    if isinstance(time_value, time):
        return time_value
    
    # If it's a pandas Timestamp, extract the time
    if isinstance(time_value, pd.Timestamp):
        return time_value.time()
    
    # Convert to string and strip whitespace
    time_str = str(time_value).strip()
    
    if not time_str or time_str.lower() == 'nan':
        return None
    
    # Try to parse as string format (HH:MM:SS or HH:MM)
    for fmt in ["%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p"]:
        try:
            return datetime.strptime(time_str, fmt).time()
        except ValueError:
            continue
    
    # If all string formats fail, try to handle Excel decimal format
    try:
        # Excel stores time as decimal where 0.5 = 12:00 PM
        time_float = float(time_value)
        if 0 <= time_float <= 1:
            seconds = int(time_float * 86400)  # 86400 seconds in a day
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            secs = seconds % 60
            return time(hours, minutes, secs)
    except (ValueError, TypeError):
        pass
    
    print(f"⚠️ Could not parse time value: {time_value} (type: {type(time_value).__name__})")
    return None





def fill_holiday_attendance_for_month(year, month):
    from calendar import monthrange
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])
    
    # Get setting
    payroll_settings = PayrollSettings.objects.first()
    branch_specific = getattr(payroll_settings, 'branch_specific_holidays', True)
    
    # Get all holidays in month
    all_holidays = Holiday.objects.filter(
        holiday_date__gte=first_day,
        holiday_date__lte=last_day
    ).select_related('holiday_calendar__branch')
    
    # Get half-day scenarios with branch info
    half_day_scenarios = HalfDayScenario.objects.filter(
        scenario_date__gte=first_day,
        scenario_date__lte=last_day,
        is_approved=True
    ).select_related('branch')
    
    # Build half-day dict: {date: set(branch_ids)}
    half_day_by_date = {}
    for s in half_day_scenarios:
        half_day_by_date.setdefault(s.scenario_date, set()).add(s.branch_id)
    
    employees = Employee.objects.filter(status='Active').select_related('branch')
    created_count = 0
    
    for employee in employees:
        dates_to_create = set()
        
        # Determine which holiday dates apply to this employee
        for holiday in all_holidays:
            if holiday.is_national:
                # National holidays apply to everyone always
                dates_to_create.add(holiday.holiday_date)
            elif not branch_specific:
                # Branch-specific setting is OFF — all holidays apply to all
                dates_to_create.add(holiday.holiday_date)
            else:
                # Branch-specific ON — only apply if branch matches
                if (employee.branch_id and 
                    holiday.holiday_calendar.branch_id == employee.branch_id):
                    dates_to_create.add(holiday.holiday_date)
        
        # Half-day dates only apply if employee's branch matches
        for hd_date, branch_ids in half_day_by_date.items():
            if employee.branch_id and employee.branch_id in branch_ids:
                dates_to_create.add(hd_date)
        
        for special_date in dates_to_create:
            if Attendance.objects.filter(
                employee=employee, date=special_date
            ).exists():
                continue
            
            attendance = Attendance(
                employee=employee,
                date=special_date,
                in_time=None,
                out_time=None,
            )
            attendance.save()
            
            if attendance.status in ('Holiday', 'Present (Half-Day)'):
                created_count += 1
            else:
                attendance.delete()
    
    return created_count

# @login_required
# @group_required("Admin", "HR")    
# def upload_attendance_excel(request):
#     if request.method != "POST" or not request.FILES.get("attendance_file"):
#         return JsonResponse(
#             {"success": False, "message": "No file uploaded!"},
#             status=400
#         )

#     file = request.FILES["attendance_file"]

#     try:
#         # Read Excel with proper time parsing
#         df = pd.read_excel(file)

#         # Clean column names
#         df.columns = df.columns.str.strip()

#         print(f"📄 Columns found: {df.columns.tolist()}")
#         print(f"📊 Data types:\n{df.dtypes}\n")

#         for index, row in df.iterrows():
#             employee_code = row.get("Employee Code")
#             attendance_date = row.get("Date")
#             in_time_raw = row.get("In Time")
#             out_time_raw = row.get("Out Time")

#             # Validate mandatory fields
#             if not employee_code or pd.isna(attendance_date):
#                 print(f"⚠️ Invalid row {index}, skipping")
#                 continue

#             # Parse date & time
#             attendance_date = pd.to_datetime(attendance_date).date()
#             in_time = parse_time(in_time_raw)
#             out_time = parse_time(out_time_raw)

#             print(f"🔍 Row {index}: Employee={employee_code}, Date={attendance_date}, "
#                   f"In={in_time}, Out={out_time}")

#             # Fetch employee
#             employee = Employee.objects.filter(employee_code=employee_code).first()
#             if not employee:
#                 print(f"⚠️ Employee not found: {employee_code}")
#                 continue

#             # 🔐 Prevent overwrite (ANTI-CHEAT)
#             if Attendance.objects.filter(employee=employee, date=attendance_date).exists():
#                 print(
#                     f"🔒 Attendance already exists for {employee_code} on {attendance_date}, skipped"
#                 )
#                 continue

#             # ✅ Create attendance (NO calculation here)
#             attendance = Attendance(
#                 employee=employee,
#                 date=attendance_date,
#                 in_time=in_time if in_time else None,
#                 out_time=out_time if out_time else None,
#             )

#             try:
#                 attendance.save()  # 🔥 shift-based calculation happens here
#                 print(
#                     f"✅ Saved: {employee_code} | {attendance_date} | "
#                     f"In: {attendance.in_time} | Out: {attendance.out_time} | "
#                     f"Status: {attendance.status} | Count: {attendance.count}"
#                 )
#             except Exception as e:
#                 print(
#                     f"❌ Error saving attendance for {employee_code} "
#                     f"on {attendance_date}: {str(e)}"
#                 )
#                 continue

#         uploaded_months = set()
#         for index, row in df.iterrows():
#             attendance_date_raw = row.get("Date")
#             if attendance_date_raw and not pd.isna(attendance_date_raw):
#                 d = pd.to_datetime(attendance_date_raw).date()
#                 uploaded_months.add((d.year, d.month))

#         for year, month in uploaded_months:
#             count = fill_holiday_attendance_for_month(year, month)
#             print(f"✅ Auto-created {count} holiday/half-day attendance records for {month}/{year}")


#         messages.success(request, "Attendance uploaded successfully!")
#         return JsonResponse(
#             {"success": True, "message": "Attendance uploaded successfully!"}
#         )

#     except Exception as e:
#         print(f"❌ File processing error: {str(e)}")
#         messages.error(request, f"Error processing file: {str(e)}")
#         return JsonResponse(
#             {"success": False, "message": str(e)}
#         )

def upload_attendance_excel(request):

    if request.method != "POST":
        return JsonResponse({"success": False})

    file = request.FILES.get("attendance_file")

    upload = AttendanceUpload.objects.create(file=file)

    from .tasks import process_attendance_file
    process_attendance_file.delay(upload.id)

    return JsonResponse({
        "success": True,
        "upload_id": upload.id
    })
    
def attendance_upload_progress(request, upload_id):

    upload = AttendanceUpload.objects.get(id=upload_id)

    if upload.total_rows == 0:
        progress = 0
    else:
        progress = int((upload.processed_rows / upload.total_rows) * 100)

    return JsonResponse({
        "progress": progress,
        "status": upload.status
    })

    
@login_required
# @group_required("Admin", "HR")
def attendance_list(request):
    user = request.user

    # 🔁 If employee → redirect to own attendance page
    if user.groups.filter(name="Employee").exists():
        try:
            employee = user.employee_profile  # OneToOne relation
            return redirect(
                "employee_attendance_detail",
                employee_id=employee.id
            )
        except Exception:
            # Safety fallback if employee profile missing
            return redirect("dashboard")


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
        "selected_date": selected_date.isoformat(),
        "prev_date": prev_date.isoformat(),
        "next_date": next_date.isoformat(),
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



def employee_search(request):
    q = request.GET.get("q", "").strip()

    employees = Employee.objects.filter(
        Q(first_name__icontains=q) |
        Q(last_name__icontains=q) |
        Q(employee_code__icontains=q)
    )[:10]

    data = [
        {
            "id": emp.id,
            "name": f"{emp.first_name} {emp.last_name}",
            "code": emp.employee_code
        }
        for emp in employees
    ]

    return JsonResponse(data, safe=False)


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


# --- Date / Time helpers (platform-safe) ---
def _format_date(d):
    """Return 'Dec. 5, 2025' or None."""
    if not d:
        return None
    month_abbr = d.strftime("%b")  # e.g. "Dec"
    return f"{month_abbr}. {d.day}, {d.year}"

def _format_time(t):
    """Return '9 a.m.' or '1:30 p.m.' or '—' for None."""
    if not t:
        return "—"
    hour_24 = t.hour
    minute = t.minute
    period = "a.m." if hour_24 < 12 else "p.m."
    hour_12 = hour_24 % 12
    if hour_12 == 0:
        hour_12 = 12
    if minute == 0:
        return f"{hour_12} {period}"
    return f"{hour_12}:{minute:02d} {period}"

def _format_date_iso(d):
    """Return ISO string or None."""
    return d.isoformat() if d else None

def attendance_correction_requests_list(request):
    from .models import AttendanceCorrectionRequest, Attendance

    # Base queryset
    base_qs = AttendanceCorrectionRequest.objects.select_related("attendance__employee")

    # Dropdown values from Attendance table
    years = Attendance.objects.dates("date", "year", order="DESC")

    raw_months_all = Attendance.objects.dates("date", "month", order="DESC")

    # --- Deduplicate months (2024-Nov & 2025-Nov appear only once) ---
    seen_months = set()
    months_all = []
    for m in raw_months_all:
        if m.month not in seen_months:
            seen_months.add(m.month)
            months_all.append(m)

    # Read filters
    selected_year = request.GET.get("year", "").strip()
    selected_month = request.GET.get("month", "").strip()

    # Start with all correction requests
    qs = base_qs

    # ----------------
    # YEAR FILTER
    # ----------------
    if selected_year:
        try:
            year_int = int(selected_year)
            qs = qs.filter(attendance__date__year=year_int)

            # Build month dropdown only for that year (also deduped)
            raw_months_year = Attendance.objects.filter(date__year=year_int).dates(
                "date", "month", order="DESC"
            )

            seen = set()
            months_qs = []
            for m in raw_months_year:
                if m.month not in seen:
                    seen.add(m.month)
                    months_qs.append(m)

        except ValueError:
            months_qs = months_all
    else:
        months_qs = months_all

    if selected_month:
        try:
            month_int = int(selected_month)
            qs = qs.filter(attendance__date__month=month_int)
        except ValueError:
            pass

    # Final ordering
    qs = qs.order_by("-created_at")

    # Build rows (your same structure)
    rows = []
    for req in qs:
        att = req.attendance
        emp = att.employee

        rows.append({
            "id": req.id,
            "emp_name": f"{emp.first_name} {emp.last_name}".strip(),
            "emp_code": emp.employee_code,
            "shift_date": att.date,
            "shift_date_str": _format_date(att.date),
            "old_in_time": _format_time(req.old_in_time),
            "old_out_time": _format_time(req.old_out_time),
            "new_in_time": _format_time(req.new_in_time),
            "new_out_time": _format_time(req.new_out_time),
            "status": req.status,
            "created_at": _format_date_iso(req.created_at),
        })

    # Render
    return render(request, "attendance/attendance_request_status.html", {
        "years": years,
        "months": months_qs,
        "selected_year": selected_year,
        "selected_month": selected_month,
        "attendance_requests": rows,
    })

def attendance_correction_detail(request, pk):
    obj = get_object_or_404(AttendanceCorrectionRequest, pk=pk)

    att = obj.attendance  # related Attendance object
    employee = att.employee  # related Employee object

    data = {
        "attendance": {
            "id": att.id,
            "date": att.date.isoformat() if att.date else None,
            "in_time": att.in_time.isoformat() if att.in_time else None,
            "out_time": att.out_time.isoformat() if att.out_time else None,
            "status": att.status,
        },
        "old_in_time": obj.old_in_time.isoformat() if obj.old_in_time else None,
        "old_out_time": obj.old_out_time.isoformat() if obj.old_out_time else None,
        "new_in_time": obj.new_in_time.isoformat() if obj.new_in_time else None,
        "new_out_time": obj.new_out_time.isoformat() if obj.new_out_time else None,
        "reason": obj.reason,
        "rejection_reason": obj.rejection_reason,
        "created_at": obj.created_at.strftime("%Y-%m-%d") if obj.created_at else None,
        "status": obj.status,
        "employee": {
            "id": employee.id,
            "first_name": employee.first_name,
            "last_name": employee.last_name,
            "employee_code": employee.employee_code,
        },
    }

    return JsonResponse(data)


# def comp_off_requests_list(request): 
#     # Pull attendance correction requests and avoid N+1 queries 
#     attendance_requests = CompOffRequest.objects.select_related( 'employee' ) 
#     rows = [] 
#     for r in attendance_requests: 
#         employee = r.employee # Employee object 
#         # employee = attendance.employee # Employee object 
#         # Build clean row for frontend table 
#         rows.append({ 
#             "id": r.id, 
#             "emp_name": f"{employee.first_name} {employee.last_name}".strip(), 
#             "emp_code": getattr(employee, "employee_code", "—"), 
#             "from_date": r.from_date,
#             "to_date": r.to_date,
#             "reason": r.reason,
#             "status": r.status,
#             }) 
#             # Debug print (optional) 
#             # for row in rows: 
#             # print(row) 
#         return render(request, "attendance/comp_off_request.html", { "attendance_requests": rows }) 
from django.db.models import Count
from django.db.models.functions import ExtractMonth, ExtractYear
import calendar        

# def comp_off_requests_list(request):

#     # read optional filters from GET
#     selected_year = request.GET.get("year")   # e.g. "2025" or empty
#     selected_month = request.GET.get("month") # e.g. "12" or empty

#     # base queryset: only requests that have from_date (safe)
#     qs = CompOffRequest.objects.filter(from_date__isnull=False).select_related("employee")

#     # annotate year/month using from_date
#     qs = qs.annotate(year=ExtractYear("from_date"), month=ExtractMonth("from_date"))

#     # apply filters if provided
#     if selected_year:
#         try:
#             qs = qs.filter(year=int(selected_year))
#         except ValueError:
#             pass
#     if selected_month:
#         try:
#             qs = qs.filter(month=int(selected_month))
#         except ValueError:
#             pass

#     # group by employee + year + month and count requests
#     grouped = (
#         qs.values(
#             "employee__id",
#             "employee__first_name",
#             "employee__last_name",
#             "employee__employee_code",
#             "year",
#             "month",
#         )
#         .annotate(requests_count=Count("id"))
#         .order_by("employee__employee_code", "year", "month")
#     )

#     # build rows for frontend
#     rows = []
#     for g in grouped:
#         month_num = g["month"]
#         month_name = calendar.month_abbr[month_num] if month_num else "—"
#         emp_name = f"{g['employee__first_name'] or ''} {g['employee__last_name'] or ''}".strip()

#         rows.append(
#             {
#                 "emp_id": g["employee__id"],
#                 "emp_code": g.get("employee__employee_code") or "—",
#                 "emp_name": emp_name or "—",
#                 "year": g.get("year"),
#                 "month": month_name,
#                 "month_number": month_num,
#                 "count": g["requests_count"],  # number of comp-off requests in that month
#             }
#         )

#     return render(
#         request,
#         "attendance/comp_off_request.html",
#         {
#             "comp_off_requests": rows,
#             "selected_year": selected_year,
#             "selected_month": selected_month,
#         },
#     )


import calendar
from django.db.models import Count
from django.db.models.functions import ExtractYear, ExtractMonth
from django.shortcuts import render

def comp_off_requests_list(request):
    # read optional filters from GET
    selected_year = request.GET.get("year")   # e.g. "2025" or ""
    selected_month = request.GET.get("month") # e.g. "12" or ""

    # base queryset: only requests that have from_date (safe)
    qs = CompOffRequest.objects.filter(from_date__isnull=False).select_related("employee")

    # annotate year/month using from_date
    qs = qs.annotate(year=ExtractYear("from_date"), month=ExtractMonth("from_date"))

    # Build distinct year/month lists from the annotated queryset for the dropdowns
    years_qs = qs.values("year").distinct().order_by("-year")
    years = [{"year": y["year"]} for y in years_qs if y.get("year") is not None]

    months_qs = qs.values("month").distinct().order_by("month")
    # convert numeric month to name for template convenience
    months = []
    for m in months_qs:
        mn = m.get("month")
        if mn:
            months.append({"month": mn, "name": calendar.month_name[mn]})

    # apply filters if provided
    if selected_year:
        try:
            qs = qs.filter(year=int(selected_year))
        except ValueError:
            pass
    if selected_month:
        try:
            qs = qs.filter(month=int(selected_month))
        except ValueError:
            pass

    # group by employee + year + month and count requests
    grouped = (
        qs.values(
            "employee__id",
            "employee__first_name",
            "employee__last_name",
            "employee__employee_code",
            "year",
            "month",
        )
        .annotate(requests_count=Count("id"))
        .order_by("employee__employee_code", "year", "month")
    )

    # build rows for frontend
    rows = []
    for g in grouped:
        month_num = g["month"]
        month_name = calendar.month_abbr[month_num] if month_num else "—"
        emp_name = f"{g['employee__first_name'] or ''} {g['employee__last_name'] or ''}".strip()

        rows.append(
            {
                "emp_id": g["employee__id"],
                "emp_code": g.get("employee__employee_code") or "—",
                "emp_name": emp_name or "—",
                "year": g.get("year"),
                "month": month_name,
                "month_number": month_num,
                "count": g["requests_count"],
            }
        )

    return render(
        request,
        "attendance/comp_off_request.html",
        {
            "comp_off_requests": rows,
            "selected_year": selected_year,
            "selected_month": selected_month,
            "years": years,
            "months": months,
        },
    )

from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from datetime import datetime
import datetime as dt


def comp_off_requests(request, pk):
    """
    Return all comp-off requests for the employee with id=pk for the requested month/year.
    Expects optional GET params: ?year=2025&month=12
    If year/month are missing, falls back to the current month/year.
    Renders a template fragment that can be loaded into a modal.
    """
    # ensure employee exists (optional, helpful for clearer 404)
    employee = get_object_or_404(Employee, pk=pk)

    # read optional filters from GET; fallback to current month/year
    selected_year = request.GET.get("year")
    selected_month = request.GET.get("month")

    now = timezone.now().date()
    try:
        year = int(selected_year) if selected_year else now.year
    except (TypeError, ValueError):
        year = now.year

    try:
        month = int(selected_month) if selected_month else now.month
    except (TypeError, ValueError):
        month = now.month

    # filter requests for the employee and month/year
    qs = (
        CompOffRequest.objects.filter(employee__id=pk, from_date__isnull=False)
        .filter(from_date__year=year, from_date__month=month)
        .order_by("from_date")
    )

    # build rows for the modal table (individual requests)
    rows = []
    for r in qs:
        rows.append(
            {
                "id": r.id,
                "from_date": r.from_date,
                "to_date": r.to_date,
                "days_count": r.count,    # the per-request day span from your model
                "reason": r.reason,
                "status": r.status,
                "rejection_reason": r.rejection_reason
            }
        )

    context = {
        "employee": employee,
        "year": year,
        "month": month,
        # "month_name": datetime.date(year, month, 1).strftime("%b"),
        "month_name": dt.date(year, month, 1).strftime("%b"),
        "comp_off_entries": rows,
    }

    # Render a fragment suitable for modal body
    return render(request, "attendance/comp_off_request_table.html", context)

@login_required(login_url="login")
@group_required("Admin", "HR")
def admin_dashboard(request):
    requests = AttendanceCorrectionRequest.objects.filter(status='Pending')  # Attendance approvals
    compoff_requests = CompOffRequest.objects.filter(status='Pending')  # CompOff approvals
    leave_requests = LeaveApplication.objects.select_related("employee").filter(status="Pending").order_by("-id")
    user = request.user
    today = date.today()
    current_month = date.today().month

    # Get the first day of the current month
    first_day_of_month = today.replace(day=1)

    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        employee = None    # Calculate the number of days

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
        "compoff_requests": compoff_requests,
        "leave_requests": leave_requests,
        "user": user,
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

# @csrf_exempt
# def reject_compoff(request, compoff_id):
#     if request.method == "POST":
#         try:
#             compoff = CompOffRequest.objects.get(id=compoff_id)
#             data = json.loads(request.body)
#             compoff.status = "Rejected"
#             compoff.rejection_reason = data.get("reason", "No reason provided")
#             compoff.save()
#             return JsonResponse({"message": "CompOff request rejected successfully!"})
#         except CompOffRequest.DoesNotExist:
#             return JsonResponse({"message": "Request not found!"}, status=404)

def reject_compoff(request, compoff_id):
    correction_request = get_object_or_404(CompOffRequest, id=compoff_id)

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


def download_employees_excel(request):
    # Fetch active employees
    employees = Employee.objects.filter(status="Active").values(
        "employee_code", "first_name", "middle_name", "last_name", "father_name",
        "gender", "blood_group", "date_of_birth", "place_of_birth",
        "personal_email", "personal_mobile", "present_address", "permanent_address",
        "date_of_marriage", "designation", "department", "date_of_joining",
        "date_of_confirmation", "location", "payroll_of", "shift_start_time", "shift_end_time",
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
        # "shift": "Shift",
        "shift_start_time": "Shift Start Time",
        "shift_end_time": "Shift End Time",
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


@login_required
def create_or_edit_employee(request, employee_id=None):
    employee = None
    is_edit = False

    if employee_id:
        employee = get_object_or_404(Employee, id=employee_id)
        is_edit = True

    if request.method == 'POST':
        form = EmployeeForm(
            request.POST,
            request.FILES,
            instance=employee
        )

        formset = PreviousEmploymentFormSet(
            request.POST,
            instance=employee
        )

        attachment_formset = AttachmentFormSet(
            request.POST,
            request.FILES,
            instance=employee
        )

        print("REQUEST METHOD:", request.method)
        print("EMPLOYEE ID FROM URL:", employee_id)
        print("EDIT MODE:", is_edit)
        print("EMPLOYEE INSTANCE:", employee)

        if form.is_valid() and formset.is_valid() and attachment_formset.is_valid():

            with transaction.atomic():

                emp_obj = form.save(commit=False)
                emp_obj.save()

                formset.instance = emp_obj
                attachment_formset.instance = emp_obj

                # ✅ SAVE PREVIOUS EMPLOYMENT + NESTED ATTACHMENTS
                for form in formset.forms:
                    if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                        continue

                    record = form.instance
                    record.employee = emp_obj
                    record.save()

                    form_index = form.prefix.split("-")[-1]

                    prefix = f"attach-{form_index}-"
                    file_keys = [k for k in request.FILES.keys() if k.startswith(prefix)]

                    for key in file_keys:
                        uploaded_file = request.FILES.get(key)
                        if not uploaded_file:
                            continue

                        file_index = key.split("-")[2]
                        doc_name = request.POST.get(
                            f"attach-{form_index}-{file_index}-document_name", ""
                        )

                        PreviousEmploymentAttachment.objects.create(
                            previous_employment=record,
                            file=uploaded_file,
                            document_name=doc_name
                        )

                # ✅ HANDLE DELETIONS
                # for obj in formset.deleted_objects:
                #     obj.delete()

                # ✅ SAVE EMPLOYEE ATTACHMENTS (AADHAAR / PAN / ETC)
                # attachment_formset.save()
                attachments = attachment_formset.save(commit=False)

                for attachment in attachments:
                    # ensure employee is set
                    attachment.employee = emp_obj

                    # 🔥 IMPORTANT LOGIC
                    if attachment.file_name == "other":
                        if not attachment.other_file_name:
                            # safety check (optional)
                            raise ValueError("Other file name is required when file type is Other")

                    attachment.save()

                # handle deletes
                for obj in attachment_formset.deleted_objects:
                    obj.delete()



                messages.success(
                    request,
                    "Employee updated successfully!" if is_edit else "Employee created successfully!"
                )

                return redirect("employee_create")

        else:
            print("FORM ERRORS:", form.errors)
            print("FORMSET ERRORS:", formset.errors)
            print("ATTACHMENT ERRORS:", attachment_formset.errors)
            messages.error(request, "Please correct the errors below.")

    else:
        form = EmployeeForm(instance=employee)
        formset = PreviousEmploymentFormSet(instance=employee)
        attachment_formset = AttachmentFormSet(instance=employee)

    return render(request, "employee/create_employee2.html", {
        "form": form,
        "formset": formset,
        "attachment_formset": attachment_formset,
        "employees": Employee.objects.all(),
        "is_edit": is_edit,
        "employee": employee,
    })



# @permission_required("website.view_employee", raise_exception=True)
@login_required
@group_required("Admin", "HR")
def employee_list(request):
    return render(request, "employee/create_employee2.html", {
        "form": EmployeeForm(),
        "formset": PreviousEmploymentFormSet(),
        "attachment_formset": AttachmentFormSet(),
        "employees": Employee.objects.all(),
        "is_edit": False,   # 🔴 IMPORTANT
    })




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

@login_required
def employee_detail(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    # employeement = PreviousEmployment.objects.filter(employee=employee)
    # previous_employments = employee.previous_employments.all().order_by('-to_date')
    previous_employments = PreviousEmployment.objects.filter(employee=employee).order_by('-to_date')
    previous_employments_attachment = PreviousEmploymentAttachment.objects.filter(previous_employment__employee=employee)
    # attachments = employee.attachments.all().order_by('-uploaded_at')
    attachments = EmployeeAttachment.objects.filter(employee=employee).order_by('-uploaded_at')
    salary = SalaryMaster.objects.filter(employee=employee, is_active=True).first()
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
        'previous_employments_attachment': previous_employments_attachment,
        'salary': salary,
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




@login_required
def my_profile(request):
    if not hasattr(request.user, 'employee_profile'):
        return redirect('dashboard')  # or raise PermissionDenied

    employee = request.user.employee_profile
    return redirect('employee_detail', pk=employee.pk)

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


# def employee_edit(request, pk):
#     employee = get_object_or_404(Employee, pk=pk)
#     form = EmployeeForm(instance=employee)
#     prev_formset = PreviousEmploymentFormSet(instance=employee)
#     attachment_formset = AttachmentFormSet(instance=employee)

#     if request.method == "POST":
#         form = EmployeeForm(request.POST, request.FILES, instance=employee)
#         prev_formset = PreviousEmploymentFormSet(request.POST, request.FILES, instance=employee)
#         attachment_formset = AttachmentFormSet(request.POST, request.FILES, instance=employee)

#         if form.is_valid() and prev_formset.is_valid() and attachment_formset.is_valid():
#             form.save()
#             prev_formset.save()
#             attachment_formset.save()
#             return redirect("employee_list")

#     return render(request, "employee/create_employee2.html", {
#         "form": form,
#         "formset": prev_formset,
#         "attachment_formset": attachment_formset
#     })

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



# Formset definition


# Formset definition

# Formset definition - Remove custom prefix, use Django default
# Create the formset
AssetHandoverFormSet = inlineformset_factory(
    Offboarding,
    AssetHandover,
    form=AssetHandoverForm,
    extra=0,
    can_delete=True
)

def offboarding_list(request):
    """Main page - List, Create, Edit, View, Delete all in one"""
    if request.method == 'POST':
        off_id = request.POST.get("offboarding_id")
        
        # Debug: Print all POST data
        print("=" * 50)
        print("POST Data:")
        for key, value in request.POST.items():
            print(f"{key} = {value}")
        print("=" * 50)
        
        if off_id:
            # EDIT MODE
            print(f"🔥 EDIT MODE - Offboarding ID: {off_id}")
            offboarding = get_object_or_404(Offboarding, id=off_id)
            form = OffboardingForm(request.POST, request.FILES, instance=offboarding)
            formset = AssetHandoverFormSet(request.POST, request.FILES, instance=offboarding)
        else:
            # CREATE MODE
            print("🆕 CREATE MODE")
            form = OffboardingForm(request.POST, request.FILES)
            # 🔥 CRITICAL: Use queryset=none() for new records
            if off_id:
                # EDIT MODE
                offboarding = get_object_or_404(Offboarding, id=off_id)
                form = OffboardingForm(request.POST, request.FILES, instance=offboarding)
                formset = AssetHandoverFormSet(
                    request.POST,
                    request.FILES,
                    instance=offboarding
                )
            else:
                # CREATE MODE
                form = OffboardingForm(request.POST, request.FILES)
                formset = AssetHandoverFormSet(
                    request.POST,
                    request.FILES,
                    instance=None    # 🔥 THIS IS CORRECT
                )

        
        # Debug formset data
        print(f"\nFormset Prefix: {formset.prefix}")
        print(f"TOTAL_FORMS: {request.POST.get(formset.prefix + '-TOTAL_FORMS')}")
        print(f"INITIAL_FORMS: {request.POST.get(formset.prefix + '-INITIAL_FORMS')}")
        
        # Debug: Print form errors
        print("\n📋 Form Valid:", form.is_valid())
        if not form.is_valid():
            print("Form Errors:", form.errors)
        
        print("📦 Formset Valid:", formset.is_valid())
        if not formset.is_valid():
            print("Formset Errors:", formset.errors)
            for i, form_err in enumerate(formset):
                if form_err.errors:
                    print(f"Form {i} Errors:", form_err.errors)
        
        if form.is_valid() and formset.is_valid():
            offboarding = form.save()
            formset.instance = offboarding
            formset.save()
            
            if off_id:
                messages.success(request, "Offboarding updated successfully!")
            else:
                messages.success(request, "Offboarding created successfully!")
            
            return redirect('offboarding-list')
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = OffboardingForm()
        formset = AssetHandoverFormSet(queryset=AssetHandover.objects.none())
    
    offboardings = Offboarding.objects.all().select_related('employee')
    employees = Employee.objects.filter(status='Active')
    
    return render(request, 'employee/offboarding2.html', {
        'form': form,
        'formset': formset,
        'offboardings': offboardings,
        'employees': employees,
    })

def offboarding_detail(request, off_id):
    """Return JSON data for view modal"""
    off = get_object_or_404(Offboarding, id=off_id)
    emp = off.employee
    assets = off.asset_handovers.all()

    asset_data = []
    for a in assets:
        asset_data.append({
            "asset_type": a.asset_type,
            "quantity": a.quantity,
            "condition": a.condition_on_return,
            "remarks": a.remarks or "-",
            "returned": "Yes" if a.returned else "No",
            "asset_photo": a.asset_photo.url if a.asset_photo else None,
            "receipt": a.receipt.url if a.receipt else None,
        })

    data = {
        # Employee
        "employee_code": emp.employee_code,
        "employee_name": str(emp),
        "email": getattr(emp, "email", "-"),
        "phone": getattr(emp, "phone_number", "-"),

        # Offboarding
        "resignation_date": off.date_of_resignation.strftime("%b %d, %Y") if off.date_of_resignation else "-",
        "relieving_date": off.date_of_relieving.strftime("%b %d, %Y") if off.date_of_relieving else "-",

        # Documents
        "experience_certificate": off.experience_certificate.url if off.experience_certificate else None,
        "relieving_letter": off.relieving_letter.url if off.relieving_letter else None,
        "other_documents": off.other_documents.url if off.other_documents else None,
        "fnf_documents": off.fnf_documents.url if off.fnf_documents else None,

        # Assets
        "assets": asset_data
    }

    return JsonResponse(data)

def offboarding_edit_data(request, id):
    """Return JSON data for edit modal"""
    off = get_object_or_404(Offboarding, id=id)
    assets = AssetHandover.objects.filter(offboarding=off)

    return JsonResponse({
        "offboarding": {
            "employee": off.employee_id,
            "date_of_resignation": off.date_of_resignation.strftime("%Y-%m-%d") if off.date_of_resignation else "",
            "date_of_relieving": off.date_of_relieving.strftime("%Y-%m-%d") if off.date_of_relieving else "",

            # File info (name + url)
            "experience_certificate": {
                "name": off.experience_certificate.name.split("/")[-1] if off.experience_certificate else "",
                "url": off.experience_certificate.url if off.experience_certificate else ""
            },
            "relieving_letter": {
                "name": off.relieving_letter.name.split("/")[-1] if off.relieving_letter else "",
                "url": off.relieving_letter.url if off.relieving_letter else ""
            },
            "other_documents": {
                "name": off.other_documents.name.split("/")[-1] if off.other_documents else "",
                "url": off.other_documents.url if off.other_documents else ""
            },
            "fnf_documents": {
                "name": off.fnf_documents.name.split("/")[-1] if off.fnf_documents else "",
                "url": off.fnf_documents.url if off.fnf_documents else ""
            },
        },

        "assets": [
            {
                "id": a.id,
                "asset_type": a.asset_type,
                "quantity": a.quantity,
                "condition": a.condition_on_return,
                "remarks": a.remarks or "",
                "returned": a.returned,

                # Asset files
                "asset_photo": {
                    "name": a.asset_photo.name.split("/")[-1] if a.asset_photo else "",
                    "url": a.asset_photo.url if a.asset_photo else ""
                },
                "receipt": {
                    "name": a.receipt.name.split("/")[-1] if a.receipt else "",
                    "url": a.receipt.url if a.receipt else ""
                },
            }
            for a in assets
        ]
    })

def offboarding_delete(request, pk):
    """Delete offboarding via AJAX"""
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
@login_required
@group_required("Admin")

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
        status = request.POST.get("status")

        if not short_name or not name or not address:
            messages.error(request, "Short Name, Company Name, and Address are required.")
            return redirect("create-company")  # Redirect back if validation fails

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
            status=status,
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



# def leave_balance_view(request):
#     """
#     Display leave balance with month filter
#     Shows current month by default, with option to view history
#     """
#     # Get selected month from query params
#     month_filter = request.GET.get("month")
    
#     # Get all unique months from history for the dropdown
#     available_months = (
#         LeaveBalanceHistory.objects
#         .values_list("month", flat=True)
#         .distinct()
#         .order_by("-month")
#     )
    
#     # Filter by company if user has company association
#     company_filter = {}
#     if hasattr(request.user, 'employee_profile'):
#         company_filter['employee__company'] = request.user.employee_profile.company
    
#     if month_filter:
#         # Show historical data for selected month
#         try:
#             selected_month = date.fromisoformat(month_filter)
#             leave_balances = LeaveBalanceHistory.objects.filter(
#                 month=selected_month,
#                 **company_filter
#             ).select_related('employee', 'employee__company', 'employee__branch')
            
#             display_month = selected_month.strftime("%B %Y")
#             is_current = False
            
#         except (ValueError, TypeError):
#             # Invalid date format, fallback to current
#             leave_balances = LeaveBalance.objects.filter(
#                 **company_filter
#             ).select_related('employee', 'employee__company', 'employee__branch')
            
#             display_month = "Current Month"
#             is_current = True
#     else:
#         # Show current leave balances
#         leave_balances = LeaveBalance.objects.filter(
#             **company_filter
#         ).select_related('employee', 'employee__company', 'employee__branch')
        
#         display_month = "Current Month"
#         is_current = True
    
#     # Order by employee code
#     leave_balances = leave_balances.order_by('employee__employee_code')
    
#     context = {
#         "leave_balances": leave_balances,
#         "available_months": available_months,
#         "selected_month": month_filter,
#         "display_month": display_month,
#         "is_current": is_current,
#     }
    
#     return render(request, "leave_balance/leave_balance.html", context)




def employee_leave_history(request, employee_id):
    """Return HTML for the employee’s month-by-month leave history."""
    history = LeaveBalanceHistory.objects.filter(employee_id=employee_id).order_by("-recorded_on")
    html = render_to_string("leave_balance/_leave_history_table.html", {"history": history})
    return JsonResponse({"html": html})

# from website.signals import update_leave_balance_on_attendance
from django.views.decorators.http import require_POST

# @require_POST
# def recalculate_leave_balances(request):
#     """
#     Manually triggers recalculation of all leave balances.
#     Uses the SAME attendance-based logic as the signal.
#     """
#     from website.models import LeaveBalance, Attendance

#     records = LeaveBalance.objects.select_related("employee")

#     for record in records:
#         employee = record.employee
#         last_att = Attendance.objects.filter(employee=employee).order_by("-date").first()

#         if last_att:
#             # call your existing signal method
#             update_leave_balance_on_attendance(Attendance, last_att, created=False)

#     return JsonResponse({"status": "ok", "message": "Leave balances recalculated successfully!"})


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



from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Min, Max
from datetime import date, timedelta
from decimal import Decimal
from website.models import LeaveBalance, Employee, PayrollSettings, Attendance, CompOffRequest
from django.db import transaction


def get_user_company(user):
    """Get company from user via employee relationship"""
    try:
        employee = Employee.objects.get(user=user)
        return employee.company
    except Employee.DoesNotExist:
        return None


def get_payroll_period_for_date(payroll_settings, target_date):
    """Determine which payroll period a date falls into"""
    if payroll_settings.is_auto:
        first_day = target_date.replace(day=1)
        if target_date.month == 12:
            last_day = date(target_date.year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = date(target_date.year, target_date.month + 1, 1) - timedelta(days=1)
        return first_day, last_day
    else:
        from_day = payroll_settings.from_date
        to_day = payroll_settings.to_date
        
        if from_day < to_day:
            if target_date.day >= from_day:
                from_d = date(target_date.year, target_date.month, from_day)
                to_d = date(target_date.year, target_date.month, to_day)
            else:
                prev_month = target_date.month - 1
                prev_year = target_date.year
                if prev_month == 0:
                    prev_month = 12
                    prev_year -= 1
                from_d = date(prev_year, prev_month, from_day)
                to_d = date(prev_year, prev_month, to_day)
        else:
            if target_date.day >= from_day:
                from_d = date(target_date.year, target_date.month, from_day)
                next_month = target_date.month + 1
                next_year = target_date.year
                if next_month > 12:
                    next_month = 1
                    next_year += 1
                to_d = date(next_year, next_month, to_day)
            else:
                prev_month = target_date.month - 1
                prev_year = target_date.year
                if prev_month == 0:
                    prev_month = 12
                    prev_year -= 1
                from_d = date(prev_year, prev_month, from_day)
                to_d = date(target_date.year, target_date.month, to_day)
        
        return from_d, to_d

def get_all_payroll_periods_from_attendance(company, payroll_settings):
    """Get all unique payroll periods that have attendance data"""
    periods = []
    
    attendance_stats = Attendance.objects.filter(
        employee__company=company
    ).aggregate(
        min_date=Min('date'),
        max_date=Max('date')
    )
    
    min_date = attendance_stats.get('min_date')
    max_date = attendance_stats.get('max_date')
    
    if not min_date or not max_date:
        return periods
    
    current_date = min_date
    seen_periods = set()
    
    while current_date <= max_date:
        from_d, to_d = get_payroll_period_for_date(payroll_settings, current_date)
        
        period_key = f"{from_d}_{to_d}"
        
        if period_key not in seen_periods:
            seen_periods.add(period_key)
            
            has_attendance = Attendance.objects.filter(
                employee__company=company,
                date__gte=from_d,
                date__lte=to_d
            ).exists()
            
            if has_attendance:
                label = f"{from_d.strftime('%b %d')} - {to_d.strftime('%b %d, %Y')}"
                periods.append({
                    'label': label,
                    'from_date': from_d,
                    'to_date': to_d,
                    'display_date': to_d,
                })
        
        current_date += timedelta(days=1)
    
    periods.sort(key=lambda x: x['to_date'], reverse=True)
    
    return periods


def get_monthly_earned_leaves(payroll_settings, month, year):
    """
    ✅ Get earned leaves for a specific month from database
    
    Instead of dividing by 12, reads from MonthlyEarnedLeaves table
    """
    try:
        monthly_leave = MonthlyEarnedLeaves.objects.get(
            payroll_settings=payroll_settings,
            month=month,
            year=year
        )
        return Decimal(str(monthly_leave.earned_leaves))
    except MonthlyEarnedLeaves.DoesNotExist:
        return Decimal('0.00')

def calculate_leave_balance_for_period(employee, payroll_settings, from_date, to_date):
    """
    ✅ UPDATED: Calculate leave balance for a specific payroll period
    Now reads monthly credit from MonthlyEarnedLeaves table
    """
    
    # ============================================
    # STEP 1: Opening Balance
    # Get PREVIOUS PERIOD's final balance (by period dates!)
    # ============================================
    prev_period_end = from_date - timedelta(days=1)
    prev_from, prev_to = get_payroll_period_for_date(payroll_settings, prev_period_end)
    
    previous_record = (
        LeaveBalance.objects
        .filter(
            employee=employee,
            period_from_date=prev_from,
            period_to_date=prev_to
        )
        .first()
    )
    
    opening_balance = (
        previous_record.final_leave_balance 
        if previous_record 
        else Decimal("0.00")
    )
    
    # Handle reset logic
    if not getattr(payroll_settings, 'carry_forward', True):
        reset_month = getattr(payroll_settings, 'reset_month', None)
        if reset_month and reset_month == to_date.month:
            opening_balance = Decimal("0.00")
    
    # ============================================
    # STEP 2: Attendance for THIS period
    # Exclude holidays (is_holiday=False)
    # ============================================
    attendance_records = Attendance.objects.filter(
        employee=employee,
        date__gte=from_date,
        date__lte=to_date,
        is_holiday=False  # ✅ Exclude holidays
    )
    
    total_days = attendance_records.count()
    
    # ============================================
    # STEP 3: Paid Days
    # ============================================
    paid_days_sum = attendance_records.aggregate(
        total=Sum("count")
    )["total"]
    paid_days = paid_days_sum if paid_days_sum else Decimal("0.00")
    
    # ============================================
    # STEP 4: Leave Taken
    # ============================================
    leave_taken = Decimal(str(total_days)) - paid_days
    if leave_taken < 0:
        leave_taken = Decimal("0.00")
    
    # ============================================
    # STEP 5: Late
    # ============================================
    total_late_minutes = attendance_records.aggregate(
        total=Sum("late")
    )["total"]
    total_late_minutes = total_late_minutes if total_late_minutes else 0
    
    late_days = Decimal(str(total_late_minutes)) / Decimal("480")
    
    # ============================================
    # STEP 6: Comp-Off
    # ============================================
    compoff_total = (
        CompOffRequest.objects
        .filter(
            employee=employee,
            status="Approved",
            from_date__gte=from_date,
            to_date__lte=to_date
        )
        .aggregate(total=Sum("count"))["total"]
        or Decimal("0.00")
    )
    
    # ============================================
    # STEP 7: LWP
    # ============================================
    balance_before_credit = opening_balance + compoff_total - leave_taken - late_days
    
    if balance_before_credit < 0:
        leave_without_pay = abs(balance_before_credit)
        leave_balance = Decimal("0.00")
    else:
        leave_without_pay = Decimal("0.00")
        leave_balance = balance_before_credit
    
    # ============================================
    # STEP 8: ✅ UPDATED - Get Monthly Credit from Database
    # Instead of: earned_leaves_per_year / 12
    # Now: Read from MonthlyEarnedLeaves table
    # ============================================
    monthly_credit = get_monthly_earned_leaves(
        payroll_settings, 
        to_date.month,      # Month of period end date
        to_date.year        # Year of period end date
    )
    
    # ============================================
    # STEP 9: Closing Balance
    # ============================================
    closing_balance = leave_balance + monthly_credit
    
    final_leave_balance = min(
        closing_balance,
        Decimal(str(payroll_settings.max_leave_balance))
    )
    
    # ============================================
    # STEP 10: Save Record (with period dates)
    # ============================================
    LeaveBalance.objects.update_or_create(
        employee=employee,
        period_from_date=from_date,
        period_to_date=to_date,
        defaults={
            'opening_balance': opening_balance,
            'leave_taken': leave_taken,
            'number_of_days_present': paid_days,
            'total_number_of_days': total_days,
            'late': total_late_minutes,
            'compoff': compoff_total,
            'leave_without_pay': leave_without_pay,
            'leave_balance': leave_balance,
            'closing_balance': closing_balance,
            'final_leave_balance': final_leave_balance
        }
    )
    
    return final_leave_balance



def generate_leave_balances_for_all_periods(company, payroll_settings):
    """Generate leave balance records for ALL periods"""
    
    periods = get_all_payroll_periods_from_attendance(company, payroll_settings)
    
    if not periods:
        return 0
    
    employees = Employee.objects.filter(company=company, status='Active')
    
    total_calculated = 0
    
    for period_info in periods:
        from_date = period_info['from_date']
        to_date = period_info['to_date']
        
        for employee in employees:
            try:
                with transaction.atomic():
                    calculate_leave_balance_for_period(
                        employee, 
                        payroll_settings, 
                        from_date, 
                        to_date
                    )
                    total_calculated += 1
            except Exception as e:
                print(f"Error: {employee.employee_code} {from_date}-{to_date}: {e}")
                continue
    
    return total_calculated


@login_required
def leave_balance_view(request):
    """
    Display leave balance report - Filters by selected period
    """
    user_company = get_user_company(request.user)
    
    context = {
        'user_company_id': user_company.id if user_company else None,
        'can_recalculate': bool(user_company),
    }
    
    if not user_company:
        context.update({
            'leave_balances': [],
            'display_month': date.today().strftime("%B %Y"),
            'available_periods': [],
        })
        return render(request, 'leave_balance/leave_balance_report.html', context)
    
    try:
        payroll_settings = PayrollSettings.objects.get(company=user_company)
    except PayrollSettings.DoesNotExist:
        context.update({
            'leave_balances': [],
            'error': 'Payroll settings not configured.'
        })
        return render(request, 'leave_balance/leave_balance_report.html', context)
    
    # Get ALL available periods
    available_periods = get_all_payroll_periods_from_attendance(user_company, payroll_settings)
    
    # Get selected period from request
    selected_period_str = request.GET.get('period')
    
    # Find selected period
    selected_period = None
    if selected_period_str and available_periods:
        for period in available_periods:
            if str(period['to_date']) == selected_period_str:
                selected_period = period
                break
    
    if not selected_period and available_periods:
        selected_period = available_periods[0]
    
    # ==========================================
    # Filter by selected period (period dates!)
    # ==========================================
    if selected_period:
        leave_balances = LeaveBalance.objects.filter(
            employee__company=user_company,
            employee__status='Active',
            period_from_date=selected_period['from_date'],
            period_to_date=selected_period['to_date']
        ).select_related('employee').order_by(
            'employee__first_name',
            'employee__last_name'
        )
    else:
        leave_balances = []
    
    # Format display
    if selected_period:
        display_month = selected_period['label']
    else:
        display_month = date.today().strftime("%b %d - %b %d, %Y")
    
    # Summary stats
    total_employees = leave_balances.count()
    
    if leave_balances.exists():
        total_lwp = sum(lb.leave_without_pay for lb in leave_balances)
        total_leaves_taken = sum(lb.leave_taken for lb in leave_balances)
        avg_balance = sum(lb.final_leave_balance for lb in leave_balances) / total_employees
    else:
        total_lwp = Decimal("0.00")
        total_leaves_taken = Decimal("0.00")
        avg_balance = Decimal("0.00")
    
    context.update({
        'leave_balances': leave_balances,
        'display_month': display_month,
        'available_periods': available_periods,
        'selected_period': str(selected_period['to_date']) if selected_period else None,
        'user_company_id': user_company.id,
        'user_company_name': getattr(user_company, 'name', 'Your Company'),
        'can_recalculate': True,
        'total_employees': total_employees,
        'total_lwp': float(total_lwp) if total_lwp else 0,
        'total_leaves_taken': float(total_leaves_taken) if total_leaves_taken else 0,
        'avg_balance': float(avg_balance) if avg_balance else 0,
    })
    
    return render(request, 'leave_balance/leave_balance_report.html', context)

@login_required
def recalculate_leave_balances_view(request):
    """Recalculate leave balances for all periods and employees"""
    
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'message': 'Invalid request method.'
        }, status=405)
    
    user_company = get_user_company(request.user)
    
    if not user_company:
        return JsonResponse({
            'success': False,
            'message': 'No company associated.'
        }, status=400)
    
    try:
        payroll_settings = PayrollSettings.objects.get(company=user_company)
        
        calculated_count = generate_leave_balances_for_all_periods(user_company, payroll_settings)
        
        return JsonResponse({
            'success': True,
            'message': f'✓ Successfully calculated {calculated_count} leave balances.',
            'recalculated_count': calculated_count
        })
        
    except PayrollSettings.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Payroll settings not found.'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)


@login_required
def recalc_employee_leave_balance(request, employee_id):
    """Recalculate for single employee"""
    if not request.user.is_staff:
        messages.error(request, "Permission denied.")
        return redirect("leave-balance")
    
    try:
        employee = Employee.objects.select_related('company').get(id=employee_id)
        
        user_company = get_user_company(request.user)
        if user_company and user_company.id != employee.company_id:
            messages.error(request, "Company mismatch.")
            return redirect("leave-balance")
        
        payroll_settings = PayrollSettings.objects.get(company=employee.company)
        
        periods = get_all_payroll_periods_from_attendance(employee.company, payroll_settings)
        count = 0
        
        for period in periods:
            calculate_leave_balance_for_period(
                employee,
                payroll_settings,
                period['from_date'],
                period['to_date']
            )
            count += 1
        
        messages.success(request, f"✓ Recalculated {count} periods for {employee.first_name}")
    except Exception as e:
        messages.error(request, f"Error: {str(e)}")
    
    return redirect("leave-balance")



@login_required
def recalc_all_employees(request):
    """Recalculate for all employees"""
    if not request.user.is_staff:
        messages.error(request, "Permission denied.")
        return redirect("leave-balance")
    
    user_company = get_user_company(request.user)
    
    if not user_company:
        messages.error(request, "No company.")
        return redirect("leave-balance")
    
    try:
        payroll_settings = PayrollSettings.objects.get(company=user_company)
        count = generate_leave_balances_for_all_periods(user_company, payroll_settings)
        messages.success(request, f"✓ Generated leave balances for {count} combinations.")
    except PayrollSettings.DoesNotExist:
        messages.error(request, "Payroll settings not found.")
    except Exception as e:
        messages.error(request, f"Error: {str(e)}")
    
    return redirect("leave-balance")


@login_required
def employee_leave_detail(request, employee_id):
    """Show detailed leave history for specific employee"""
    try:
        employee = Employee.objects.select_related('company').get(id=employee_id)
        
        if not request.user.is_staff:
            user_employee = Employee.objects.filter(user=request.user).first()
            if not user_employee or user_employee.id != employee_id:
                messages.error(request, "Permission denied.")
                return redirect("leave-balance")
        
        history = LeaveBalance.objects.filter(
            employee=employee
        ).order_by('-period_to_date')
        
        current_balance = history.first()
        
        context = {
            'employee': employee,
            'history': history,
            'current_balance': current_balance,
        }
        
        return render(request, 'leave_balance/employee_detail.html', context)
    
    except Employee.DoesNotExist:
        messages.error(request, "Employee not found.")
        return redirect("leave-balance")
    except Exception as e:
        messages.error(request, f"Error: {str(e)}")
        return redirect("leave-balance")

        

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






def leave_apply_view(request):
    leaves = LeaveApplication.objects.select_related("employee").order_by("-id")

    # ================== Filters ==================
    status = request.GET.get("status")
    search = request.GET.get("search")

    if status and status != "All":
        leaves = leaves.filter(status=status)

    if search:
        leaves = leaves.filter(
            Q(employee__first_name__icontains=search) | 
            Q(employee__last_name__icontains=search) |
            Q(leave_type__icontains=search)
        )

    # Pagination
    paginator = Paginator(leaves, 8)  # 8 rows per page
    page = request.GET.get("page")
    leaves = paginator.get_page(page)

    # ================== POST Submit ==================
    if request.method == "POST":
        form = LeaveApplicationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request,"Leave Applied Successfully!")
            return redirect("leave_apply")
        messages.error(request,"Please fix the errors.")
    else:
        form = LeaveApplicationForm()

    return render(request,"leave_balance/leave_apply.html",{
        "form":form,
        "leaves":leaves,
        "status":status,
        "search":search,
    })


@require_POST
def approve_leave(request, leave_id):
    try:
        leave = LeaveApplication.objects.get(id=leave_id)
        leave.status = "Approved"
        leave.save()

        return JsonResponse({"message": "Leave Approved Successfully!"})
    except:
        return JsonResponse({"message": "Leave not found"}, status=404)


@require_POST
def reject_leave(request, leave_id):
    try:
        data = json.loads(request.body)
        reason = data.get("reason")

        if not reason:
            return JsonResponse({"message": "Reason required"}, status=400)

        leave = LeaveApplication.objects.get(id=leave_id)
        leave.status = "Rejected"
        leave.save()

        return JsonResponse({"message": "Leave Rejected Successfully!"})
    except:
        return JsonResponse({"message": "Error while rejecting"}, status=404)


def leave_credit_policy_view(request):                           
    # Assume HR selects the company or logged-in user company
    company = Company.objects.first()  # You can customise this

    policy, created = LeaveCreditPolicy.objects.get_or_create(company=company)

    if request.method == "POST":
        form = LeaveCreditPolicyForm(request.POST, instance=policy)
        if form.is_valid():
            form.save()
            messages.success(request, "Leave Credit Policy updated successfully!")
            return redirect("admin-dashboard")
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




from datetime import datetime



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
        salary_id = request.POST.get("salary_id")
        employee_id = request.POST.get("employee")

        employee = Employee.objects.get(pk=employee_id)

        pf_deducted = request.POST.get("pf_deducted", "").lower() == "yes"
        gratuity_applicable = request.POST.get("gratuity_applicable", "").lower() == "yes"
        esic_applicable = request.POST.get("esic_applicable", "").lower() == "yes"

        data = {
            "gross_ctc_pm": extract_decimal(request, "gross_ctc_pm"),
            "basic_pm": extract_decimal(request, "basic_pm"),
            "hra_pm": extract_decimal(request, "hra_pm"),
            "stat_bonus_pm": extract_decimal(request, "stat_bonus_pm"),
            "allowance1_pm": extract_decimal(request, "allowance1_pm"),
            "allowance2_pm": extract_decimal(request, "allowance2_pm"),
            "sp_allowance_pm": extract_decimal(request, "sp_allowance_pm"),
            "guaranteed_cash_pm": extract_decimal(request, "guaranteed_cash_pm"),
            "profession_tax_pm": extract_decimal(request, "profession_tax_pm"),
            "pf_er_cont_pm": extract_decimal(request, "pf_er_cont_pm"),
            "pf_ee_cont_pm": extract_decimal(request, "pf_ee_cont_pm"),
            "esic_er_cont_pm": extract_decimal(request, "esic_er_cont_pm"),
            "esic_ee_cont_pm": extract_decimal(request, "esic_ee_cont_pm"),
            "gratuity_pm": extract_decimal(request, "gratuity_pm"),
            "net_salary_pm": extract_decimal(request, "net_salary_pm"),
            "ctc_pm": extract_decimal(request, "ctc_pm"),
        }

        if salary_id:
            sm = SalaryMaster.objects.get(pk=salary_id)
            message = "Salary updated successfully."
        else:
            sm = SalaryMaster(employee=employee)
            message = "Salary created successfully."

        sm.employee = employee
        sm.pf_deducted = pf_deducted
        sm.gratuity_applicable = gratuity_applicable
        sm.esic_applicable = esic_applicable

        for field, value in data.items():
            setattr(sm, field, value)
            setattr(sm, field.replace("_pm", "_pa"), value * 12)

        sm.save()

        messages.success(request, message)
        return redirect("create-salary")

    # 🔹 GET REQUEST
    employees = Employee.objects.all()
    salaries = SalaryMaster.objects.all()

    salary_id = request.GET.get("edit")
    salary_obj = SalaryMaster.objects.filter(pk=salary_id).first() if salary_id else None

    return render(request, "salary/create_salary4.html", {
        "employees": employees,
        "salary": salaries,
        "salary_obj": salary_obj,   # 👈 IMPORTANT
        "is_edit": bool(salary_obj)
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





# def advances_list(request):
#     advances = AdvanceMaster.objects.all().order_by('-created_on')
#     employees = Employee.objects.all()
#     return render(request, 'advance/advance_list.html', {'advances': advances, 'employees': employees})


# @csrf_exempt
# def create_advance(request):
#     if request.method == "POST":
#         emp_id = request.POST.get("employee")
#         total_amount = request.POST.get("total_amount")
#         start_month = request.POST.get("start_month")
#         remarks = request.POST.get("remarks", "")

#         employee = get_object_or_404(Employee, id=emp_id)
#         adv = AdvanceMaster.objects.create(
#             employee=employee,
#             total_amount=total_amount,
#             start_month=start_month + "-01",  # convert YYYY-MM to full date
#             remarks=remarks
#         )
#         return JsonResponse({"status": "success", "message": "Advance created successfully!"})


# @csrf_exempt
# def add_installment(request, advance_id):
#     advance = get_object_or_404(AdvanceMaster, id=advance_id)

#     month = request.POST.get("month")
#     amount = float(request.POST.get("amount"))
#     remarks = request.POST.get("remarks", "")
#     is_paid = request.POST.get("is_paid") == "on"

#     AdvanceInstallment.objects.create(
#         advance=advance,
#         month=month + "-01",
#         amount=amount,
#         is_paid=is_paid,
#         paid_on=timezone.now().date() if is_paid else None,
#         remarks=remarks
#     )

#     if advance.remaining_amount_db <= 0:
#         advance.is_closed = True
#         advance.save()

#     return JsonResponse({"status": "success", "message": "Installment recorded successfully!"})


# def view_installments(request, advance_id):
#     advance = get_object_or_404(AdvanceMaster, id=advance_id)
#     installments = advance.installments.order_by('month')
#     html = render_to_string("partials/installments_table.html", {"installments": installments})
#     return JsonResponse({"html": html})


# @csrf_exempt
# def mark_paid(request, installment_id):
#     inst = get_object_or_404(AdvanceInstallment, id=installment_id)
#     inst.is_paid = True
#     inst.is_skipped = False
#     inst.paid_on = timezone.now().date()
#     inst.save()

#     advance = inst.advance
#     if advance.remaining_amount_db <= 0:
#         advance.is_closed = True
#         advance.save()

#     return JsonResponse({"message": "Installment marked as paid!"})


# @csrf_exempt
# def undo_paid(request, installment_id):
#     inst = get_object_or_404(AdvanceInstallment, id=installment_id)
#     inst.is_paid = False
#     inst.paid_on = None
#     inst.save()

#     inst.advance.is_closed = False
#     inst.advance.save()

#     return JsonResponse({"message": "Installment reverted to pending!"})


# @csrf_exempt
# def skip_installment(request, installment_id):
#     """✅ Mark this month's installment as skipped."""
#     inst = get_object_or_404(AdvanceInstallment, id=installment_id)
#     inst.is_skipped = True
#     inst.is_paid = False
#     inst.paid_on = None
#     inst.save()
#     return JsonResponse({"message": "Installment skipped for this month!"})



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

# Add these to your views.py
def create_salary_increment(request):
    if request.method == "POST":
        try:
            employee = Employee.objects.get(id=request.POST.get("employee"))
            effective_date = datetime.strptime(
                request.POST.get("effective_date"), "%Y-%m-%d"
            ).date()

            # Flags
            pf = request.POST.get("pf_deducted") == "yes"
            esic = request.POST.get("esic_applicable") == "yes"
            gratuity = request.POST.get("gratuity_applicable") == "yes"

            # Monthly values
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

            # Annual
            a = {k: float(v * 12) for k, v in m.items()}

            SalaryIncrement.objects.create(
                employee=employee,
                effective_date=effective_date,
                change_set={
                    "reason": request.POST.get("reason", ""),
                    "flags": {
                        "pf_deducted": pf,
                        "esic_applicable": esic,
                        "gratuity_applicable": gratuity,
                    },
                    "monthly": m,
                    "annual": a,
                }
            )

            messages.success(request, "Increment created successfully.")
            return redirect("salary_increment")  # ✅ redirect to list

        except Exception as e:
            print("CREATE ERROR:", e)
            messages.error(request, "Failed to create increment.")

    return render(request, "salary_increment/create_increment.html", {
        "employees": Employee.objects.all(),
        "increments": SalaryIncrement.objects.all(),
    })
def edit_increment(request, pk):
    """Return increment data as JSON for editing"""
    try:
        inc = SalaryIncrement.objects.get(id=pk)
        
        monthly = inc.change_set.get("monthly", {})
        flags = inc.change_set.get("flags", {})
        
        data = {
            "id": inc.id,
            "employee_id": inc.employee.id,
            "effective_date": inc.effective_date.strftime("%Y-%m-%d"),
            "reason": inc.change_set.get("reason", ""),
            
            # Flags
            "pf_deducted": flags.get("pf_deducted", False),
            "esic_applicable": flags.get("esic_applicable", False),
            "gratuity_applicable": flags.get("gratuity_applicable", False),
            
            # Monthly values
            "gross_ctc": monthly.get("gross_ctc", 0),
            "basic": monthly.get("basic", 0),
            "hra": monthly.get("hra", 0),
            "stat_bonus": monthly.get("stat_bonus", 0),
            "allowance1": monthly.get("allowance1", 0),
            "allowance2": monthly.get("allowance2", 0),
            "special_allowance": monthly.get("special_allowance", 0),
            "guaranteed_cash": monthly.get("guaranteed_cash", 0),
            "professional_tax": monthly.get("professional_tax", 0),
            "pf_er": monthly.get("pf_er", 0),
            "pf_ee": monthly.get("pf_ee", 0),
            "esic_er": monthly.get("esic_er", 0),
            "esic_ee": monthly.get("esic_ee", 0),
            "gratuity": monthly.get("gratuity", 0),
            "net_salary": monthly.get("net_salary", 0),
            "ctc": monthly.get("ctc", 0),
        }
        
        return JsonResponse(data)
        
    except SalaryIncrement.DoesNotExist:
        return JsonResponse({"error": "Increment not found"}, status=404)


def update_salary_increment(request, pk):
    """Update existing increment"""
    if request.method == "POST":
        try:
            inc = SalaryIncrement.objects.get(id=pk)
            
            # Update employee and date
            inc.employee = Employee.objects.get(id=request.POST.get("employee"))
            inc.effective_date = datetime.strptime(request.POST.get("effective_date"), "%Y-%m-%d").date()
            
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
            
            # Update change_set
            inc.change_set = {
                "reason": request.POST.get("reason", ""),
                "flags": {
                    "pf_deducted": pf,
                    "esic_applicable": esic,
                    "gratuity_applicable": gratuity,
                },
                "monthly": m,
                "annual": a,
            }
            
            inc.save()
            messages.success(request, "Increment updated successfully.")
            return redirect("salary_increment")
            
        except SalaryIncrement.DoesNotExist:
            return JsonResponse({"error": "Increment not found"}, status=404)
    
    return JsonResponse({"error": "Invalid request"}, status=400)


def increment_details(request, pk):
    inc = get_object_or_404(SalaryIncrement, id=pk)

    return JsonResponse({
        "employee_code": inc.employee.employee_code,
        "employee_name": str(inc.employee),
        "effective_date": inc.effective_date.strftime("%d %b, %Y"),
        "reason": inc.change_set.get("reason", "-"),

        "monthly": inc.change_set.get("monthly", {}),
        "flags": inc.change_set.get("flags", {}),

        "status": "Applied" if inc.is_processed else "Pending"
    })




def delete_salary_increment(request, pk):
    """Delete increment"""
    if request.method == "POST":
        try:
            inc = SalaryIncrement.objects.get(id=pk)
            
            # Check if already processed
            if inc.is_processed:
                return JsonResponse({
                    "error": "Cannot delete processed increment"
                }, status=400)
            
            inc.delete()
            messages.success(request, "Increment deleted successfully.")
            return JsonResponse({"success": True})
            
        except SalaryIncrement.DoesNotExist:
            return JsonResponse({"error": "Increment not found"}, status=404)
    
    return JsonResponse({"error": "Invalid request"}, status=400)

def employee_salary_ajax(request):
    employee_id = request.GET.get("employee_id")

    if not employee_id:
        return JsonResponse({"error": "Employee ID required"}, status=400)

    employee = get_object_or_404(Employee, pk=employee_id)

    salary = (
        SalaryMaster.objects
        .filter(employee=employee, is_active=True)
        .order_by("-effective_date")
        .first()
    )

    if not salary:
        return JsonResponse({"salary_exists": False})

    return JsonResponse({
        "salary_exists": True,

        # Flags
        "pf_deducted": salary.pf_deducted,
        "esic_applicable": salary.esic_applicable,
        "gratuity_applicable": salary.gratuity_applicable,

        # Monthly values
        "grossCTC": salary.gross_ctc_pm,
        "basic": salary.basic_pm,
        "hra": salary.hra_pm,
        "statBonus": salary.stat_bonus_pm,
        "specialAllowance": salary.sp_allowance_pm,
        "allowance1": salary.allowance1_pm,
        "allowance2": salary.allowance2_pm,
        "guaranteedCash": salary.guaranteed_cash_pm,
        "pfEr": salary.pf_er_cont_pm,
        "pfEe": salary.pf_ee_cont_pm,
        "esicEr": salary.esic_er_cont_pm,
        "esicEe": salary.esic_ee_cont_pm,
        "gratuity": salary.gratuity_pm,
        "professionTax": salary.profession_tax_pm,
        "ctc": salary.ctc_pm,
        "netSalary": salary.net_salary_pm,
    })



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



# ── helpers ──────────────────────────────────────────────────────────────────

def get_user_company(request):
    """Return the Company for the logged-in user, or None."""
    try:
        return request.user.employee_profile.company
    except AttributeError:
        return None


# ── views ────────────────────────────────────────────────────────────────────

@login_required
def get_payroll_settings(request):
    company = get_user_company(request)
    if company is None:
        return JsonResponse(
            {'error': 'No company linked to your account.'},
            status=400
        )

    settings = PayrollSettings.objects.filter(company=company).first()
    if settings is None:
        return JsonResponse(
            {'error': 'Payroll settings not found. Please configure them.'},
            status=404
        )

    return JsonResponse({
        'pf_percentage':        float(settings.pf_percentage),
        'esic_percentage':      float(settings.esic_percentage),
        'gratuity_percentage':  float(settings.gratuity_percentage),
        'professional_tax':     float(settings.professional_tax),
        'bonus_percentage':     float(settings.bonus_percentage),
        'basic_percentage':     float(settings.basic_percentage),
        'hra_percentage':       float(settings.hra_percentage),
        'basic_cap':            float(settings.basic_cap),
    })


@login_required
def settings_page(request):
    company = get_user_company(request)
    if company is None:
        # You can redirect to an error page or show a message instead
        return render(request, 'settings/no_company.html', {
            'error': 'Your account is not linked to any company.'
        })

    payroll_settings, _ = PayrollSettings.objects.get_or_create(company=company)

    # ✅ FIX: LeaveSettings must also be scoped to company
    # Your LeaveSettings model needs a company FK — see note below
    leave_settings, _ = LeaveSettings.objects.get_or_create(company=company)

    context = {
        'company':          company,
        'payroll_settings': payroll_settings,
        'leave_settings':   leave_settings,
    }
    return render(request, 'settings/settings_page.html', context)


@login_required
@require_http_methods(["POST"])
def save_payroll_settings(request):
    company = get_user_company(request)
    if company is None:
        return JsonResponse({'success': False, 'error': 'No company linked to your account.'}, status=400)

    try:
        settings, _ = PayrollSettings.objects.get_or_create(company=company)

        # Boolean
        settings.is_auto = request.POST.get("is_auto") == "on"

        # Integers
        settings.from_date             = int(request.POST.get("from_date")) if request.POST.get("from_date") else None
        settings.to_date               = int(request.POST.get("to_date"))   if request.POST.get("to_date")   else None
        settings.grace_period_minutes  = int(request.POST.get("grace_period_minutes", 15))
        settings.max_leave_balance     = int(request.POST.get("max_leave_balance", 30))
        settings.earned_leaves_per_year = int(request.POST.get("earned_leaves_per_year", 12))

        # Floats / Decimals
        settings.basic_percentage    = float(request.POST.get("basic_percentage",    50))
        settings.hra_percentage      = float(request.POST.get("hra_percentage",      60))
        settings.basic_cap           = float(request.POST.get("basic_cap",        21000))
        settings.pf_percentage       = float(request.POST.get("pf_percentage",       12))
        settings.esic_percentage     = float(request.POST.get("esic_percentage",   3.67))
        settings.gratuity_percentage = float(request.POST.get("gratuity_percentage", 4.61))
        settings.bonus_percentage    = float(request.POST.get("bonus_percentage",   8.33))
        settings.professional_tax    = float(request.POST.get("professional_tax",    200))

        # Financial year + branch-specific holidays
        fy_month = request.POST.get("financial_year_start_month")
        if fy_month:
            old_fy = settings.financial_year_start_month
            new_fy = int(fy_month)
            settings.financial_year_start_month = new_fy

            if old_fy != new_fy:
                MonthlyEarnedLeaves.objects.filter(
                    payroll_settings=settings,
                    is_auto_generated=True
                ).delete()
                MonthlyEarnedLeaves.generate_for_payroll_settings(settings)

        branch_specific = request.POST.get("branch_specific_holidays")
        if branch_specific is not None:
            settings.branch_specific_holidays = branch_specific == "true"

        settings.save()
        MonthlyEarnedLeaves.sync_with_payroll_settings(settings)

        return JsonResponse({'success': True, 'message': 'Settings saved successfully!'})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

        
@login_required
@require_http_methods(["POST"])
def save_leave_settings(request):
    company = get_user_company(request)
    if company is None:
        return JsonResponse({'success': False, 'error': 'No company linked to your account.'}, status=400)

    try:
        settings, _ = LeaveSettings.objects.get_or_create(company=company)

        settings.carry_forward = request.POST.get("carry_forward") == "on"
        reset_month = request.POST.get("reset_month")
        settings.reset_month = int(reset_month) if reset_month else None

        settings.save()

        return JsonResponse({"success": True, "message": "Leave settings saved successfully!"})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)



def advance_list(request):
    advances = AdvanceMaster.objects.all()

    for adv in advances:
        try:
            paid = adv.advance_amount - adv.outstanding_amount
            adv.progress = (paid / adv.advance_amount) * 100
        except:
            adv.progress = 0

    return render(request, 'advances/advance_list.html', {
        'advances': advances
    })


def advance_create(request):
    """Admin/HR creates an advance."""
    # if not request.user.is_staff:
    #     return HttpResponseBadRequest("Not allowed")

    if request.method == 'POST':
        form = AdvanceCreateForm(request.POST)
        if form.is_valid():
            # Use service create_advance so schedules auto-created
            data = form.cleaned_data
            employee = data['employee']
            amount = data['advance_amount']
            months = data['default_months']
            start_date = data.get('start_date') or None
            adv = create_advance(employee, amount, months, start_date=start_date)
            messages.success(request, f"Advance created for {employee} - ₹{amount}")
            return redirect('advances-list')
    else:
        form = AdvanceCreateForm(initial={'start_date': date.today().replace(day=1)})
    return render(request, 'advances/advance_create.html', {'form': form})



def advance_detail(request, pk):
    """Show schedule, payments, actions (pay/skip)."""
    adv = get_object_or_404(AdvanceMaster, pk=pk)
    # security: if non-staff, ensure this belongs to user
    # if not request.user.is_staff:
    #     try:
    #         if request.user.employee != adv.employee:
    #             return HttpResponseBadRequest("Not allowed")
    #     except:
    #         return HttpResponseBadRequest("Not allowed")

    schedules = adv.schedules.order_by('due_month')
    payments = adv.payments.order_by('-date')
    payment_form = PaymentForm()
    skip_form = SkipMonthForm()
    return render(request, 'advances/advance_detail.html', {
        'advance': adv,
        'schedules': schedules,
        'payments': payments,
        'payment_form': payment_form,
        'skip_form': skip_form
    })

@require_POST
@transaction.atomic
def pay_advance(request, pk):
    """AJAX / form POST to apply payment."""
    adv = get_object_or_404(AdvanceMaster, pk=pk)
    # authorization check
    # if not request.user.is_staff:
    #     try:
    #         if request.user.employee != adv.employee:
    #             return JsonResponse({'error': 'Not allowed'}, status=403)
    #     except:
    #         return JsonResponse({'error': 'Not allowed'}, status=403)

    form = PaymentForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'error': 'Invalid data', 'errors': form.errors}, status=400)
    amount = form.cleaned_data['amount']
    note = form.cleaned_data.get('note', '')

    # Use service to apply payment
    try:
        apply_payment(adv, amount, note=note)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    # return updated schedule + outstanding
    schedules = []
    for s in adv.schedules.order_by('due_month'):
        schedules.append({
            'due_month': s.due_month.strftime('%Y-%m'),
            'scheduled_amount': s.scheduled_amount,
            'paid_amount': s.paid_amount,
            'status': s.status
        })
    return JsonResponse({
        'success': True,
        'outstanding': adv.outstanding_amount,
        'schedules': schedules
    })

@require_POST
@transaction.atomic
def skip_advance_month(request, pk):
    """Mark a schedule month as skipped (AJAX). Expects due_month in POST (YYYY-MM-DD)."""
    adv = get_object_or_404(AdvanceMaster, pk=pk)
    # if not request.user.is_staff:
    #     try:
    #         if request.user.employee != adv.employee:
    #             return JsonResponse({'error': 'Not allowed'}, status=403)
    #     except:
    #         return JsonResponse({'error': 'Not allowed'}, status=403)

    form = SkipMonthForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'error': 'Invalid data', 'errors': form.errors}, status=400)

    due_month = form.cleaned_data['due_month']
    try:
        skip_month(adv, due_month)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    schedules = []
    for s in adv.schedules.order_by('due_month'):
        schedules.append({
            'due_month': s.due_month.strftime('%Y-%m'),
            'scheduled_amount': s.scheduled_amount,
            'paid_amount': s.paid_amount,
            'status': s.status
        })
    return JsonResponse({
        'success': True,
        'outstanding': adv.outstanding_amount,
        'schedules': schedules
    })


@require_POST
def revert_skip_view(request, pk):
    adv = get_object_or_404(AdvanceMaster, pk=pk)
    due_month = request.POST.get("due_month")

    try:
        due_month = date.fromisoformat(due_month)
        revert_skip(adv, due_month)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

    updated = [{
        "due_month": s.due_month.strftime("%Y-%m"),
        "scheduled_amount": s.scheduled_amount,
        "paid_amount": s.paid_amount,
        "status": s.status
    } for s in adv.schedules.order_by("due_month")]

    return JsonResponse({"success": True, "schedules": updated})




def payroll_run_list(request):
    runs = PayrollRun.objects.order_by("-month")
    return render(request, "payroll/run_list.html", {"runs": runs})

def payroll_run_create(request):
    companies = Company.objects.all()
    if request.method == "POST":
        company_id = request.POST.get("company")
        month = request.POST.get("month")  # expected "YYYY-MM"
        if not company_id or not month:
            return redirect("payroll-run-create")
        company = get_object_or_404(Company, id=company_id)
        year, m = map(int, month.split("-"))
        month_start = date(year, m, 1)
        next_month = month_start.replace(day=28) + timedelta(days=4)
        month_end = next_month - timedelta(days=next_month.day)
        run = create_payroll_run(company, month_start, month_end)
        return redirect("payroll-run-detail", run_id=run.id)
    return render(request, "payroll/run_create.html", {"companies": companies})

def payroll_run_detail(request, run_id):
    run = get_object_or_404(PayrollRun, id=run_id)
    records = run.records.select_related("employee").all()
    settings = PayrollSettings.objects.filter(company=run.company).first()
    return render(request, "payroll/run_detail.html", {"run": run, "records": records, "settings": settings})

@require_POST
def payroll_record_update(request, record_id):
    record = get_object_or_404(PayrollRecord, id=record_id)
    if record.payroll.status == PayrollRun.STATUS_FINALIZED:
        return JsonResponse({"success": False, "error": "Payroll finalized"}, status=400)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    # apply edits to record fields (present_days, leave_adjust, pf_employee, professional_tax, advance, tds, other_deductions)
    editable = ["present_days", "leave_adjust", "pf_employee", "professional_tax", "advance", "tds", "other_deductions", "esic_employee"]
    manual = {}
    for k in editable:
        if k in payload:
            try:
                val = Decimal(payload[k])
            except Exception:
                val = Decimal(0)
            setattr(record, k, val)
            manual[k] = float(val)

    # save then recalc authoritative
    record.save()
    recalc_and_save_record(record, manual_overrides=manual)

    return JsonResponse({
        "success": True,
        "record": {
            "id": record.id,
            "net_salary": float(record.net_salary),
            "total_deductions": float(record.total_deductions),
            "calculation_breakdown": record.calculation_breakdown
        }
    })

@require_POST
def payroll_run_finalize(request, run_id):
    run = get_object_or_404(PayrollRun, id=run_id)
    # recalc all and set finalized
    for rec in run.records.all():
        recalc_and_save_record(rec, manual_overrides=rec.manual_override or {})
    run.status = PayrollRun.STATUS_FINALIZED
    run.save()
    return JsonResponse({"success": True})




from openpyxl import Workbook
from django.http import HttpResponse
from .models import PayrollRun, PayrollRecord

def payroll_export_excel(request, run_id):
    run = PayrollRun.objects.get(id=run_id)
    records = PayrollRecord.objects.filter(payroll=run)   # ✅ FIXED FIELD NAME

    wb = Workbook()
    ws = wb.active
    ws.title = f"Payroll {run.month.strftime('%b %Y')}"

    headers = [
        "Employee Code", "Name", "Designation", "Branch",
        "Gross CTC", "Basic (PM)", "HRA (PM)", "Sp Allow (PM)", "Stat Bonus (PM)",
        "Allowance1", "Allowance2",
        "Total Days", "Present Days", "Leave Taken", "Leave Without Pay",  # LWP included
        "Basic Processed", "HRA Processed", "Sp Allow Processed", "Stat Bonus Processed",
        "Allowance1 Processed", "Allowance2 Processed", "Gross Processed",
        "PF (EE)", "Professional Tax", "Advance", "ESIC (EE)", "TDS", "Other Deductions",
        "Total Deductions", "Net Pay"
    ]

    ws.append(headers)

    for r in records:
        ws.append([
            r.employee_code, r.employee_name, r.designation, r.branch_name,
            float(r.gross_ctc), float(r.basic_pm), float(r.hra_pm), float(r.sp_allowance_pm), float(r.stat_bonus_pm),
            float(r.allowance1_pm), float(r.allowance2_pm),
            r.total_days, float(r.present_days), float(r.leave_taken), float(r.leave_without_pay),
            float(r.basic_processed), float(r.hra_processed), float(r.sp_allowance_processed), float(r.stat_bonus_processed),
            float(r.allowance1_processed), float(r.allowance2_processed), float(r.gross_processed),
            float(r.pf_employee), float(r.professional_tax), float(r.advance), float(r.esic_employee), float(r.tds), float(r.other_deductions),
            float(r.total_deductions), float(r.net_salary)
        ])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    filename = f"Payroll_{run.month.strftime('%b_%Y')}.xlsx"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    wb.save(response)
    return response




from django.template.loader import get_template
from xhtml2pdf import pisa
from django.http import HttpResponse
from io import BytesIO

def payroll_export_pdf(request, run_id):
    run = PayrollRun.objects.get(id=run_id)
    records = PayrollRecord.objects.filter(payroll=run)   # ✅ FIXED FIELD NAME

    template = get_template("payroll/payroll_pdf_template.html")
    html = template.render({"run": run, "records": records})

    pdf_file = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=pdf_file)

    if pisa_status.err:
        return HttpResponse("PDF generation failed", status=500)

    response = HttpResponse(pdf_file.getvalue(), content_type="application/pdf")
    response['Content-Disposition'] = f'attachment; filename="Payroll_{run.month.strftime("%b_%Y")}.pdf"'

    return response



def download_empty_excel(request):
    # Create a new Excel workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "attendance_file"

    # (Optional) Add headers only
    headers = [
        "Employee Code",
        "Date",
        "In Time",
        "Out Time",
    ]

    ws.append(headers)  # comment this line if you want 100% empty

    # Prepare HTTP response
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="attendance_file.xlsx"'

    wb.save(response)
    return response





from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect
from django.contrib import messages

def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user)

            # ADMIN or HR → Admin Dashboard
            if user.groups.filter(name__in=["Admin", "HR","Manager"]).exists():
                return redirect("admin-dashboard")

            # EMPLOYEE → Employee Detail Page
            elif user.groups.filter(name="Employee").exists():
                employee = Employee.objects.get(user=user)
                return redirect("employee_detail", pk=employee.id)

            # MANAGER (optional)
            # elif user.groups.filter(name="Manager").exists():
            #     employee = Employee.objects.get(user=user)
            #     return redirect("employee_detail", pk=employee.id)

            # fallback
            return redirect("login")

        else:
            messages.error(request, "Invalid username or password")

    return render(request, "auth/login.html")


from django.contrib.auth import logout

def logout_view(request):
    logout(request)
    return redirect("login")



from django.contrib.auth.models import User, Group

@login_required
def create_user_view(request):
    if request.method == "POST":
        employee_id = request.POST.get("employee_id")
        role = request.POST.get("role")

        employee = Employee.objects.get(id=employee_id)

        if employee.user:
            messages.error(request, "User already exists for this employee.")
            return redirect("create-user")

        user = User.objects.create_user(
            username=employee.employee_code,
            email=employee.personal_email,
            password="Temp@123"
        )

        group = Group.objects.get(name=role)
        user.groups.add(group)

        employee.user = user
        employee.force_password_change = True   # 🔥 REQUIRED
        employee.save()

        messages.success(
            request,
            f"User created. Username: {user.username}, Password: Temp@123"
        )

        return redirect("create-user")

    employees = Employee.objects.filter(user__isnull=True)
    return render(request, "auth/create_user.html", {"employees": employees})



# views.py
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.contrib import messages

@login_required
def change_password(request):
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)

        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)

            employee = request.user.employee_profile
            employee.force_password_change = False
            employee.save()

            messages.success(request, "✅ Password updated successfully.")
            return redirect("admin-dashboard")

        else:
            # 🔴 IMPORTANT: show WHY it failed
            messages.error(request, "❌ Password update failed. Please fix the errors below.")
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")

    else:
        form = PasswordChangeForm(request.user)

    return render(request, "auth/change_password.html", {"form": form})



# holiday calendar views


# website/views.py - COMPLETE HOLIDAY CALENDAR VIEWS

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from datetime import timedelta, date
import json

from .models import Holiday, HolidayType, MonthlyEarnedLeaves, PayrollSettings, Branch, Company
from .forms import HolidayForm, MonthlyEarnedLeavesForm

# ============================================================================
# HOLIDAY CALENDAR DASHBOARD VIEW
# ============================================================================

@login_required
@require_http_methods(["GET"])
def holiday_calendar_dashboard(request):
    """
    Main Holiday Calendar Dashboard View
    """

    # ----------------------------------------------------
    # 1️⃣ Year & Month handling
    # ----------------------------------------------------
    year = int(request.GET.get('year', timezone.now().year))
    month = int(request.GET.get('month', timezone.now().month))

    if not 1 <= month <= 12:
        month = timezone.now().month

    month_name = calendar.month_name[month]

    # ----------------------------------------------------
    # 2️⃣ Payroll Settings (company-wide)
    # ----------------------------------------------------
    payroll_settings = PayrollSettings.objects.first()

    # ----------------------------------------------------
    # 3️⃣ Auto-create Monthly Earned Leaves (CRITICAL FIX)
    # ----------------------------------------------------
    monthly_leaves = []

# In holiday_calendar_dashboard view, replace the monthly_leaves section:

    if payroll_settings:
        annual_leaves = payroll_settings.earned_leaves_per_year or 24
        monthly_default = (
            Decimal(str(annual_leaves)) / Decimal('12')
        ).quantize(Decimal('0.01'))
        
        fy_start = payroll_settings.financial_year_start_month or 4  # April default
        
        # Determine FY year range based on selected year
        # If FY starts April 2025 → months Apr2025 to Mar2026
        # Current year shown in dashboard determines which FY
        if month >= fy_start:
            fy_start_year = year
        else:
            fy_start_year = year - 1
        
        monthly_leaves = []
        for i in range(12):
            m = fy_start + i
            y = fy_start_year
            if m > 12:
                m -= 12
                y += 1
            
            leave, _ = MonthlyEarnedLeaves.objects.get_or_create(
                payroll_settings=payroll_settings,
                month=m,
                year=y,
                defaults={
                    'earned_leaves': monthly_default,
                    'is_auto_generated': True,
                }
            )
            monthly_leaves.append(leave)
        
        # Sort by year then month
        monthly_leaves = sorted(monthly_leaves, key=lambda x: (x.year, x.month))
    # ----------------------------------------------------
    # 4️⃣ Holidays for calendar (month-based)
    # ----------------------------------------------------
    all_holidays_month = Holiday.objects.filter(
        holiday_date__year=year,
        holiday_date__month=month
    ).order_by('holiday_date')

    # ----------------------------------------------------
    # 5️⃣ Holidays JSON for calendar UI
    # ----------------------------------------------------
    holidays_json = json.dumps([
        {
            'id': h.id,
            'holiday_date': h.holiday_date.isoformat(),
            'name': h.name,
            'status': h.status,
            'is_national': h.is_national,
        }
        for h in Holiday.objects.all()
    ])

    # ----------------------------------------------------
    # 6️⃣ Upcoming Holidays (next 7 days)
    # ----------------------------------------------------
    today = date.today()
    upcoming_holidays = Holiday.objects.filter(
        holiday_date__gte=today,
        holiday_date__lte=today + timedelta(days=7)
    ).order_by('holiday_date')[:10]

    # ----------------------------------------------------
    # 7️⃣ Statistics (year-based)
    # ----------------------------------------------------
    all_holidays_year = Holiday.objects.filter(holiday_date__year=year)

    total_holidays = all_holidays_year.count()
    national_holidays = all_holidays_year.filter(is_national=True).count()
    regional_holidays = all_holidays_year.filter(is_national=False).count()
    emergency_closures = all_holidays_year.filter(status='emergency').count()

    # ----------------------------------------------------
    # 8️⃣ Holiday Types (dropdowns)
    # ----------------------------------------------------
    holiday_types = HolidayType.objects.all()
    branches = Branch.objects.all()

    all_half_day_scenarios = HalfDayScenario.objects.all().order_by('scenario_date')
    
    half_day_json = json.dumps([
        {
            'id': s.id,
            'scenario_date': s.scenario_date.isoformat(),
            'description': s.description,    # ✅ correct field name
            'scenario_type': s.scenario_type,
            'is_approved': s.is_approved,
            'branch': s.branch.branch_name if s.branch else 'All',
            'credit_count': str(s.credit_count),
        }
        for s in all_half_day_scenarios
    ])

    # ----------------------------------------------------
    # 9️⃣ FINAL CONTEXT (⚠️ NOTHING REMOVED)
    # ----------------------------------------------------
    context = {
        'year': year,
        'month': month,
        'month_name': month_name,

        # Holidays
        'all_holidays': Holiday.objects.all().order_by('holiday_date'),
        'upcoming_holidays': upcoming_holidays,
        'holidays_json': holidays_json,

        # Stats
        'total_holidays': total_holidays,
        'national_holidays': national_holidays,
        'regional_holidays': regional_holidays,
        'emergency_closures': emergency_closures,

        # Earned Leaves
        'monthly_leaves': monthly_leaves,
        'payroll_settings': payroll_settings,

        # Dropdowns
        'holiday_types': holiday_types,

        'branches': branches,
        'all_half_day_scenarios': all_half_day_scenarios,
        'half_day_json': half_day_json,
        'total_half_days': all_half_day_scenarios.filter(
            scenario_date__year=year, is_approved=True
        ).count(),

    }

    return render(request, 'holiday_calendar/dashboard.html', context)







@login_required
@require_http_methods(["POST"])
def save_holiday_settings(request):
    try:
        company = Company.objects.first()
        settings, _ = PayrollSettings.objects.get_or_create(company=company)
        
        financial_year_start = request.POST.get('financial_year_start_month')
        branch_specific_holidays = request.POST.get('branch_specific_holidays') == 'true'
        
        if financial_year_start:
            fy_month = int(financial_year_start)
            if 1 <= fy_month <= 12:
                old_fy = settings.financial_year_start_month
                settings.financial_year_start_month = fy_month
                
                # If FY start month changed, regenerate earned leaves
                if old_fy != fy_month:
                    # Delete old auto-generated leaves for future years
                    MonthlyEarnedLeaves.objects.filter(
                        payroll_settings=settings,
                        is_auto_generated=True
                    ).delete()
                    # Regenerate for current FY
                    MonthlyEarnedLeaves.generate_for_payroll_settings(settings)
                    messages.success(
                        request,
                        f'✓ Financial year updated to start from month {fy_month}. '
                        f'Earned leaves regenerated.'
                    )
        
        settings.branch_specific_holidays = branch_specific_holidays
        settings.save()
        
        messages.success(request, '✓ Holiday settings saved successfully!')
        
    except Exception as e:
        messages.error(request, f'❌ Error saving settings: {str(e)}')
    
    return redirect('holiday-calendar')


# ============================================================================
# ADD HOLIDAY VIEW
# ============================================================================

@login_required
@require_http_methods(["GET", "POST"])
def add_holiday(request):
    """
    Add New Holiday View
    
    GET: Shows form (but in modal, so redirects)
    POST: Creates new Holiday object
    
    Form Fields:
    - holiday_date (DateField): Date of holiday
    - name (CharField): Name of holiday
    - holiday_type (ForeignKey): Type of holiday
    - status (CharField): Status (declared/optional/emergency)
    - is_national (BooleanField): Apply to all branches?
    - description (TextField): Optional description
    
    Redirects back to dashboard with success/error message
    """
    
    if request.method == 'POST':
        # Instantiate form with POST data
        form = HolidayForm(request.POST)
        
        if form.is_valid():
            # Save the holiday
            holiday = form.save(commit=False)
            holiday.created_by = request.user

            employee = request.user.employee_profile

            # Map calendar automatically
            holiday.holiday_calendar = HolidayCalendar.objects.get(
                branch=employee.branch,
                year=holiday.holiday_date.year  # ← add this
            )
            # Auto-national logic
            if holiday.holiday_type.type_category == "national":
                holiday.is_national = True

            holiday.save()
            
            # Show success message
            messages.success(
                request,
                f'✓ Holiday "{holiday.name}" ({holiday.holiday_date.strftime("%b %d, %Y")}) '
                f'added successfully!'
            )
            
            return redirect('holiday-calendar')
        else:
            # Form has errors - show them
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field.title()}: {error}')
            
            return redirect('holiday-calendar')
    
    # GET request - show form (in modal, so just redirect)
    return redirect('holiday-calendar')

# ============================================================================
# EDIT HOLIDAY VIEW
# ============================================================================

@login_required
@require_http_methods(["GET", "POST"])
def edit_holiday(request, holiday_id):
    """
    Edit Existing Holiday View
    
    GET: Loads holiday data via AJAX (see api_get_holiday)
    POST: Updates existing Holiday object
    
    Parameters:
    - holiday_id: ID of holiday to edit
    
    Redirects back to dashboard with success/error message
    """
    
    # Get the holiday or 404
    holiday = get_object_or_404(Holiday, id=holiday_id)
    
    if request.method == 'POST':
        # Instantiate form with existing instance
        form = HolidayForm(request.POST, instance=holiday)
        
        if form.is_valid():
            # Save updates
            form.save()
            
            # Show success message
            messages.success(
                request,
                f'✓ Holiday "{holiday.name}" updated successfully!'
            )
            
            return redirect('holiday-calendar')
        else:
            # Form has errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field.title()}: {error}')
    
    return redirect('holiday-calendar')


# ============================================================================
# DELETE HOLIDAY VIEW
# ============================================================================

@login_required
@require_http_methods(["POST"])
def delete_holiday(request, holiday_id):
    """
    Delete Holiday View
    
    POST only (with confirmation from frontend)
    
    Parameters:
    - holiday_id: ID of holiday to delete
    
    Deletes the holiday and redirects with message
    """
    
    # Get the holiday
    holiday = get_object_or_404(Holiday, id=holiday_id)
    holiday_name = holiday.name
    holiday_date = holiday.holiday_date.strftime("%b %d, %Y")
    
    # Delete it
    holiday.delete()
    
    # Show success message
    messages.success(
        request,
        f'✓ Holiday "{holiday_name}" ({holiday_date}) deleted successfully!'
    )
    
    return redirect('holiday-calendar')


# ============================================================================
# HOLIDAY LIST VIEW
# ============================================================================

@login_required
@require_http_methods(["GET"])
def holiday_list(request):
    """
    Holiday List View (List Tab)
    
    Shows all holidays in table format
    Can filter by type, status, branch
    
    Query Parameters:
    - type: Filter by holiday type
    - status: Filter by status
    - branch: Filter by branch
    
    Returns: Redirects to dashboard (list is shown in tab)
    """
    
    return redirect('holiday-calendar')


# ============================================================================
# EARNED LEAVES CONFIGURATION VIEW
# ============================================================================

@login_required
@require_http_methods(["GET"])
def earned_leaves_config(request):
    """
    Display Monthly Earned Leaves for a selected financial year.
    Auto-generation is handled via signals.
    """

    try:
        year = int(request.GET.get('year', timezone.now().year))

        payroll_settings = PayrollSettings.objects.first()
        if not payroll_settings:
            messages.error(request, "❌ Payroll Settings not configured!")
            return render(request, 'holiday_calendar/dashboard.html', {
                'monthly_leaves': [],
                'year': year,
                'error': 'No payroll settings'
            })

        # ✅ JUST FETCH – do NOT create here
        monthly_leaves = MonthlyEarnedLeaves.objects.filter(
            payroll_settings=payroll_settings,
            year=year
        ).order_by('month')

        # Safety check (optional but good)
        if not monthly_leaves.exists():
            messages.warning(
                request,
                "⚠️ Earned leaves not found for this year. Please check Payroll Settings."
            )

        # Statistics
        total_earned_leaves = sum(
            float(leave.earned_leaves) for leave in monthly_leaves
        )
        auto_count = monthly_leaves.filter(is_auto_generated=True).count()
        manual_count = monthly_leaves.count() - auto_count

        context = {
            'monthly_leaves': monthly_leaves,
            'year': year,
            'payroll_settings': payroll_settings,
            'total_earned_leaves': round(total_earned_leaves, 2),
            'auto_generated_count': auto_count,
            'manual_count': manual_count,
        }

        return render(request, 'holiday_calendar/dashboard.html', context)

    except Exception as e:
        messages.error(request, f"❌ Error loading earned leaves: {str(e)}")
        return render(request, 'holiday_calendar/dashboard.html', {
            'monthly_leaves': [],
            'year': timezone.now().year,
        })


@login_required
@require_http_methods(["POST"])
def edit_earned_leave(request, leave_id):
    """
    ✅ Edit Monthly Earned Leave Value
    
    Updates the earned_leaves field for a specific month.
    
    Example:
    POST /holiday/earned-leave/1/edit/
    Data: {
        'earned_leaves': '3.5',
        'is_auto_generated': 'on'
    }
    """
    
    try:
        # Get the leave record
        leave = MonthlyEarnedLeaves.objects.get(id=leave_id)
        
        # Get form data
        earned_leaves_value = request.POST.get('earned_leaves', '').strip()
        is_auto_generated = request.POST.get('is_auto_generated', 'off') == 'on'
        
        # Validate input
        if not earned_leaves_value:
            messages.error(request, '❌ Earned leaves value is required!')
            return redirect('holiday-calendar')
        
        # Try to convert to Decimal
        try:
            earned_leaves_decimal = Decimal(earned_leaves_value)
        except:
            messages.error(
                request,
                f'❌ Invalid value "{earned_leaves_value}". Use decimal numbers like 2.5 or 3.75'
            )
            return redirect('holiday-calendar')
        
        # Validate range (0-31 days)
        if earned_leaves_decimal < 0 or earned_leaves_decimal > 31:
            messages.error(request, '❌ Earned leaves must be between 0 and 31 days!')
            return redirect('holiday-calendar')
        
        # Update the record
        leave.earned_leaves = earned_leaves_decimal
        leave.is_auto_generated = is_auto_generated
        leave.save()
        
        # Get month name
        month_names = {
            1: 'January', 2: 'February', 3: 'March', 4: 'April',
            5: 'May', 6: 'June', 7: 'July', 8: 'August',
            9: 'September', 10: 'October', 11: 'November', 12: 'December'
        }
        month_name = month_names.get(leave.month, 'Month')
        status_text = "Manual" if not is_auto_generated else "Auto"
        
        messages.success(
            request,
            f'✓ {month_name} {leave.year}: Updated to {earned_leaves_decimal} days ({status_text})'
        )
    
    except MonthlyEarnedLeaves.DoesNotExist:
        messages.error(request, '❌ Earned leave record not found!')
    except ValueError as e:
        messages.error(request, f'❌ Invalid input: {str(e)}')
    except Exception as e:
        messages.error(request, f'❌ Error updating earned leaves: {str(e)}')
    
    return redirect('holiday-calendar')


@login_required
@require_http_methods(["GET"])
def api_earned_leaves(request):
    """
    ✅ API Endpoint - Get Earned Leaves as JSON
    
    Used by JavaScript to fetch earned leaves data.
    
    Example:
    GET /api/earned-leaves/?year=2025
    
    Response:
    [
        {
            'id': 1,
            'month': 1,
            'month_name': 'January',
            'year': 2025,
            'earned_leaves': '3.50',
            'is_auto_generated': False
        },
        ...
    ]
    """
    
    try:
        year = request.GET.get('year', timezone.now().year)
        payroll_settings = PayrollSettings.objects.first()
        
        if not payroll_settings:
            return JsonResponse({'error': 'No payroll settings'}, status=400)
        
        leaves = MonthlyEarnedLeaves.objects.filter(
            payroll_settings=payroll_settings,
            year=year
        ).order_by('month')
        
        month_names = {
            1: 'January', 2: 'February', 3: 'March', 4: 'April',
            5: 'May', 6: 'June', 7: 'July', 8: 'August',
            9: 'September', 10: 'October', 11: 'November', 12: 'December'
        }
        
        data = [
            {
                'id': leave.id,
                'month': leave.month,
                'month_name': month_names.get(leave.month, 'Unknown'),
                'year': leave.year,
                'earned_leaves': str(leave.earned_leaves),
                'is_auto_generated': leave.is_auto_generated,
            }
            for leave in leaves
        ]
        
        return JsonResponse(data, safe=False)
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET", "POST"])
def add_half_day_scenario(request):
    if request.method == 'POST':
        scenario_date = request.POST.get('scenario_date')
        description = request.POST.get('description', '')
        scenario_type = request.POST.get('scenario_type', 'other')
        is_approved = request.POST.get('is_approved') == 'on'
        branch_id = request.POST.get('branch')
        credit_count = request.POST.get('credit_count', '0.50')

        if not scenario_date or not description or not branch_id:
            messages.error(request, '❌ Date, description and branch are required.')
            return redirect('holiday-calendar')

        try:
            from datetime import date as date_cls
            parsed_date = date_cls.fromisoformat(scenario_date)
            branch = get_object_or_404(Branch, id=branch_id)

            # Prevent duplicate for same branch + date
            if HalfDayScenario.objects.filter(
                scenario_date=parsed_date, branch=branch
            ).exists():
                messages.error(
                    request,
                    f'❌ A half-day scenario already exists for '
                    f'{branch.branch_name} on {parsed_date}.'
                )
                return redirect('holiday-calendar')

            HalfDayScenario.objects.create(
                scenario_date=parsed_date,
                description=description,
                scenario_type=scenario_type,
                is_approved=is_approved,
                branch=branch,
                credit_count=Decimal(credit_count),
                created_by=request.user,
            )

            messages.success(
                request,
                f'✓ Half-day scenario added for '
                f'{branch.branch_name} on {parsed_date.strftime("%b %d, %Y")}!'
            )
        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')

    return redirect('holiday-calendar')


@login_required
@require_http_methods(["POST"])
def edit_half_day_scenario(request, scenario_id):
    scenario = get_object_or_404(HalfDayScenario, id=scenario_id)

    try:
        from datetime import date as date_cls
        scenario_date = request.POST.get('scenario_date')
        description = request.POST.get('description', '')
        scenario_type = request.POST.get('scenario_type', 'other')
        is_approved = request.POST.get('is_approved') == 'on'
        branch_id = request.POST.get('branch')
        credit_count = request.POST.get('credit_count', '0.50')

        if not branch_id:
            messages.error(request, '❌ Branch is required.')
            return redirect('holiday-calendar')

        scenario.scenario_date = date_cls.fromisoformat(scenario_date)
        scenario.description = description
        scenario.scenario_type = scenario_type
        scenario.is_approved = is_approved
        scenario.branch = get_object_or_404(Branch, id=branch_id)
        scenario.credit_count = Decimal(credit_count)

        # Set approved_by if being approved
        if is_approved and not scenario.approved_by:
            scenario.approved_by = request.user

        scenario.save()
        messages.success(request, '✓ Half-day scenario updated!')
    except Exception as e:
        messages.error(request, f'❌ Error: {str(e)}')

    return redirect('holiday-calendar')


@login_required
@require_http_methods(["POST"])
def delete_half_day_scenario(request, scenario_id):
    scenario = get_object_or_404(HalfDayScenario, id=scenario_id)
    branch_name = scenario.branch.branch_name
    date_str = scenario.scenario_date.strftime("%b %d, %Y")
    scenario.delete()
    messages.success(request, f'✓ Half-day scenario for {branch_name} on {date_str} deleted!')
    return redirect('holiday-calendar')


@login_required
@require_http_methods(["GET"])
def api_get_half_day_scenario(request, scenario_id):
    try:
        s = HalfDayScenario.objects.get(id=scenario_id)
        return JsonResponse({
            'id': s.id,
            'scenario_date': s.scenario_date.isoformat(),
            'description': s.description,
            'scenario_type': s.scenario_type,
            'is_approved': s.is_approved,
            'branch': s.branch.id if s.branch else None,
            'credit_count': str(s.credit_count),
        })
    except HalfDayScenario.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
# ============================================================================
# API ENDPOINTS - JSON RESPONSES FOR AJAX
# ============================================================================

@login_required
@require_http_methods(["GET"])
def api_get_holiday(request, holiday_id):
    """
    API: Get Single Holiday Data
    
    Used by AJAX to populate edit modal
    
    Returns: JSON object with holiday data
    
    Example Response:
    {
        'id': 1,
        'holiday_date': '2025-01-26',
        'name': 'Republic Day',
        'holiday_type': 1,
        'status': 'declared',
        'description': 'National holiday',
        'is_national': true
    }
    """
    
    try:
        # Get the holiday
        holiday = Holiday.objects.get(id=holiday_id)
        
        # Build response data
        data = {
            'id': holiday.id,
            'holiday_date': holiday.holiday_date.isoformat(),
            'name': holiday.name,
            'holiday_type': holiday.holiday_type.id,
            'status': holiday.status,
            'description': holiday.description or '',
            'is_national': holiday.is_national,
        }
        
        return JsonResponse(data)
    
    except Holiday.DoesNotExist:
        # Holiday not found
        return JsonResponse({'error': 'Holiday not found'}, status=404)
    except Exception as e:
        # Other error
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def api_holidays_json(request):
    """
    API: Get All Holidays
    
    Returns JSON array of all holidays
    Used to populate holiday list table
    
    Query Parameters:
    - type: Filter by holiday type
    - status: Filter by status
    - year: Filter by year
    
    Example Response:
    [
        {
            'id': 1,
            'holiday_date': '2025-01-26',
            'name': 'Republic Day',
            'holiday_type': 'National',
            'status': 'declared',
            'is_national': true
        },
        ...
    ]
    """
    
    # Start with all holidays
    holidays = Holiday.objects.all().order_by('holiday_date')
    
    # Apply filters if provided
    holiday_type = request.GET.get('type')
    if holiday_type:
        holidays = holidays.filter(holiday_type__type_category=holiday_type)
    
    status = request.GET.get('status')
    if status:
        holidays = holidays.filter(status=status)
    
    year = request.GET.get('year')
    if year:
        holidays = holidays.filter(holiday_date__year=year)
    
    # Build response data
    data = [
        {
            'id': h.id,
            'holiday_date': h.holiday_date.isoformat(),
            'name': h.name,
            'holiday_type': h.holiday_type.name,
            'status': h.status,
            'is_national': h.is_national,
        }
        for h in holidays
    ]
    
    return JsonResponse(data, safe=False)


@login_required
@require_http_methods(["GET"])
def api_earned_leaves_json(request):
    """
    API: Get Earned Leaves Data
    
    Returns monthly earned leaves for calendar calculations
    
    Query Parameters:
    - year: Filter by year (default: current year)
    
    Example Response:
    [
        {
            'id': 1,
            'month': 1,
            'year': 2025,
            'earned_leaves': '2.0',
            'is_auto_generated': true
        },
        ...
    ]
    """
    
    # Get year from query params or use current
    year = request.GET.get('year', timezone.now().year)
    
    # Get earned leaves
    leaves = MonthlyEarnedLeaves.objects.filter(year=year).order_by('month')
    
    # Build response data
    data = [
        {
            'id': l.id,
            'month': l.month,
            'year': l.year,
            'earned_leaves': str(l.earned_leaves),
            'is_auto_generated': l.is_auto_generated,
        }
        for l in leaves
    ]
    
    return JsonResponse(data, safe=False)


# ============================================================================
# UTILITY VIEWS (Optional but helpful)
# ============================================================================

@login_required
@require_http_methods(["GET"])
def api_holiday_types(request):
    """
    API: Get Holiday Types
    
    Returns all available holiday types
    Used to populate type filter and form dropdowns
    """
    
    types = HolidayType.objects.all()
    
    data = [
        {
            'id': t.id,
            'name': t.name,
            'type_category': t.type_category,
        }
        for t in types
    ]
    
    return JsonResponse(data, safe=False)


@login_required
@require_http_methods(["GET"])
def api_payroll_settings(request):
    """
    API: Get Payroll Settings
    
    Returns company-wide holiday and leave settings
    """
    
    try:
        settings = PayrollSettings.objects.first()
        
        if not settings:
            return JsonResponse({'error': 'Settings not configured'}, status=404)
        
        data = {
            'id': settings.id,
            'earned_leaves_per_year': str(settings.earned_leaves_per_year),
            'financial_year_start_month': settings.financial_year_start_month,
        }
        
        return JsonResponse(data)
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ============================================================================
# HELPER FUNCTIONS (Not views, but useful)
# ============================================================================

def get_holidays_for_month(year, month):
    """
    Helper: Get all holidays for a specific month
    
    Parameters:
    - year: Year
    - month: Month (1-12)
    
    Returns: QuerySet of Holiday objects
    """
    
    return Holiday.objects.filter(
        holiday_date__year=year,
        holiday_date__month=month
    ).order_by('holiday_date')


def get_upcoming_holidays(days=7):
    """
    Helper: Get upcoming holidays
    
    Parameters:
    - days: Number of days to look ahead (default: 7)
    
    Returns: QuerySet of Holiday objects
    """
    
    today = date.today()
    end_date = today + timedelta(days=days)
    
    return Holiday.objects.filter(
        holiday_date__gte=today,
        holiday_date__lte=end_date
    ).order_by('holiday_date')


def calculate_working_days(start_date, end_date):
    """
    Helper: Calculate working days (excluding holidays and weekends)
    
    Parameters:
    - start_date: Start date
    - end_date: End date
    
    Returns: Number of working days
    """
    
    working_days = 0
    current = start_date
    
    # Get all holidays in date range
    holidays = Holiday.objects.filter(
        holiday_date__gte=start_date,
        holiday_date__lte=end_date
    )
    holiday_dates = set(h.holiday_date for h in holidays)
    
    # Count working days
    while current <= end_date:
        # Skip weekends (Saturday=5, Sunday=6)
        if current.weekday() < 5:
            # Skip holidays
            if current not in holiday_dates:
                working_days += 1
        
        current += timedelta(days=1)
    
    return working_days