from datetime import date
from website.tasks import run_monthly_leave_balance
from website.models import LeaveBalance
from website.tests.utils import create_attendance

def test_celery_task(company, employee, payroll_settings, leave_policy):
    # Arrange
    create_attendance(employee, date(2024, 1, 26), 1)

    # Act (call task directly, sync)
    run_monthly_leave_balance(company.id)

    # Assert
    assert LeaveBalance.objects.count() == 1
