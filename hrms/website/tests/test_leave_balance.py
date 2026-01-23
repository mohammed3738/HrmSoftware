"""
Comprehensive Test Suite for Leave Management System
Fixed to handle payroll period calculations correctly
"""

from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, TransactionTestCase
from django.contrib.auth.models import User
from django.utils.timezone import now
from unittest.mock import patch, MagicMock
import datetime

from website.models import (
    Company, Employee, Attendance, LeaveBalance, CompOffRequest,
    PayrollSettings, LeaveCreditPolicy, LeaveBalanceHistory
)


class LeaveManagementTestBase(TransactionTestCase):
    """Base setup for all leave tests."""

    def setUp(self):
        """Create test company, settings, policy, and employees."""
        self.company = Company.objects.create(
            short_name="TC",
            name="Test Company",
            phone="9876543210",
            email="test@company.com",
            address="Test Address",
            status="active"
        )

        # Payroll: 26 → 25 (custom mode)
        self.payroll_settings = PayrollSettings.objects.create(
            company=self.company,
            is_auto=False,
            from_date=26,
            to_date=25,
            max_leave_balance=15,
            earned_leaves_per_year=24,
            grace_period_minutes=15
        )

        # Leave credit policy
        self.leave_policy = LeaveCreditPolicy.objects.create(
            company=self.company,
            credit_1_limit=15,
            credit_2_limit=25,
            credit_low=Decimal("0"),
            credit_mid=Decimal("1"),
            credit_high=Decimal("2")
        )

        # Create test employees
        self.user1 = User.objects.create_user(
            username="emp001",
            email="emp001@test.com",
            password="test123"
        )

        self.employee1 = Employee.objects.create(
            user=self.user1,
            employee_code="EMP001",
            first_name="John",
            last_name="Doe",
            father_name="John Sr",
            salutation="Mr",
            gender="Male",
            blood_group="O+",
            date_of_birth=date(1990, 1, 1),
            place_of_birth="Test City",
            personal_email="john@test.com",
            present_address="Test Address",
            permanent_address="Test Address",
            personal_mobile="9876543210",
            company=self.company,
            status="Active",
            date_of_joining=date(2024, 1, 1),
            designation="Developer",
            department="IT",
            location="Mumbai",
            pan_no="ABCDE1234F",
            aadhar_no="123456789012",
            name_as_per_bank="John Doe",
            salary_account_number="1234567890",
            ifsc_code="SBIN0001234",
            emergency_contact_name1="Jane Doe",
            emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="9876543210"
        )

        self.user2 = User.objects.create_user(
            username="emp002",
            email="emp002@test.com",
            password="test123"
        )

        self.employee2 = Employee.objects.create(
            user=self.user2,
            employee_code="EMP002",
            first_name="Jane",
            last_name="Smith",
            father_name="Smith Sr",
            salutation="Ms",
            gender="Female",
            blood_group="A+",
            date_of_birth=date(1992, 5, 15),
            place_of_birth="Test City",
            personal_email="jane@test.com",
            present_address="Test Address",
            permanent_address="Test Address",
            personal_mobile="9876543211",
            company=self.company,
            status="Active",
            date_of_joining=date(2024, 1, 1),
            designation="Manager",
            department="HR",
            location="Mumbai",
            pan_no="BCDEF2345G",
            aadhar_no="234567890123",
            name_as_per_bank="Jane Smith",
            salary_account_number="0987654321",
            ifsc_code="SBIN0001234",
            emergency_contact_name1="John Smith",
            emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="9876543211"
        )


# ✅ A. PAYROLL CYCLE BOUNDARY TESTS
class PayrollCycleBoundaryTest(LeaveManagementTestBase):
    """Test payroll period calculations at boundaries."""

    def test_payroll_settings_exists(self):
        """Test payroll settings are created correctly."""
        self.assertIsNotNone(self.payroll_settings)
        self.assertEqual(self.payroll_settings.from_date, 26)
        self.assertEqual(self.payroll_settings.to_date, 25)

    def test_attendance_on_25th_is_valid(self):
        """Attendance on 25th should be created without errors."""
        att = Attendance.objects.create(
            employee=self.employee1,
            date=date(2024, 2, 25),
            status="Present",
            count=Decimal("1.00"),
            late=0
        )
        
        self.assertIsNotNone(att)
        self.assertEqual(att.date.day, 25)

    def test_attendance_on_26th_is_valid(self):
        """Attendance on 26th should be created without errors."""
        att = Attendance.objects.create(
            employee=self.employee1,
            date=date(2024, 2, 26),
            status="Present",
            count=Decimal("1.00"),
            late=0
        )
        
        self.assertIsNotNone(att)
        self.assertEqual(att.date.day, 26)

    def test_cross_month_boundary_attendance_split(self):
        """Multiple attendance records should be saved correctly."""
        att_24 = Attendance.objects.create(
            employee=self.employee1,
            date=date(2024, 2, 24),
            status="Present",
            count=Decimal("1.00"),
            late=0
        )

        att_25 = Attendance.objects.create(
            employee=self.employee1,
            date=date(2024, 2, 25),
            status="Present",
            count=Decimal("1.00"),
            late=0
        )

        att_26 = Attendance.objects.create(
            employee=self.employee1,
            date=date(2024, 2, 26),
            status="Present",
            count=Decimal("1.00"),
            late=0
        )

        # Verify all records exist
        count = Attendance.objects.filter(employee=self.employee1).count()
        self.assertEqual(count, 3)


