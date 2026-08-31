
from django.urls import path

from website import views

urlpatterns = [    
    # path('',views.test,name="test"),
    path("", views.admin_dashboard, name="admin-dashboard"),

    path('home',views.home,name="home"),
    path('employees/', views.employee_list, name='employee_list'),
    path('my-profile/', views.my_profile, name='my_profile'),
    path('my-dashboard/', views.employee_dashboard, name='employee-dashboard'),
    path('employees/bulk-action/', views.bulk_employee_action, name='bulk-employee-action'),
    path('employee/', views.create_or_edit_employee, name='employee_create'),
    path('employee/<int:employee_id>/', views.create_or_edit_employee, name='employee_edit'),
    path('employee-detail/<int:pk>/', views.employee_detail, name='employee_detail'),
    path('attachments/<int:pk>/download/', views.download_attachment, name='download_attachment'),
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

    path('upload-company/', views.upload_company_excel, name='upload-company-excel'),
    path('company/upload-template/', views.download_company_upload_template, name='download-company-upload-template'),
    path('upload-branch/', views.upload_branch_excel, name='upload-branch-excel'),
    path('branch/upload-template/', views.download_branch_upload_template, name='download-branch-upload-template'),

    path("login/", views.login_view, name="login"),

    path("create-user/", views.create_user_view, name="create-user"),
    path("logout/", views.logout_view, name="logout"),
    path("change-password/", views.change_password, name="change-password"),

    path('create-salary',views.create_salary,name="create-salary"),
    path("salary/details/<int:pk>/", views.salary_details, name="salary_details"),
    path("download-employees/", views.download_employees_excel, name="download_employees"),
    path("download-leave/", views.download_leave_excel, name="download_leave"),
    path("upload-attendance/", views.upload_attendance_excel, name="upload_attendance"),
    path("upload-attendance/init/", views.upload_attendance_init, name="upload_attendance_init"),
    path("upload-attendance/<int:upload_id>/chunk/", views.upload_attendance_chunk, name="upload_attendance_chunk"),

    path("attendance-progress/<int:upload_id>/", views.attendance_upload_progress, name="attendance_upload_progress"),

    path("recalculate-attendance/init/", views.recalculate_attendance_init, name="recalculate_attendance_init"),
    path("recalculate-attendance/chunk/", views.recalculate_attendance_chunk, name="recalculate_attendance_chunk"),
    path("attendance/late-review/", views.late_attendance_review, name="late_attendance_review"),
    path("attendance/override-status/", views.override_attendance_status, name="override_attendance_status"),
    path("attendance/bulk-override-status/", views.bulk_override_attendance_status, name="bulk_override_attendance_status"),
    path("attendance/register/", views.attendance_register_view, name="attendance-register"),

    path("attendance/shift-roster/", views.shift_roster_list, name="shift_roster_list"),
    path("attendance/shift-roster/add/", views.add_shift_assignment, name="add_shift_assignment"),
    path("attendance/shift-roster/<int:pk>/edit/", views.edit_shift_assignment, name="edit_shift_assignment"),
    path("attendance/shift-roster/<int:pk>/delete/", views.delete_shift_assignment, name="delete_shift_assignment"),
    path("api/shift-roster/<int:pk>/", views.api_get_shift_assignment, name="api_get_shift_assignment"),
    path("attendance/", views.attendance_list, name="attendance"),
    path("attendance/<int:employee_id>/", views.employee_attendance_detail, name="employee_attendance_detail"),
    path("ajax/employees/search/", views.employee_search, name="employee_search"),

    path("submit-correction-request/", views.submit_correction_request, name="submit_correction_request"),
    path("approve-correction/<int:request_id>/", views.approve_correction_request, name="approve_correction"),
    path("reject-correction/<int:request_id>/", views.reject_correction_request, name="reject_correction"),
    path("bulk-approve-correction/", views.bulk_approve_correction, name="bulk_approve_correction"),

    path("leave-balance/", views.leave_balance_view, name="leave_balance"),
    path("employees/<int:employee_id>/compoffs/", views.employee_compoff_details, name="employee-compoff-details"),
    path("employees/<int:employee_id>/leave-history/", views.employee_leave_history, name="employee_leave_history"),
    path('approve-compoff/<int:compoff_id>/', views.approve_compoff, name='approve_compoff'),
    path('reject-compoff/<int:compoff_id>/', views.reject_compoff, name='reject_compoff'),
    path('bulk-approve-compoff/', views.bulk_approve_compoff, name='bulk_approve_compoff'),
    path("submit-comp-off-request/", views.submit_comp_off_request, name="submit_comp_off_request"),
    
    
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


    path('payroll-settings/', views.get_payroll_settings, name='get_payroll_settings'),
    path('settings/', views.settings_page, name='settings-page'),
    path('settings/save/payroll/', views.save_payroll_settings, name='save-payroll-settings'),
    path('settings/save/leave/', views.save_leave_settings, name='save-leave-settings'),
    path('settings/save/credit-policy/', views.save_leave_credit_policy, name='save-leave-credit-policy'),
    path('settings/hub/', views.company_settings_hub, name='company-settings-hub'),
    path('settings/roles-permissions/', views.roles_permissions_hub, name='roles-permissions-hub'),
    path('settings/roles-permissions/create-role/', views.create_role, name='create-role'),
    path('settings/roles-permissions/<int:role_id>/rename/', views.rename_role, name='rename-role'),
    path('settings/roles-permissions/<int:role_id>/delete/', views.delete_role, name='delete-role'),
    path('settings/roles-permissions/save/', views.save_role_permissions, name='save-role-permissions'),
    path('settings/roles-permissions/reassign-user/', views.reassign_user_role, name='reassign-user-role'),
    path('settings/hub/broadcast/', views.broadcast_settings_to_all_companies, name='broadcast-settings'),

    path('announcements/', views.announcements_hub, name='announcements-hub'),
    path('announcements/save/', views.save_announcement, name='save-announcement'),
    path('announcements/<int:pk>/delete/', views.delete_announcement, name='delete-announcement'),
    path('announcements/api/', views.announcements_api, name='announcements-api'),
    path('announcements/mark-read/', views.mark_announcement_read, name='mark-announcement-read'),

    path('audit-log/', views.audit_log_view, name='audit-log'),
    path('restore/<str:model_type>/<int:pk>/', views.restore_record, name='restore-record'),

    path("leave-credit-policy/", views.leave_credit_policy_view, name="leave_credit_policy"),
    path("leave-apply/", views.leave_apply_view, name="leave_apply"),
    path("approve-leave/<int:leave_id>/", views.approve_leave, name="approve_leave"),
    path("reject-leave/<int:leave_id>/", views.reject_leave, name="reject_leave"),
    path("bulk-approve-leave/", views.bulk_approve_leave, name="bulk_approve_leave"),


    path("leave-credit-policy/update/", views.update_leave_credit_policy, name="update_leave_credit_policy"),
    # path("recalculate-leaves/", views.recalculate_leave_balances, name="recalculate_leave_balances"),

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
    path("payroll/run/period-preview/", views.payroll_period_preview, name="payroll-period-preview"),
    path("payroll/run/<int:run_id>/", views.payroll_run_detail, name="payroll-run-detail"),
    path("payroll/record/<int:record_id>/update/", views.payroll_record_update, name="payroll-record-update"),
    path("payroll/record/<int:record_id>/salary-slip/", views.salary_slip_view, name="salary-slip"),
    path("payroll/run/<int:run_id>/recalculate/", views.payroll_run_recalculate, name="payroll-run-recalculate"),
    path("payroll/run/<int:run_id>/finalize/", views.payroll_run_finalize, name="payroll-run-finalize"),


    path("payroll/<int:run_id>/export/excel/", views.payroll_export_excel, name="payroll-export-excel"),
    path("payroll/<int:run_id>/export/pdf/", views.payroll_export_pdf, name="payroll-export-pdf"),


    path("download-empty-excel/", views.download_empty_excel, name="download-empty-excel"),

    # Employee Excel import
    path("import-employees/", views.import_employees_excel, name="import-employees"),
    path("import-employees/template/", views.download_employee_import_template, name="employee-import-template"),

    # Salary Excel import
    path("import-salary/", views.import_salary_excel, name="import-salary"),
    path("import-salary/template/", views.download_salary_import_template, name="salary-import-template"),

    path('leave-balance/', views.leave_balance_view, name='leave_balance_report'),
    path('leave-balance/recalculate/', views.recalculate_leave_balances_view, name='recalculate_leave_balances'),

    path('leave-balance/employee/<int:employee_id>/recalc/', views.recalc_employee_leave_balance, name='recalc-employee-leave'),
    path('leave-balance/employee/<int:employee_id>/', views.employee_leave_detail, name='employee-leave-detail'),
    path('leave-balance/override-lwp/', views.override_lwp_view, name='override-lwp'),




    # Holiday Calendar URLs (NO namespace, just simple URLs)
    path('holiday/dashboard/', views.holiday_calendar_dashboard, name='holiday-calendar'),
    path('holiday/', views.holiday_calendar_dashboard, name='holiday-dashboard'),
    path('holiday/add/', views.add_holiday, name='add-holiday'),
    path('holiday/<int:holiday_id>/edit/', views.edit_holiday, name='edit-holiday'),
    path('holiday/<int:holiday_id>/delete/', views.delete_holiday, name='delete-holiday'),
    path('holiday/list/', views.holiday_list, name='holiday-list'),
    path('holiday/settings/save/', views.save_holiday_settings, name='save-holiday-settings'),  # ← ADD THIS

# Add to urlpatterns:
    path('holiday/earned-leaves/', views.earned_leaves_config, name='earned-leaves'),
    path('holiday/earned-leave/<int:leave_id>/edit/', views.edit_earned_leave, name='edit-earned-leave'),
    path('api/earned-leaves/', views.api_earned_leaves, name='api-earned-leaves'),
    path('holiday/half-day/add/', views.add_half_day_scenario, name='add-half-day-scenario'),
    path('holiday/half-day/<int:scenario_id>/edit/', views.edit_half_day_scenario, name='edit-half-day-scenario'),
    path('holiday/half-day/<int:scenario_id>/delete/', views.delete_half_day_scenario, name='delete-half-day-scenario'),
    path('holiday/api/half-day/<int:scenario_id>/', views.api_get_half_day_scenario, name='api-get-half-day-scenario'),

    # Holiday Type management
    path('holiday/type/add/', views.create_holiday_type, name='holiday-type-add'),
    path('holiday/type/<int:type_id>/edit/', views.edit_holiday_type, name='holiday-type-edit'),
    path('holiday/type/<int:type_id>/delete/', views.delete_holiday_type, name='holiday-type-delete'),

    # API Endpoints
    path('api/holiday/<int:holiday_id>/', views.api_get_holiday, name='api-holiday'),
    path('api/holiday-type/<int:type_id>/', views.api_get_holiday_type, name='api-holiday-type'),
    path('api/holidays/', views.api_holidays_json, name='api-holidays'),
    path('api/earned-leaves/', views.api_earned_leaves_json, name='api-earned-leaves'),

]
