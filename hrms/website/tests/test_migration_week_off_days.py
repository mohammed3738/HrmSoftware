"""
Migration 0061 turns Employee.week_off_day (one day) into week_off_days
("5,6"). An employee's existing day must carry over unchanged.

Run with: python manage.py test website.tests.test_migration_week_off_days
"""
from datetime import date

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [("website", "0060_payroll_month_is_ending_month")]
AFTER = [("website", "0061_employee_week_off_days")]


class WeekOffDaysMigrationTest(TransactionTestCase):
    def test_existing_single_day_carries_over(self):
        executor = MigrationExecutor(connection)
        executor.migrate(BEFORE)
        old_apps = executor.loader.project_state(BEFORE).apps
        Company = old_apps.get_model("website", "Company")
        Employee = old_apps.get_model("website", "Employee")
        company = Company.objects.create(name="Mig Co")
        Employee.objects.create(company=company, first_name="Sat", employee_code="M1",
                                date_of_joining=date(2020, 1, 1), week_off_day=5)
        Employee.objects.create(company=company, first_name="None", employee_code="M2",
                                date_of_joining=date(2020, 1, 1), week_off_day=None)

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(AFTER)
        new_apps = executor.loader.project_state(AFTER).apps
        Employee = new_apps.get_model("website", "Employee")
        self.assertEqual(Employee.objects.get(employee_code="M1").week_off_days, "5")
        self.assertEqual(Employee.objects.get(employee_code="M2").week_off_days, "")