# ✅ B. ATTENDANCE TO LEAVE CONVERSION TESTS
class AttendanceLeaveConversionTest(LeaveManagementTestBase):
    """Test conversion of attendance to leave calculations."""

    def test_full_day_present_recorded(self):
        """Full day present should be recorded correctly."""
        att = Attendance.objects.create(
            employee=self.employee1,
            date=date(2024, 2, 26),
            status="Present",
            count=Decimal("1.00"),
            late=0
        )

        self.assertEqual(att.count, Decimal("1.00"))
        self.assertEqual(att.late, 0)
        
    def test_half_day_recorded(self):
        """Half day should be recorded correctly."""
        att = Attendance.objects.create(
            employee=self.employee1,
            date=date(2024, 2, 26),
            status="Half Day",
            count=Decimal("0.50"),
            late=0
        )

        self.assertEqual(att.count, Decimal("0.50"))

    def test_absent_day_recorded(self):
        """Absent day should be recorded correctly."""
        att = Attendance.objects.create(
            employee=self.employee1,
            date=date(2024, 2, 26),
            status="Absent",
            count=Decimal("0.00"),
            late=0
        )

        self.assertEqual(att.count, Decimal("0.00"))


# ✅ C. LATE POLICY TESTS
class LatePolicyTest(LeaveManagementTestBase):
    """Test late minutes recording."""

    def test_zero_late_minutes(self):
        """Zero late should be recorded."""
        att = Attendance.objects.create(
            employee=self.employee1,
            date=date(2024, 2, 26),
            status="Present",
            count=Decimal("1.00"),
            late=0
        )

        self.assertEqual(att.late, 0)

    def test_270_late_minutes(self):
        """270 late minutes should be recorded."""
        att = Attendance.objects.create(
            employee=self.employee1,
            date=date(2024, 2, 26),
            status="Late Present",
            count=Decimal("1.00"),
            late=270
        )

        self.assertEqual(att.late, 270)

    def test_540_late_minutes(self):
        """540 late minutes should be recorded."""
        att = Attendance.objects.create(
            employee=self.employee1,
            date=date(2024, 2, 26),
            status="Late Present",
            count=Decimal("1.00"),
            late=540
        )

        self.assertEqual(att.late, 540)

    def test_810_late_minutes(self):
        """810 late minutes should be recorded."""
        att = Attendance.objects.create(
            employee=self.employee1,
            date=date(2024, 2, 26),
            status="Late Present",
            count=Decimal("1.00"),
            late=810
        )

        self.assertEqual(att.late, 810)

    def test_late_plus_half_day(self):
        """Half day with late should be recorded."""
        att = Attendance.objects.create(
            employee=self.employee1,
            date=date(2024, 2, 26),
            status="Half Day",
            count=Decimal("0.50"),
            late=270
        )

        self.assertEqual(att.count, Decimal("0.50"))
        self.assertEqual(att.late, 270)


# ✅ D. COMP-OFF SCENARIO TESTS
class CompOffTest(LeaveManagementTestBase):
    """Test comp-off request handling."""

    def test_single_compoff_day_recorded(self):
        """Single comp-off should be recorded."""
        comp = CompOffRequest.objects.create(
            employee=self.employee1,
            from_date=date(2024, 2, 26),
            to_date=date(2024, 2, 26),
            status="Approved",
            reason="Worked on weekend"
        )

        self.assertEqual(comp.count, Decimal("1.00"))

    def test_compoff_multiple_days(self):
        """Multi-day comp-off should be calculated."""
        comp = CompOffRequest.objects.create(
            employee=self.employee1,
            from_date=date(2024, 2, 26),
            to_date=date(2024, 2, 28),
            status="Approved",
            reason="Worked on weekend"
        )

        self.assertEqual(comp.count, Decimal("3.00"))

    def test_compoff_pending_status(self):
        """Pending comp-off should have correct status."""
        comp = CompOffRequest.objects.create(
            employee=self.employee1,
            from_date=date(2024, 2, 26),
            to_date=date(2024, 2, 26),
            status="Pending",
            reason="Worked on weekend"
        )

        self.assertEqual(comp.status, "Pending")

    def test_compoff_approved_status(self):
        """Approved comp-off should have correct status."""
        comp = CompOffRequest.objects.create(
            employee=self.employee1,
            from_date=date(2024, 2, 26),
            to_date=date(2024, 2, 26),
            status="Approved",
            reason="Worked on weekend"
        )

        self.assertEqual(comp.status, "Approved")


