
from django.urls import path

from website import views

urlpatterns = [    
    # path('',views.test,name="test"),
    path("", views.admin_dashboard, name="admin-dashboard"),

    path('home',views.home,name="home"),
    path('create-employee',views.create_employee,name="create-employee"),
    path('employee/<int:pk>/', views.employee_detail, name='employee_detail'),
    path('create-offboarding',views.create_offboarding,name="create-offboarding"),
    path('delete-offboarding/<int:pk>/', views.delete_offboarding, name='delete-offboarding'),
    # path('create-branch',views.create_branch,name="create-branch"),
    path('create-branch',views.create_branchs,name="create-branch"),
    path('create-company/',views.create_company,name="create-company"),
    path("company/<int:company_id>/edit/", views.edit_company, name="edit_company"),
    path("company/<int:company_id>/get/", views.get_company, name="get_company"),

    path("company/delete/<int:company_id>/", views.delete_company, name="delete_company"),







    path("company/<int:pk>/details/", views.company_details_api, name="company_details_api"),









    path('create-salary',views.create_salary,name="create-salary"),
    path("salary/details/<int:pk>/", views.salary_details, name="salary_details"),
    path("download-employees/", views.download_employees_excel, name="download_employees"),
    path("download-leave/", views.download_leave_excel, name="download_leave"),
    path("upload-attendance/", views.upload_attendance_excel, name="upload_attendance"),
    path("attendance/", views.attendance_list, name="attendance"),
    path("attendance/<int:employee_id>/", views.employee_attendance_detail, name="employee_attendance_detail"),
    path("submit-correction-request/", views.submit_correction_request, name="submit_correction_request"),
    path("approve-correction/<int:request_id>/", views.approve_correction_request, name="approve_correction"),
    path("reject-correction/<int:request_id>/", views.reject_correction_request, name="reject_correction"),  
    # employee advances
    path('advances/', views.advances_list, name='advances-list'),
    path('advances/create/', views.create_advance, name='create-advance'),
    path('advances/<int:advance_id>/add-installment/', views.add_installment, name='add-installment'),
    path('advances/<int:advance_id>/installments/', views.view_installments, name='view-installments'),
    path('advances/mark-paid/<int:installment_id>/', views.mark_paid, name='mark-paid'),
    path('advances/undo-paid/<int:installment_id>/', views.undo_paid, name='undo-paid'),
    path('advances/skip/<int:installment_id>/', views.skip_installment, name='skip-installment'),  # ✅ NEW

    path("leave-balance/", views.leave_balance_view, name="leave_balance"),
    path("employees/<int:employee_id>/compoffs/", views.employee_compoff_details, name="employee-compoff-details"),
    path("employees/<int:employee_id>/leave-history/", views.employee_leave_history, name="employee_leave_history"),
    path('approve-compoff/<int:compoff_id>/', views.approve_compoff, name='approve_compoff'),
    path('reject-compoff/<int:compoff_id>/', views.reject_compoff, name='reject_compoff'),
    path("submit-comp-off-request/", views.submit_comp_off_request, name="submit_comp_off_request"),
    path("salary-increment/", views.create_salary_increment, name="salary_increment"),
    path("salary-history/", views.salary_history, name="salary_history"),
    path("salary/increment/details/<int:pk>/", views.increment_details, name="increment_details"),

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
    path("leave-credit-policy/update/", views.update_leave_credit_policy, name="update_leave_credit_policy"),
    path("recalculate-leaves/", views.recalculate_leave_balances, name="recalculate_leave_balances"),

]

