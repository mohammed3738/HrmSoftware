"""
Unit tests for Leave Balance calculation
Run with: python manage.py test website.tests.leave_balance_test.LeaveBalanceTestCase
"""
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User
from datetime import date, timedelta, time
from website.models import (
    Company, Employee, Attendance, CompOffRequest,
    PayrollSettings, LeaveCreditPolicy, LeaveBalance
)
from website.services.leave_balance_service import calculate_leave_balance


class LeaveBalanceTestCase(TestCase):
    
    def setUp(self):
        """Set up test data"""
        # Create company
        self.company = Company.objects.create(
            name="Test Company"
        )
        
        # Create payroll settings
        self.payroll = PayrollSettings.objects.create(
            company=self.company,
            is_auto=True,
            max_leave_balance=30,
            earned_leaves_per_year=24,
            grace_period_minutes=15,
            carry_forward=True
        )
        
        # Create leave credit policy
        self.policy = LeaveCreditPolicy.objects.create(
            company=self.company,
            credit_1_limit=15,
            credit_2_limit=25,
            credit_low=Decimal("0.00"),
            credit_mid=Decimal("1.00"),
            credit_high=Decimal("2.00")
        )
        
        # Create employee with 8-hour shift (9am-5pm) for easier testing
        self.employee = Employee.objects.create(
            company=self.company,
            salutation="Mr",
            first_name="John",
            last_name="Doe",
            father_name="Robert Doe",
            gender="Male",
            blood_group="O+",
            date_of_birth=date(1990, 1, 1),
            place_of_birth="Test City",
            personal_email="john@test.com",
            present_address="123 Test St",
            permanent_address="123 Test St",
            personal_mobile="1234567890",
            employee_code="EMP001",
            designation="Developer",
            department="IT",
            date_of_joining=date(2020, 1, 1),
            location="Test Location",
            pan_no="ABCDE1234F",
            aadhar_no="123456789012",
            name_as_per_bank="John Doe",
            salary_account_number="1234567890",
            ifsc_code="TEST0001234",
            emergency_contact_name1="Jane Doe",
            emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="0987654321",
            status="Active",
            shift_start_time=time(9, 0, 0),
            shift_end_time=time(17, 0, 0)  # 8-hour shift: 9am-5pm
        )
    
    def test_full_month_present(self):
        """Test employee present all 30 days"""
        # Create 30 days of attendance - all present
        today = date.today()
        start = today.replace(day=1)
        
        for i in range(30):
            Attendance.objects.create(
                employee=self.employee,
                date=start + timedelta(days=i),
                in_time=time(9, 0, 0),
                out_time=time(17, 0, 0),  # 8-hour shift
                status="Present",
                late=0
            )
        
        # Calculate
        final_balance = calculate_leave_balance(self.employee, self.payroll)
        
        # Assertions
        balance = LeaveBalance.objects.filter(employee=self.employee).latest('id')
        
        self.assertEqual(balance.total_number_of_days, 30)
        self.assertEqual(balance.number_of_days_present, Decimal("30.00"))
        self.assertEqual(balance.leave_taken, Decimal("0.00"))
        self.assertEqual(balance.leave_without_pay, Decimal("0.00"))
        # 30 days > 25 (credit_2_limit), so credit_high = 2
        self.assertEqual(final_balance, Decimal("2.00"))
    
    def test_with_half_days(self):
        """Test employee with some half days"""
        today = date.today()
        start = today.replace(day=1)
        
        # 20 full days (9am-5pm = 8 hours, full shift)
        for i in range(20):
            Attendance.objects.create(
                employee=self.employee,
                date=start + timedelta(days=i),
                in_time=time(9, 0, 0),
                out_time=time(17, 0, 0),  # 8 hours - full day
                status="Present"
            )
        
        # 10 half days (9am-1pm = 4 hours = 50% of 8-hour shift)
        for i in range(20, 30):
            Attendance.objects.create(
                employee=self.employee,
                date=start + timedelta(days=i),
                in_time=time(9, 0, 0),
                out_time=time(13, 0, 0),  # 4 hours = 50% of 8-hour shift
                status="Half Day"
            )
        
        final_balance = calculate_leave_balance(self.employee, self.payroll)
        balance = LeaveBalance.objects.filter(employee=self.employee).latest('id')
        
        # Paid days = 20 + (10 * 0.5) = 25
        self.assertEqual(balance.number_of_days_present, Decimal("25.00"))
        # Leave taken = 30 - 25 = 5
        self.assertEqual(balance.leave_taken, Decimal("5.00"))
        # 25 days = credit_2_limit, so credit_mid = 1
        # Balance = 0 + 0 - 5 - 0 = -5, but floored to 0
        # LWP = 5
        self.assertEqual(balance.leave_without_pay, Decimal("5.00"))
        self.assertEqual(balance.leave_balance, Decimal("0.00"))
        # Final = 0 + 1 (credit) = 1
        self.assertEqual(final_balance, Decimal("1.00"))
    
    def test_with_compoff(self):
        """Test employee with approved comp-off"""
        today = date.today()
        start = today.replace(day=1)
        
        # 28 days present
        for i in range(28):
            Attendance.objects.create(
                employee=self.employee,
                date=start + timedelta(days=i),
                in_time=time(9, 0, 0),
                out_time=time(17, 0, 0),  # 8-hour shift
                status="Present"
            )
        
        # 2 days absent (no in_time/out_time = Absent)
        for i in range(28, 30):
            Attendance.objects.create(
                employee=self.employee,
                date=start + timedelta(days=i),
                status="Absent"
            )
        
        # Add 2 days comp-off
        CompOffRequest.objects.create(
            employee=self.employee,
            from_date=start,
            to_date=start + timedelta(days=1),
            count=Decimal("2.00"),
            status="Approved"
        )
        
        final_balance = calculate_leave_balance(self.employee, self.payroll)
        balance = LeaveBalance.objects.filter(employee=self.employee).latest('id')
        
        # Paid days = 28
        self.assertEqual(balance.number_of_days_present, Decimal("28.00"))
        # Leave taken = 30 - 28 = 2
        self.assertEqual(balance.leave_taken, Decimal("2.00"))
        # Compoff = 2
        self.assertEqual(balance.compoff, Decimal("2.00"))
        # Balance = 0 + 2 - 2 = 0
        self.assertEqual(balance.leave_balance, Decimal("0.00"))
        # 28 days > 25, so credit = 2
        # Final = 0 + 2 = 2
        self.assertEqual(final_balance, Decimal("2.00"))
    
    def test_with_late_minutes(self):
        """Test late minutes conversion to days"""
        today = date.today()
        start = today.replace(day=1)
        
        # 30 days present, but with late check-in times
        # Shift is 9am-5pm (8 hours), come in at 1pm (4 hours late)
        # Work from 1pm-10pm (9 hours) to count as full day
        for i in range(30):
            Attendance.objects.create(
                employee=self.employee,
                date=start + timedelta(days=i),
                in_time=time(13, 0, 0),   # Check in at 1pm (4 hours late)
                out_time=time(22, 0, 0),  # Check out at 10pm (9 hours worked)
                status="Late Present"
            )
        
        final_balance = calculate_leave_balance(self.employee, self.payroll)
        balance = LeaveBalance.objects.filter(employee=self.employee).latest('id')
        
        # Total late = 30 * 240 = 7200 minutes
        self.assertEqual(balance.late, 7200)
        # Late days = 7200 / 480 = 15
        # Balance = 0 + 0 - 0 - 15 = -15, floored to 0
        # LWP = 15
        self.assertEqual(balance.leave_without_pay, Decimal("15.00"))
        self.assertEqual(balance.leave_balance, Decimal("0.00"))
    
    def test_carry_forward(self):
        """Test opening balance from previous month"""
        # Create previous month record
        LeaveBalance.objects.create(
            employee=self.employee,
            opening_balance=Decimal("10.00"),
            final_leave_balance=Decimal("15.00")
        )
        
        today = date.today()
        start = today.replace(day=1)
        
        # 30 days present
        for i in range(30):
            Attendance.objects.create(
                employee=self.employee,
                date=start + timedelta(days=i),
                in_time=time(9, 0, 0),
                out_time=time(17, 0, 0),  # 8-hour shift
                status="Present"
            )
        
        final_balance = calculate_leave_balance(self.employee, self.payroll)
        balance = LeaveBalance.objects.filter(employee=self.employee).latest('id')
        
        # Opening should be previous final_leave_balance
        self.assertEqual(balance.opening_balance, Decimal("15.00"))
        # Balance = 15 + 0 - 0 - 0 = 15
        # Credit = 2 (30 days > 25)
        # Final = min(15 + 2, 30) = 17
        self.assertEqual(final_balance, Decimal("17.00"))
    
    def test_max_balance_cap(self):
        """Test maximum leave balance cap"""
        # Create previous record with high balance
        LeaveBalance.objects.create(
            employee=self.employee,
            final_leave_balance=Decimal("28.00")
        )
        
        today = date.today()
        start = today.replace(day=1)
        
        # 30 days present (would add 2 more)
        for i in range(30):
            Attendance.objects.create(
                employee=self.employee,
                date=start + timedelta(days=i),
                in_time=time(9, 0, 0),
                out_time=time(17, 0, 0),  # 8-hour shift
                status="Present"
            )
        
        final_balance = calculate_leave_balance(self.employee, self.payroll)
        
        # Opening = 28, Credit = 2
        # Closing would be 30, which equals max
        self.assertEqual(final_balance, Decimal("30.00"))
    
    def test_low_attendance_zero_credit(self):
        """Test low attendance gets zero credit"""
        today = date.today()
        start = today.replace(day=1)
        
        # Only 10 days present (below credit_1_limit of 15)
        for i in range(10):
            Attendance.objects.create(
                employee=self.employee,
                date=start + timedelta(days=i),
                in_time=time(9, 0, 0),
                out_time=time(17, 0, 0),  # 8-hour shift
                status="Present"
            )
        
        # Rest absent (no in_time/out_time)
        for i in range(10, 30):
            Attendance.objects.create(
                employee=self.employee,
                date=start + timedelta(days=i),
                status="Absent"
            )
        
        final_balance = calculate_leave_balance(self.employee, self.payroll)
        balance = LeaveBalance.objects.filter(employee=self.employee).latest('id')
        
        # 10 days <= 15, so credit_low = 0
        # Paid = 10, Leave taken = 20
        # Balance = 0 + 0 - 20 = -20, floored to 0
        # LWP = 20
        self.assertEqual(balance.leave_without_pay, Decimal("20.00"))
        # Final = 0 + 0 (no credit) = 0
        self.assertEqual(final_balance, Decimal("0.00"))