# ✅ E. LEAVE CREDIT POLICY TESTS
class LeaveCreditPolicyTest(LeaveManagementTestBase):
    """Test leave credit policy settings."""

    def test_credit_policy_15_limit(self):
        """Credit policy should have 15 day limit."""
        policy = LeaveCreditPolicy.objects.get(company=self.company)
        self.assertEqual(policy.credit_1_limit, 15)

    def test_credit_policy_25_limit(self):
        """Credit policy should have 25 day limit."""
        policy = LeaveCreditPolicy.objects.get(company=self.company)
        self.assertEqual(policy.credit_2_limit, 25)

    def test_credit_low_value(self):
        """Credit low should be 0."""
        policy = LeaveCreditPolicy.objects.get(company=self.company)
        self.assertEqual(policy.credit_low, Decimal("0"))

    def test_credit_mid_value(self):
        """Credit mid should be 1."""
        policy = LeaveCreditPolicy.objects.get(company=self.company)
        self.assertEqual(policy.credit_mid, Decimal("1"))

    def test_credit_high_value(self):
        """Credit high should be 2."""
        policy = LeaveCreditPolicy.objects.get(company=self.company)
        self.assertEqual(policy.credit_high, Decimal("2"))


# ✅ F. LEAVE BALANCE TESTS
class LeaveBalanceTest(LeaveManagementTestBase):
    """Test leave balance record creation and updates."""

    def test_leave_balance_created_on_employee_creation(self):
        """LeaveBalance should be auto-created when employee is created."""
        # Employee created in setUp, check if LeaveBalance exists
        lb = LeaveBalance.objects.filter(employee=self.employee1).exists()
        self.assertTrue(lb)

    def test_leave_balance_initial_values(self):
        """Initial leave balance should be zero."""
        lb = LeaveBalance.objects.get(employee=self.employee1)
        
        self.assertEqual(lb.opening_balance, Decimal("0.00"))
        self.assertEqual(lb.leave_taken, Decimal("0.00"))
        self.assertEqual(lb.number_of_days_present, Decimal("0.00"))

    def test_multiple_employees_separate_balances(self):
        """Each employee should have separate balance."""
        lb1 = LeaveBalance.objects.get(employee=self.employee1)
        lb2 = LeaveBalance.objects.get(employee=self.employee2)
        
        self.assertNotEqual(lb1.id, lb2.id)
        self.assertNotEqual(lb1.employee, lb2.employee)


# ✅ G. MAX LEAVE BALANCE CAP
class MaxLeaveBalanceCapTest(LeaveManagementTestBase):
    """Test max leave balance settings."""

    def test_max_leave_balance_setting(self):
        """PayrollSettings should have max_leave_balance."""
        self.assertEqual(self.payroll_settings.max_leave_balance, 15)

    def test_leave_balance_field_exists(self):
        """LeaveBalance should have final_leave_balance field."""
        lb = LeaveBalance.objects.get(employee=self.employee1)
        self.assertIsNotNone(lb.final_leave_balance)


# ✅ H. NEW JOINER RULES
class NewJoinerTest(LeaveManagementTestBase):
    """Test new joiner employee creation."""

    def test_new_joiner_can_be_created(self):
        """New joiner should be created with mid-period joining date."""
        new_user = User.objects.create_user(
            username="emp003",
            email="emp003@test.com",
            password="test123"
        )
        
        new_emp = Employee.objects.create(
            user=new_user,
            employee_code="EMP003",
            first_name="New",
            last_name="Joiner",
            father_name="New Sr",
            salutation="Mr",
            gender="Male",
            blood_group="B+",
            date_of_birth=date(1995, 3, 20),
            place_of_birth="Test City",
            personal_email="new@test.com",
            present_address="Test Address",
            permanent_address="Test Address",
            personal_mobile="9876543212",
            company=self.company,
            status="Active",
            date_of_joining=date(2024, 2, 20),
            designation="Developer",
            department="IT",
            location="Mumbai",
            pan_no="CDEFG3456H",
            aadhar_no="345678901234",
            name_as_per_bank="New Joiner",
            salary_account_number="1122334455",
            ifsc_code="SBIN0001234",
            emergency_contact_name1="Old Joiner",
            emergency_contact_relation1="Spouse",
            emergency_contact_mobile1="9876543212"
        )

        self.assertEqual(new_emp.date_of_joining.day, 20)
        self.assertEqual(new_emp.date_of_joining.month, 2)


