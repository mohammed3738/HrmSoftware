"""
Django management command for calculating leave balance
Prevents duplicates by using update_or_create
Usage: python manage.py calculate_leave_balance --company-id=1
       python manage.py calculate_leave_balance --all
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from website.models import Company, Employee, PayrollSettings
from website.services.leave_balance_service import calculate_leave_balance


class Command(BaseCommand):
    help = 'Calculate monthly leave balance for employees (no duplicates)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--company-id',
            type=int,
            help='Calculate for specific company ID',
        )
        parser.add_argument(
            '--employee-id',
            type=int,
            help='Calculate for specific employee ID',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Calculate for all companies',
        )

    def handle(self, *args, **options):
        company_id = options.get('company_id')
        employee_id = options.get('employee_id')
        process_all = options.get('all')

        if employee_id:
            # Process single employee
            self.process_employee(employee_id)
            
        elif company_id:
            # Process single company
            self.process_company(company_id)
            
        elif process_all:
            # Process all companies
            companies = Company.objects.all()
            for company in companies:
                self.process_company(company.id)
                
        else:
            self.stdout.write(
                self.style.ERROR('Please specify --company-id, --employee-id, or --all')
            )

    def process_employee(self, employee_id):
        """Process a single employee"""
        try:
            employee = Employee.objects.get(id=employee_id)
            payroll = PayrollSettings.objects.get(company=employee.company)
            
            with transaction.atomic():
                final_balance = calculate_leave_balance(employee, payroll)
                
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ {employee.employee_code}: Balance = {final_balance} (no duplicates created)'
                )
            )
            
        except Employee.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Employee {employee_id} not found')
            )
        except PayrollSettings.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'No payroll settings for employee\'s company')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error processing employee {employee_id}: {str(e)}')
            )

    def process_company(self, company_id):
        """Process all active employees in a company"""
        try:
            company = Company.objects.get(id=company_id)
            payroll = PayrollSettings.objects.get(company=company)
            
            self.stdout.write(f'\n📊 Processing company: {company.name}')
            
            employees = Employee.objects.filter(
                company=company,
                status="Active"
            )
            
            success_count = 0
            error_count = 0
            
            for employee in employees:
                try:
                    with transaction.atomic():
                        final_balance = calculate_leave_balance(employee, payroll)
                        
                    self.stdout.write(
                        f'  ✓ {employee.employee_code}: {final_balance}'
                    )
                    success_count += 1
                    
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f'  ✗ {employee.employee_code}: {str(e)}'
                        )
                    )
                    error_count += 1
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✅ Completed: {success_count} successful, {error_count} errors\n'
                )
            )
            
        except Company.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Company {company_id} not found')
            )
        except PayrollSettings.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'No payroll settings for company {company_id}')
            )