
from django.urls import path

from website import views

urlpatterns = [    
    # path('',views.test,name="test"),
    path("", views.admin_dashboard, name="admin-dashboard"),

    path('home',views.home,name="home"),
    path('employees/', views.employee_list, name='employee_list'),

    path('employee/', views.create_or_edit_employee, name='employee_create'),
    path('employee/<int:employee_id>/', views.create_or_edit_employee, name='employee_edit'),
    path('employee-detail/<int:pk>/', views.employee_detail, name='employee_detail'),
    path('attachments/<int:pk>/download/', views.download_attachment, name='download_attachment'),
    # urls.py
    # path('employee/<int:pk>/edit/', views.employee_edit, name='employee_edit'),

    # path('create-offboarding',views.create_offboarding,name="create-offboarding"),
    # path("offboarding/<int:off_id>/details/",views.offboarding_detail,name="offboarding_detail"),
    # path("offboarding/<int:id>/edit-data/", views.offboarding_edit_data, name="offboarding_edit_data"),





    # path('delete-offboarding/<int:pk>/', views.delete_offboarding, name='delete-offboarding'),
        # Main page (list + create + edit in modals)
    path('offboarding/', views.offboarding_list, name='offboarding-list'),
    
    # AJAX endpoints for modals
    path('offboarding/<int:off_id>/details/', views.offboarding_detail, name='offboarding-detail'),
    path('offboarding/<int:id>/edit-data/', views.offboarding_edit_data, name='offboarding-edit-data'),
    path('delete-offboarding/<int:pk>/', views.offboarding_delete, name='offboarding-delete'),
    # path('create-branch',views.create_branch,name="create-branch"),
    path('create-branch',views.create_branchs,name="create-branch"),
    path('create-company/',views.create_company,name="create-company"),
    path("company/<int:company_id>/edit/", views.edit_company, name="edit_company"),
    path("company/<int:company_id>/get/", views.get_company, name="get_company"),

    path("company/delete/<int:company_id>/", views.delete_company, name="delete_company"),
    path("employee/delete/<int:employee_id>/", views.delete_employee, name="delete_employee"),







    path("company/<int:pk>/details/", views.company_details_api, name="company_details_api"),
    path("branch/<int:pk>/details/", views.branch_details_api, name="branch_details_api"),
    path("branch/<int:branch_id>/edit/", views.edit_branch, name="edit_branch"),
    path("branch/<int:branch_id>/get/", views.get_branch, name="get_branch"),
    path("branch/delete/<int:branch_id>/", views.delete_branch, name="delete_branch"),










    path('create-salary',views.create_salary,name="create-salary"),
    path("salary/details/<int:pk>/", views.salary_details, name="salary_details"),
    path("download-employees/", views.download_employees_excel, name="download_employees"),
    path("download-leave/", views.download_leave_excel, name="download_leave"),
    path("upload-attendance/", views.upload_attendance_excel, name="upload_attendance"),
    path("attendance/", views.attendance_list, name="attendance"),
    path("attendance/<int:employee_id>/", views.employee_attendance_detail, name="employee_attendance_detail"),
    path("ajax/employees/search/", views.employee_search, name="employee_search"),

    path("submit-correction-request/", views.submit_correction_request, name="submit_correction_request"),
    path("approve-correction/<int:request_id>/", views.approve_correction_request, name="approve_correction"),
    path("reject-correction/<int:request_id>/", views.reject_correction_request, name="reject_correction"),  
    # employee advances
    # path('advances/', views.advances_list, name='advances-list'),
    # path('advances/create/', views.create_advance, name='create-advance'),
    # path('advances/<int:advance_id>/add-installment/', views.add_installment, name='add-installment'),
    # path('advances/<int:advance_id>/installments/', views.view_installments, name='view-installments'),
    # path('advances/mark-paid/<int:installment_id>/', views.mark_paid, name='mark-paid'),
    # path('advances/undo-paid/<int:installment_id>/', views.undo_paid, name='undo-paid'),
    # path('advances/skip/<int:installment_id>/', views.skip_installment, name='skip-installment'),  # ✅ NEW

    path("leave-balance/", views.leave_balance_view, name="leave_balance"),
    path("employees/<int:employee_id>/compoffs/", views.employee_compoff_details, name="employee-compoff-details"),
    path("employees/<int:employee_id>/leave-history/", views.employee_leave_history, name="employee_leave_history"),
    path('approve-compoff/<int:compoff_id>/', views.approve_compoff, name='approve_compoff'),
    path('reject-compoff/<int:compoff_id>/', views.reject_compoff, name='reject_compoff'),
    path("submit-comp-off-request/", views.submit_comp_off_request, name="submit_comp_off_request"),
    # path("salary-increment/", views.create_salary_increment, name="salary_increment"),
    # path("salary/increment/details/<int:pk>/", views.increment_details, name="increment_details"),
    
    
     # Main page - list and create (no pk needed)
    path('salary-increment/', views.create_salary_increment, name='salary_increment'),
    
    # Specific actions (pk required)
    path('salary/increment/edit/<int:pk>/', views.edit_increment, name='edit_increment'),
    path('salary/increment/update/<int:pk>/', views.update_salary_increment, name='update_increment'),
    path('salary/increment/delete/<int:pk>/', views.delete_salary_increment, name='delete_increment'),
    path('salary/increment/details/<int:pk>/', views.increment_details, name='increment_details'),

    
    
    
    
    
    
    
    path("salary-history/", views.salary_history, name="salary_history"),
    path("ajax/employee-details/", views.employee_salary_ajax, name="employee_details_ajax"),

    # DETAIL MODAL
    path("salary-history/detail/<int:pk>/", 
        views.salary_history_detail, name="salary_history_detail"),

    path("salary-history/compare/<int:history_id>/<int:employee_id>/",
        views.salary_compare, name="salary_compare"),

    # CHART DATA
    path('salary-history/chart-data/<int:employee_id>/',
         views.salary_timeline_data,
         name='salary_timeline_data'),

    # EXPORTS
    path('salary-history/export/excel/',
         views.salary_history_export_excel,
         name='salary_history_export_excel'),

    # path('salary-history/export/pdf/',
    #      views.salary_history_export_pdf,
    #      name='salary_history_export_pdf'),

    # path("leave-balance/", leave_balance_view, name="leave_balance"),

    path('payroll-settings/', views.get_payroll_settings, name='get_payroll_settings'),
    path('settings/', views.settings_page, name='settings-page'),
    path('settings/save/payroll/', views.save_payroll_settings, name='save-payroll-settings'),
    path('settings/save/leave/', views.save_leave_settings, name='save-leave-settings'),

    path("leave-credit-policy/", views.leave_credit_policy_view, name="leave_credit_policy"),
    path("leave-apply/", views.leave_apply_view, name="leave_apply"),
    path("approve-leave/<int:leave_id>/", views.approve_leave, name="approve_leave"),
    path("reject-leave/<int:leave_id>/", views.reject_leave, name="reject_leave"),


    path("leave-credit-policy/update/", views.update_leave_credit_policy, name="update_leave_credit_policy"),
    path("recalculate-leaves/", views.recalculate_leave_balances, name="recalculate_leave_balances"),

    path('attendance-correction-requests/', views.attendance_correction_requests_list, name='attendance_correction_requests_list'),
    path("branch/<int:pk>/details/", views.branch_details_api, name="branch_details_api"),
    path("attendance-correction/<int:pk>/details/", views.attendance_correction_detail, name="attendance_correction_detail"),

    path('comp-off-requests/', views.comp_off_requests_list, name='comp_off_requests_list'),
    path("comp-off/<int:pk>/month/", views.comp_off_requests, name="comp_off_requests"),





    path('advances/', views.advance_list, name='advances-list'),
    path('advances/create/', views.advance_create, name='create-advance'),
    path('advances/<int:pk>/', views.advance_detail, name='advance-detail'),
    path('advances/<int:pk>/pay/', views.pay_advance, name='advances-pay'),
    path('advances/<int:pk>/skip/', views.skip_advance_month, name='advances-skip'),
    path("advances/<int:pk>/revert-skip/", views.revert_skip_view, name="revert-skip"),



    path("payroll/", views.payroll_run_list, name="payroll-run-list"),
    path("payroll/run/create/", views.payroll_run_create, name="payroll-run-create"),
    path("payroll/run/<int:run_id>/", views.payroll_run_detail, name="payroll-run-detail"),
    path("payroll/record/<int:record_id>/update/", views.payroll_record_update, name="payroll-record-update"),
    path("payroll/run/<int:run_id>/finalize/", views.payroll_run_finalize, name="payroll-run-finalize"),


    path("payroll/<int:run_id>/export/excel/", views.payroll_export_excel, name="payroll-export-excel"),
    path("payroll/<int:run_id>/export/pdf/", views.payroll_export_pdf, name="payroll-export-pdf"),


    path("download-empty-excel/", views.download_empty_excel, name="download-empty-excel"),

]