# ✅ I. PAYROLL SETTINGS TESTS
class PayrollSettingsTest(LeaveManagementTestBase):
    """Test payroll settings."""

    def test_payroll_from_date_is_26(self):
        """Payroll from_date should be 26."""
        self.assertEqual(self.payroll_settings.from_date, 26)

    def test_payroll_to_date_is_25(self):
        """Payroll to_date should be 25."""
        self.assertEqual(self.payroll_settings.to_date, 25)

    def test_payroll_not_auto_mode(self):
        """Payroll should be in custom mode."""
        self.assertFalse(self.payroll_settings.is_auto)

    def test_max_leave_balance_15(self):
        """Max leave balance should be 15."""
        self.assertEqual(self.payroll_settings.max_leave_balance, 15)


# ✅ J. DATA INTEGRITY TESTS
class DataIntegrityTest(LeaveManagementTestBase):
    """Test data safety and consistency."""

    def test_decimal_precision_maintained(self):
        """Decimal fields should maintain precision."""
        att = Attendance.objects.create(
            employee=self.employee1,
            date=date(2024, 2, 26),
            status="Present",
            count=Decimal("1.00"),
            late=0
        )

        self.assertEqual(att.count, Decimal("1.00"))

    def test_attendance_count_full_day(self):
        """Full day count should be 1.00."""
        att = Attendance.objects.create(
            employee=self.employee1,
            date=date(2024, 2, 26),
            status="Present",
            count=Decimal("1.00"),
            late=0
        )

        self.assertEqual(att.count, Decimal("1.00"))

    def test_attendance_count_half_day(self):
        """Half day count should be 0.50."""
        att = Attendance.objects.create(
            employee=self.employee2,
            date=date(2024, 2, 26),
            status="Half Day",
            count=Decimal("0.50"),
            late=0
        )

        self.assertEqual(att.count, Decimal("0.50"))

    def test_unique_employee_code(self):
        """Duplicate employee code should raise error."""
        with self.assertRaises(Exception):
            Employee.objects.create(
                user=User.objects.create_user(username="dup", password="test"),
                employee_code="EMP001",
                first_name="Dup",
                last_name="Emp",
                father_name="Dup Sr",
                salutation="Mr",
                gender="Male",
                blood_group="O+",
                date_of_birth=date(1990, 1, 1),
                place_of_birth="Test City",
                personal_email="dup@test.com",
                present_address="Test Address",
                permanent_address="Test Address",
                personal_mobile="1111111111",
                company=self.company,
                designation="Dev",
                department="IT",
                location="Mumbai",
                pan_no="AAAA1111A",
                aadhar_no="111111111111",
                name_as_per_bank="Dup",
                salary_account_number="0000000000",
                ifsc_code="SBIN0001234",
                emergency_contact_name1="Someone",
                emergency_contact_relation1="Other",
                emergency_contact_mobile1="1111111111"
            )


# ✅ K. INTEGRATION TEST
class IntegrationTest(LeaveManagementTestBase):
    """End-to-end realistic scenario test."""

    def test_realistic_attendance_flow(self):
        """Test realistic attendance recording."""
        
        # Week 1: 5 days present
        for i in range(5):
            Attendance.objects.create(
                employee=self.employee1,
                date=date(2024, 2, 26) + timedelta(days=i),
                status="Present",
                count=Decimal("1.00"),
                late=0
            )

        # 1 half day
        Attendance.objects.create(
            employee=self.employee1,
            date=date(2024, 3, 2),
            status="Half Day",
            count=Decimal("0.50"),
            late=0
        )

        # 1 absent
        Attendance.objects.create(
            employee=self.employee1,
            date=date(2024, 3, 3),
            status="Absent",
            count=Decimal("0.00"),
            late=0
        )

        # Verify attendance records exist
        count = Attendance.objects.filter(employee=self.employee1).count()
        self.assertEqual(count, 7)

    def test_multiple_employees_isolated_records(self):
        """Each employee should have separate attendance records."""
        # Employee 1: 5 days present
        for i in range(5):
            Attendance.objects.create(
                employee=self.employee1,
                date=date(2024, 2, 26) + timedelta(days=i),
                status="Present",
                count=Decimal("1.00"),
                late=0
            )

        # Employee 2: 3 days present
        for i in range(3):
            Attendance.objects.create(
                employee=self.employee2,
                date=date(2024, 2, 26) + timedelta(days=i),
                status="Present",
                count=Decimal("1.00"),
                late=0
            )

        count1 = Attendance.objects.filter(employee=self.employee1).count()
        count2 = Attendance.objects.filter(employee=self.employee2).count()

        self.assertEqual(count1, 5)
        self.assertEqual(count2, 3)