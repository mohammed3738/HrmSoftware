import pytest
from decimal import Decimal
from datetime import date
from website.models import Company
from website.models import PayrollSettings
from website.models import LeaveCreditPolicy
from website.models import Employee



from django.db.models.signals import post_save

@pytest.fixture(autouse=True)
def disable_signals():
    post_save.receivers = []


@pytest.fixture
def company(db):
    return Company.objects.create(name="Test Company")

@pytest.fixture
def payroll_settings(company):
    return PayrollSettings.objects.create(
        company=company,
        is_auto=False,
        from_date=26,
        to_date=25,
        earned_leaves_per_year=12,
        max_leave_balance=30,
        carry_forward=True,
        reset_month=4
    )

@pytest.fixture
def leave_policy(company):
    return LeaveCreditPolicy.objects.create(
        company=company,
        credit_1_limit=10,
        credit_2_limit=20,
        credit_low=Decimal("0"),
        credit_mid=Decimal("1"),
        credit_high=Decimal("2"),
    )



@pytest.fixture
def employee(company):
    return Employee.objects.create(
        first_name="Test",
        employee_code="E001",
        date_of_birth="1990-01-01",
        date_of_joining=date.today(),
        company=company,
        status="Active"
    )
