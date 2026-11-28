# HRMS transformation inventory and roadmap

## Discovery baseline

The project mounts website.urls at the root and Django administration at /admin/. Static and media routes are appended by the project URL configuration in development. This inventory covers source declarations. A literal template reference may be a fragment or an email. Delegated views can resolve templates indirectly. Decorators are entry checks only. Additional company, ownership and reporting-line checks occur inside views and services.

## Application routes

| Name | Path | Handler | Direct template references | Entry decorators |
|---|---|---|---|---|
| admin-dashboard | `/` | views.admin_dashboard | d/f.html | login_required(login_url='login'), feature_required('admin_dashboard', action='view') |
| home | `/home` | views.home | base2.html | login_required |
| employee_list | `/employees/` | views.employee_list | employee/create_employee2.html | login_required, feature_required('employee_records', action='view') |
| my_profile | `/my-profile/` | views.my_profile |  | login_required |
| my_attendance | `/my-attendance/` | views.my_attendance |  | login_required |
| employee-dashboard | `/my-dashboard/` | views.employee_dashboard | employee/employee_dashboard.html | login_required |
| bulk-employee-action | `/employees/bulk-action/` | views.bulk_employee_action |  | login_required, feature_required('employee_records', action='edit'), require_http_methods(['POST']) |
| employee_create | `/employee/` | views.create_or_edit_employee | employee/create_employee2.html | login_required, create_or_edit_required('employee_records', resolve_action=lambda request, *a, **kw: 'edit' if kw.get('employee_id') or a else 'create') |
| employee_edit | `/employee/<int:employee_id>/` | views.create_or_edit_employee | employee/create_employee2.html | login_required, create_or_edit_required('employee_records', resolve_action=lambda request, *a, **kw: 'edit' if kw.get('employee_id') or a else 'create') |
| employee_detail | `/employee-detail/<int:pk>/` | views.employee_detail | employee/employee_detail.html | login_required |
| employee_change_requests | `/employee-changes/` | views.employee_change_requests | employee/change_requests.html | login_required, feature_required('employee_records', action='view') |
| employee_change_requests_bulk | `/employee-changes/bulk/` | views.employee_change_requests_bulk |  | login_required, feature_required('employee_records', action='view'), require_http_methods(['POST']) |
| employee_change_request_detail | `/employee-changes/<int:pk>/` | views.employee_change_request_detail | employee/change_request_detail.html | login_required, feature_required('employee_records', action='view') |
| download_attachment | `/attachments/<int:pk>/download/` | views.download_attachment |  | login_required |
| download_previous_attachment | `/previous-employment-documents/<int:pk>/download/` | views.download_previous_attachment |  | login_required |
| download-offboarding-document | `/offboarding/<int:off_id>/document/<str:field>/` | views.download_offboarding_document |  | login_required, feature_required('offboarding', action='view') |
| download-asset-document | `/offboarding/asset/<int:asset_id>/document/<str:field>/` | views.download_asset_document |  | login_required, feature_required('offboarding', action='view') |
| download-change-request-file | `/employee-changes/file/<int:pk>/download/` | views.download_change_request_file |  | login_required |
| offboarding-list | `/offboarding/` | views.offboarding_list | employee/offboarding2.html | login_required, create_or_edit_required('offboarding', resolve_action=lambda request, *a, **kw: 'view' if request.method != 'POST' else 'edit' if request.POST.get('offboarding_id') else 'create') |
| offboarding-export-excel | `/offboarding/export-excel/` | views.offboarding_export_excel |  | login_required, feature_required('offboarding', action='view') |
| offboarding-detail | `/offboarding/<int:off_id>/details/` | views.offboarding_detail |  | login_required, feature_required('offboarding', action='view') |
| offboarding-edit-data | `/offboarding/<int:id>/edit-data/` | views.offboarding_edit_data |  | login_required, feature_required('offboarding', action='view') |
| offboarding-delete | `/delete-offboarding/<int:pk>/` | views.offboarding_delete |  | login_required, feature_required('offboarding', action='edit'), feature_required('archive_records', action='edit') |
| create-branch | `/create-branch` | views.create_branchs | branch/create-branch.html | login_required, feature_required('branch_management', action='edit') |
| branch-export-excel | `/branch/export-excel/` | views.branch_export_excel |  | login_required, feature_required('branch_management', action='view') |
| create-company | `/create-company/` | views.create_company | company/home2.html | login_required, feature_required('company_management', action='view') |
| company-export-excel | `/company/export-excel/` | views.company_export_excel |  | login_required, feature_required('company_management', action='view') |
| edit_company | `/company/<int:company_id>/edit/` | views.edit_company | company/_edit_company_form.html | login_required, feature_required('company_management', action='edit') |
| get_company | `/company/<int:company_id>/get/` | views.get_company |  | login_required, feature_required('company_management', action='view') |
| delete_company | `/company/delete/<int:company_id>/` | views.delete_company |  | login_required, feature_required('company_management', action='edit'), feature_required('archive_records', action='edit') |
| delete_employee | `/employee/delete/<int:employee_id>/` | views.delete_employee |  | login_required, feature_required('employee_delete', action='edit'), feature_required('archive_records', action='edit') |
| company_details_api | `/company/<int:pk>/details/` | views.company_details_api |  | login_required, feature_required('company_management', action='view') |
| branch_details_api | `/branch/<int:pk>/details/` | views.branch_details_api |  | login_required, feature_required('branch_management', action='view') |
| edit_branch | `/branch/<int:branch_id>/edit/` | views.edit_branch | branch/_edit_branch_form.html | login_required, feature_required('branch_management', action='edit') |
| get_branch | `/branch/<int:branch_id>/get/` | views.get_branch |  | login_required, feature_required('branch_management', action='view') |
| delete_branch | `/branch/delete/<int:branch_id>/` | views.delete_branch |  | login_required, feature_required('branch_management', action='edit'), feature_required('archive_records', action='edit') |
| upload-company-excel | `/upload-company/` | views.upload_company_excel |  | login_required, feature_required('company_management', action='edit'), require_http_methods(['POST']) |
| download-company-upload-template | `/company/upload-template/` | views.download_company_upload_template |  | login_required, feature_required('company_management', action='edit') |
| upload-branch-excel | `/upload-branch/` | views.upload_branch_excel |  | login_required, feature_required('branch_management', action='edit'), require_http_methods(['POST']) |
| download-branch-upload-template | `/branch/upload-template/` | views.download_branch_upload_template |  | login_required, feature_required('branch_management', action='edit') |
| login | `/login/` | views.login_view | auth/login.html |  |
| create-user | `/create-user/` | views.create_user_view | auth/create_user.html | login_required, feature_required('user_accounts', action='edit') |
| logout | `/logout/` | views.logout_view |  |  |
| change-password | `/change-password/` | views.change_password | auth/change_password.html | login_required |
| password-reset | `/forgot-password/` | views_password_reset.PasswordResetView.as_view() | auth/password_reset_email.txt, auth/password_reset_form.html, auth/password_reset_subject.txt |  |
| password-reset-done | `/forgot-password/sent/` | views_password_reset.PasswordResetDoneView.as_view() | auth/password_reset_done.html |  |
| password_reset_confirm | `/reset/<uidb64>/<token>/` | views_password_reset.PasswordResetConfirmView.as_view() | auth/password_reset_confirm.html |  |
| password-reset-complete | `/reset/done/` | views_password_reset.PasswordResetCompleteView.as_view() | auth/password_reset_complete.html |  |
| create-salary | `/create-salary` | views.create_salary | salary/create_salary4.html | login_required, create_or_edit_required('salary_structure', resolve_action=lambda request, *a, **kw: 'edit' if request.method == 'POST' and request.POST.get('salary_id') else 'create') |
| salary-master-export-excel | `/salary/export-excel/` | views.salary_master_export_excel |  | login_required, feature_required('salary_structure', action='view') |
| salary_details | `/salary/details/<int:pk>/` | views.salary_details |  | login_required, feature_required('salary_structure', action='view') |
| download_employees | `/download-employees/` | views.download_employees_excel |  | login_required, feature_required('employee_records', action='view') |
| download_leave | `/download-leave/` | views.download_leave_excel |  | login_required, feature_required('leave_management', action='view') |
| upload_attendance | `/upload-attendance/` | views.upload_attendance_excel | attendance/attendance_upload.html | login_required, feature_required('attendance_data', action='edit') |
| upload_attendance_init | `/upload-attendance/init/` | views.upload_attendance_init |  | login_required, feature_required('attendance_data', action='edit'), require_http_methods(['POST']) |
| upload_attendance_chunk | `/upload-attendance/<int:upload_id>/chunk/` | views.upload_attendance_chunk |  | login_required, feature_required('attendance_data', action='edit'), require_http_methods(['POST']) |
| attendance_upload_progress | `/attendance-progress/<int:upload_id>/` | views.attendance_upload_progress |  | login_required |
| recalculate_attendance_init | `/recalculate-attendance/init/` | views.recalculate_attendance_init |  | login_required, feature_required('attendance_data', action='edit'), require_http_methods(['POST']) |
| recalculate_attendance_chunk | `/recalculate-attendance/chunk/` | views.recalculate_attendance_chunk |  | login_required, feature_required('attendance_data', action='edit'), require_http_methods(['POST']) |
| late_attendance_review | `/attendance/late-review/` | views.late_attendance_review | attendance/late_attendance_review.html | login_required, feature_required('attendance_review', action='edit') |
| override_attendance_status | `/attendance/override-status/` | views.override_attendance_status |  | login_required, _attendance_day_editors_only, require_http_methods(['POST']) |
| bulk_override_attendance_status | `/attendance/bulk-override-status/` | views.bulk_override_attendance_status |  | login_required, _attendance_day_editors_only, require_http_methods(['POST']) |
| attendance-register | `/attendance/register/` | views.attendance_register_view | attendance/attendance_register.html | login_required, feature_required('attendance_register', action='view') |
| attendance-register-export | `/attendance/register/export/` | views.attendance_register_export_excel |  | login_required, feature_required('attendance_register', action='view') |
| shift_roster_list | `/attendance/shift-roster/` | views.shift_roster_list | attendance/shift_roster.html | login_required, feature_required('shift_roster', action='view') |
| add_shift_assignment | `/attendance/shift-roster/add/` | views.add_shift_assignment |  | login_required, feature_required('shift_roster', action='edit'), require_http_methods(['POST']) |
| edit_shift_assignment | `/attendance/shift-roster/<int:pk>/edit/` | views.edit_shift_assignment |  | login_required, feature_required('shift_roster', action='edit'), require_http_methods(['POST']) |
| delete_shift_assignment | `/attendance/shift-roster/<int:pk>/delete/` | views.delete_shift_assignment |  | login_required, feature_required('shift_roster', action='edit'), require_http_methods(['POST']), feature_required('archive_records', action='edit') |
| api_get_shift_assignment | `/api/shift-roster/<int:pk>/` | views.api_get_shift_assignment |  | login_required, feature_required('shift_roster', action='view') |
| attendance | `/attendance/` | views.attendance_list | attendance/today.html | login_required, feature_required('attendance_review', action='view') |
| attendance_export | `/attendance/export/` | views.attendance_list_export |  | login_required, feature_required('attendance_review', action='view') |
| employee_attendance_detail | `/attendance/<int:employee_id>/` | views.employee_attendance_detail | attendance/employee_attendance_detail.html | login_required |
| employee_attendance_export | `/attendance/<int:employee_id>/export/` | views.employee_attendance_export |  | login_required |
| employee_search | `/ajax/employees/search/` | views.employee_search |  | login_required |
| submit_correction_request | `/submit-correction-request/` | views.submit_correction_request |  | login_required |
| approve_correction | `/approve-correction/<int:request_id>/` | views.approve_correction_request |  | login_required, approval_required('attendance_corrections'), require_http_methods(['POST']) |
| reject_correction | `/reject-correction/<int:request_id>/` | views.reject_correction_request |  | login_required, approval_required('attendance_corrections') |
| bulk_approve_correction | `/bulk-approve-correction/` | views.bulk_approve_correction |  | login_required, approval_required('attendance_corrections'), require_http_methods(['POST']) |
| leave_balance | `/leave-balance/` | views.leave_balance_view | leave_balance/leave_balance_report.html | login_required |
| employee-compoff-details | `/employees/<int:employee_id>/compoffs/` | views.employee_compoff_details | leave_balance/_compoff_modal_table.html | login_required |
| employee_leave_history | `/employees/<int:employee_id>/leave-history/` | views.employee_leave_history | leave_balance/_leave_history_table.html | login_required |
| approve_compoff | `/approve-compoff/<int:compoff_id>/` | views.approve_compoff |  | login_required, approval_required('comp_off') |
| reject_compoff | `/reject-compoff/<int:compoff_id>/` | views.reject_compoff |  | login_required, approval_required('comp_off') |
| bulk_approve_compoff | `/bulk-approve-compoff/` | views.bulk_approve_compoff |  | login_required, approval_required('comp_off'), require_http_methods(['POST']) |
| submit_comp_off_request | `/submit-comp-off-request/` | views.submit_comp_off_request |  | login_required |
| import-compoff | `/import-compoff/` | views.import_compoff_excel |  | login_required, feature_required('comp_off', action='create') |
| compoff-import-template | `/import-compoff/template/` | views.download_compoff_import_template |  | login_required, feature_required('comp_off', action='create') |
| salary_increment | `/salary-increment/` | views.create_salary_increment | salary_increment/create_increment.html | login_required, feature_required('salary_structure', action='edit') |
| salary-increment-export-excel | `/salary-increment/export-excel/` | views.salary_increment_export_excel |  | login_required, feature_required('salary_structure', action='view') |
| edit_increment | `/salary/increment/edit/<int:pk>/` | views.edit_increment |  | login_required, feature_required('salary_structure', action='edit') |
| update_increment | `/salary/increment/update/<int:pk>/` | views.update_salary_increment |  | login_required, feature_required('salary_structure', action='edit') |
| delete_increment | `/salary/increment/delete/<int:pk>/` | views.delete_salary_increment |  | login_required, feature_required('salary_structure', action='edit'), feature_required('archive_records', action='edit') |
| increment_details | `/salary/increment/details/<int:pk>/` | views.increment_details |  | login_required, feature_required('salary_structure', action='view') |
| salary_history | `/salary-history/` | views.salary_history | salary_increment/salary_history_list.html | login_required, feature_required('salary_structure', action='view') |
| employee_details_ajax | `/ajax/employee-details/` | views.employee_salary_ajax |  | login_required |
| salary_history_detail | `/salary-history/detail/<int:pk>/` | views.salary_history_detail | partials/salary_history_detail.html | login_required, feature_required('salary_structure', action='view') |
| salary_compare | `/salary-history/compare/<int:history_id>/<int:employee_id>/` | views.salary_compare | partials/salary_compare.html | login_required, feature_required('salary_structure', action='view') |
| salary_timeline_data | `/salary-history/chart-data/<int:employee_id>/` | views.salary_timeline_data |  | login_required |
| salary_history_export_excel | `/salary-history/export/excel/` | views.salary_history_export_excel |  | login_required, feature_required('salary_structure', action='view') |
| get_payroll_settings | `/payroll-settings/` | views.get_payroll_settings |  | login_required |
| settings-page | `/settings/` | views.settings_page | settings/no_company.html, settings/settings_page.html | login_required, feature_required('company_settings', action='view') |
| save-payroll-settings | `/settings/save/payroll/` | views.save_payroll_settings |  | login_required, require_http_methods(['POST']), feature_required('company_settings', action='edit') |
| save-leave-settings | `/settings/save/leave/` | views.save_leave_settings |  | login_required, require_http_methods(['POST']), feature_required('company_settings', action='edit') |
| save-leave-credit-policy | `/settings/save/credit-policy/` | views.save_leave_credit_policy |  | login_required, require_http_methods(['POST']), feature_required('company_settings', action='edit') |
| company-settings-hub | `/settings/hub/` | views.company_settings_hub | settings/company_settings_hub.html | login_required, feature_required('company_settings', action='view') |
| roles-permissions-hub | `/settings/roles-permissions/` | views.roles_permissions_hub | settings/roles_permissions_hub.html | login_required, group_required('Super Admin', 'Admin') |
| create-role | `/settings/roles-permissions/create-role/` | views.create_role |  | login_required, group_required('Super Admin', 'Admin'), require_http_methods(['POST']) |
| rename-role | `/settings/roles-permissions/<int:role_id>/rename/` | views.rename_role |  | login_required, group_required('Super Admin', 'Admin'), require_http_methods(['POST']) |
| delete-role | `/settings/roles-permissions/<int:role_id>/delete/` | views.delete_role |  | login_required, group_required('Super Admin', 'Admin'), require_http_methods(['POST']) |
| save-role-permissions | `/settings/roles-permissions/save/` | views.save_role_permissions |  | login_required, group_required('Super Admin', 'Admin'), require_http_methods(['POST']) |
| reassign-user-role | `/settings/roles-permissions/reassign-user/` | views.reassign_user_role |  | login_required, group_required('Super Admin', 'Admin'), require_http_methods(['POST']) |
| broadcast-settings | `/settings/hub/broadcast/` | views.broadcast_settings_to_all_companies |  | login_required, feature_required('company_settings_broadcast', action='edit'), require_http_methods(['POST']) |
| announcements-hub | `/announcements/` | views.announcements_hub | announcements/hub.html | login_required, feature_required('announcements', action='view') |
| save-announcement | `/announcements/save/` | views.save_announcement |  | login_required, feature_required('announcements', action='edit'), require_http_methods(['POST']) |
| delete-announcement | `/announcements/<int:pk>/delete/` | views.delete_announcement |  | login_required, feature_required('announcements', action='edit'), require_http_methods(['POST']), feature_required('archive_records', action='edit') |
| announcements-api | `/announcements/api/` | views.announcements_api |  | login_required |
| mark-announcement-read | `/announcements/mark-read/` | views.mark_announcement_read |  | login_required, require_http_methods(['POST']) |
| audit-log | `/audit-log/` | views.audit_log_view | audit/audit_log.html | login_required, feature_required('audit_log', action='view') |
| restore-record | `/restore/<str:model_type>/<int:pk>/` | views.restore_record |  | login_required, require_http_methods(['POST']) |
| leave_credit_policy | `/leave-credit-policy/` | views.leave_credit_policy_view | leave_policy/leave_credit_policy.html | login_required, feature_required('leave_management', action='edit') |
| leave_apply | `/leave-apply/` | views.leave_apply_view | leave_balance/leave_apply.html | login_required |
| approve_leave | `/approve-leave/<int:leave_id>/` | views.approve_leave |  | login_required, approval_required('leave_management'), require_POST |
| reject_leave | `/reject-leave/<int:leave_id>/` | views.reject_leave |  | login_required, approval_required('leave_management'), require_POST |
| bulk_approve_leave | `/bulk-approve-leave/` | views.bulk_approve_leave |  | login_required, approval_required('leave_management'), require_POST |
| update_leave_credit_policy | `/leave-credit-policy/update/` | views.update_leave_credit_policy |  | login_required, feature_required('leave_management', action='edit') |
| attendance_correction_requests_list | `/attendance-correction-requests/` | views.attendance_correction_requests_list | attendance/attendance_request_status.html | login_required |
| branch_details_api | `/branch/<int:pk>/details/` | views.branch_details_api |  | login_required, feature_required('branch_management', action='view') |
| attendance_correction_detail | `/attendance-correction/<int:pk>/details/` | views.attendance_correction_detail |  | login_required |
| comp_off_requests_list | `/comp-off-requests/` | views.comp_off_requests_list | attendance/comp_off_request.html | login_required |
| comp_off_requests | `/comp-off/<int:pk>/month/` | views.comp_off_requests | attendance/comp_off_request_table.html | login_required |
| advances-list | `/advances/` | views.advance_list | advances/advance_list.html | login_required |
| create-advance | `/advances/create/` | views.advance_create | advances/advance_create.html | login_required, feature_required('advances', action='edit') |
| advance-detail | `/advances/<int:pk>/` | views.advance_detail | advances/advance_detail.html | login_required |
| advance-edit | `/advances/<int:pk>/edit/` | views.advance_edit | advances/advance_edit.html | login_required |
| advance-delete | `/advances/<int:pk>/delete/` | views.advance_delete |  | login_required, require_POST |
| advances-pay | `/advances/<int:pk>/pay/` | views.pay_advance |  | login_required, feature_required('advances', action='edit'), require_POST, transaction.atomic |
| advances-skip | `/advances/<int:pk>/skip/` | views.skip_advance_month |  | login_required, feature_required('advances', action='edit'), require_POST, transaction.atomic |
| revert-skip | `/advances/<int:pk>/revert-skip/` | views.revert_skip_view |  | login_required, feature_required('advances', action='edit'), require_POST |
| payroll-run-list | `/payroll/` | views.payroll_run_list | payroll/run_list.html | login_required, feature_required('payroll', action='view') |
| payroll-run-create | `/payroll/run/create/` | views.payroll_run_create | payroll/run_create.html | login_required, feature_required('payroll', action='edit') |
| payroll-period-preview | `/payroll/run/period-preview/` | views.payroll_period_preview |  | login_required, feature_required('payroll', action='view') |
| payroll-run-detail | `/payroll/run/<int:run_id>/` | views.payroll_run_detail | payroll/run_detail.html | login_required, feature_required('payroll', action='view') |
| payroll-record-update | `/payroll/record/<int:record_id>/update/` | views.payroll_record_update |  | login_required, feature_required('payroll', action='edit'), require_POST |
| salary-slip | `/payroll/record/<int:record_id>/salary-slip/` | views.salary_slip_view | payroll/salary_slip.html | login_required |
| salary-slips | `/salary-slips/` | views.salary_slips_list | payroll/salary_slips_list.html | login_required |
| salary-slip-statement | `/salary-slips/statement/` | views.salary_slip_statement | payroll/salary_statement.html | login_required |
| payroll-run-recalculate | `/payroll/run/<int:run_id>/recalculate/` | views.payroll_run_recalculate |  | login_required, feature_required('payroll', action='edit'), require_POST |
| payroll-run-finalize | `/payroll/run/<int:run_id>/finalize/` | views.payroll_run_finalize |  | login_required, feature_required('payroll', action='edit'), require_POST |
| payroll-export-excel | `/payroll/<int:run_id>/export/excel/` | views.payroll_export_excel |  | login_required, feature_required('payroll', action='view') |
| payroll-export-pdf | `/payroll/<int:run_id>/export/pdf/` | views.payroll_export_pdf | payroll/payroll_pdf_template.html | login_required, feature_required('payroll', action='view') |
| download-empty-excel | `/download-empty-excel/` | views.download_empty_excel |  | login_required |
| import-employees-init | `/import-employees/init/` | views.import_employees_init |  | login_required, feature_required('employee_records', action='edit'), require_http_methods(['POST']) |
| import-employees-chunk | `/import-employees/<int:upload_id>/chunk/` | views.import_employees_chunk |  | login_required, feature_required('employee_records', action='edit'), require_http_methods(['POST']) |
| employee-import-template | `/import-employees/template/` | views.download_employee_import_template |  | login_required, feature_required('employee_records', action='view') |
| import-salary | `/import-salary/` | views.import_salary_excel |  | login_required, feature_required('salary_structure', action='edit') |
| salary-import-template | `/import-salary/template/` | views.download_salary_import_template |  | login_required, feature_required('salary_structure', action='view') |
| leave_balance_report | `/leave-balance/` | views.leave_balance_view | leave_balance/leave_balance_report.html | login_required |
| recalculate_leave_balances | `/leave-balance/recalculate/` | views.recalculate_leave_balances_view |  | login_required |
| recalc-employee-leave | `/leave-balance/employee/<int:employee_id>/recalc/` | views.recalc_employee_leave_balance |  | login_required |
| my-approvals | `/my-approvals/` | views.my_approvals | approvals/my_approvals.html | login_required |
| department-list | `/departments/` | views.department_list | department/department_list.html | login_required, feature_required('department_management', action='view') |
| department-create | `/departments/save/` | views.save_department |  | login_required, feature_required('department_management', action='edit'), require_http_methods(['POST']) |
| department-edit | `/departments/<int:department_id>/save/` | views.save_department |  | login_required, feature_required('department_management', action='edit'), require_http_methods(['POST']) |
| department-delete | `/departments/<int:department_id>/delete/` | views.delete_department |  | login_required, feature_required('department_management', action='edit'), require_http_methods(['POST']), feature_required('archive_records', action='edit') |
| department-defaults | `/departments/defaults/` | views.department_defaults_api |  | login_required |
| override-lwp | `/leave-balance/override-lwp/` | views.override_lwp_view |  | login_required, feature_required('leave_management', action='edit'), require_http_methods(['POST']) |
| override-compoff | `/leave-balance/override-compoff/` | views.override_compoff_view |  | login_required, feature_required('leave_management', action='edit'), require_http_methods(['POST']) |
| holiday-calendar | `/holiday/dashboard/` | views.holiday_calendar_dashboard | holiday_calendar/dashboard.html | login_required, require_http_methods(['GET']) |
| holiday-dashboard | `/holiday/` | views.holiday_calendar_dashboard | holiday_calendar/dashboard.html | login_required, require_http_methods(['GET']) |
| add-holiday | `/holiday/add/` | views.add_holiday |  | login_required, feature_required('holiday_calendar', action='edit'), require_http_methods(['GET', 'POST']) |
| edit-holiday | `/holiday/<int:holiday_id>/edit/` | views.edit_holiday |  | login_required, feature_required('holiday_calendar', action='edit'), require_http_methods(['GET', 'POST']) |
| delete-holiday | `/holiday/<int:holiday_id>/delete/` | views.delete_holiday |  | login_required, feature_required('holiday_calendar', action='edit'), require_http_methods(['POST']), feature_required('archive_records', action='edit') |
| holiday-list | `/holiday/list/` | views.holiday_list |  | login_required, require_http_methods(['GET']) |
| save-holiday-settings | `/holiday/settings/save/` | views.save_holiday_settings |  | login_required, feature_required('holiday_calendar', action='edit'), require_http_methods(['POST']) |
| earned-leaves | `/holiday/earned-leaves/` | views.earned_leaves_config | holiday_calendar/dashboard.html | login_required, require_http_methods(['GET']) |
| edit-earned-leave | `/holiday/earned-leave/<int:leave_id>/edit/` | views.edit_earned_leave |  | login_required, feature_required('holiday_calendar', action='edit'), require_http_methods(['POST']) |
| api-earned-leaves | `/api/earned-leaves/` | views.api_earned_leaves |  | login_required, require_http_methods(['GET']) |
| add-half-day-scenario | `/holiday/half-day/add/` | views.add_half_day_scenario |  | login_required, feature_required('holiday_calendar', action='edit'), require_http_methods(['GET', 'POST']) |
| edit-half-day-scenario | `/holiday/half-day/<int:scenario_id>/edit/` | views.edit_half_day_scenario |  | login_required, feature_required('holiday_calendar', action='edit'), require_http_methods(['POST']) |
| delete-half-day-scenario | `/holiday/half-day/<int:scenario_id>/delete/` | views.delete_half_day_scenario |  | login_required, feature_required('holiday_calendar', action='edit'), require_http_methods(['POST']), feature_required('archive_records', action='edit') |
| api-get-half-day-scenario | `/holiday/api/half-day/<int:scenario_id>/` | views.api_get_half_day_scenario |  | login_required, require_http_methods(['GET']) |
| holiday-type-add | `/holiday/type/add/` | views.create_holiday_type |  | login_required, feature_required('holiday_calendar', action='edit'), require_POST |
| holiday-type-edit | `/holiday/type/<int:type_id>/edit/` | views.edit_holiday_type |  | login_required, feature_required('holiday_calendar', action='edit'), require_POST |
| holiday-type-delete | `/holiday/type/<int:type_id>/delete/` | views.delete_holiday_type |  | login_required, feature_required('holiday_calendar', action='edit'), require_POST, feature_required('archive_records', action='edit') |
| api-holiday | `/api/holiday/<int:holiday_id>/` | views.api_get_holiday |  | login_required, require_http_methods(['GET']) |
| api-holiday-type | `/api/holiday-type/<int:type_id>/` | views.api_get_holiday_type |  | login_required |
| api-holidays | `/api/holidays/` | views.api_holidays_json |  | login_required, require_http_methods(['GET']) |
| api-earned-leaves | `/api/earned-leaves/` | views.api_earned_leaves_json |  | login_required, require_http_methods(['GET']) |
| biometric-punches-api | `/api/biometric/punches/` | views_biometric.biometric_punches_api |  | csrf_exempt, require_POST |
| biometric-status-api | `/api/biometric/status/` | views_biometric.biometric_status_api |  | csrf_exempt, require_GET |
| biometric-sync | `/attendance/biometric-sync/` | views_biometric.biometric_sync_dashboard | attendance/biometric_sync.html | login_required, feature_required('attendance_data', 'edit') |
| biometric-sync-rebuild | `/attendance/biometric-sync/rebuild/` | views_biometric.biometric_resync |  | login_required, feature_required('attendance_data', 'edit'), require_POST |
| field-duty | `/field-duty/` | views_field_duty.field_duty_home | field_duty/home.html | login_required |
| field-duty-start | `/field-duty/start/` | views_field_duty.field_duty_start |  | login_required, require_POST |
| field-duty-end | `/field-duty/end/` | views_field_duty.field_duty_end |  | login_required, require_POST |
| field-duty-log | `/field-duty/log/` | views_field_duty.field_duty_log | field_duty/log.html | login_required |
| field-duty-detail | `/field-duty/<int:pk>/details/` | views_field_duty.field_duty_detail | field_duty/_detail.html | login_required |
| field-duty-upload-report | `/field-duty/<int:pk>/report/upload/` | views_field_duty.field_duty_upload_report |  | login_required, require_POST |
| field-duty-report | `/field-duty/<int:pk>/report/` | views_field_duty.field_duty_report |  | login_required |
| field-duty-selfie | `/field-duty/<int:pk>/selfie/<str:side>/` | views_field_duty.field_duty_selfie |  | login_required |

## Template coverage

| Template | Shell or includes | Components and conversion dependencies found in markup | Status |
|---|---|---|---|
| 404.html |  | inline CSS | Not Started |
| advances/advance_create.html | base2.html | forms, inline JS, inline CSS | Not Started |
| advances/advance_detail.html | base2.html | forms, table, modal, AJAX, inline JS, inline CSS, Bootstrap controls | Not Started |
| advances/advance_edit.html | base2.html | forms | Not Started |
| advances/advance_list.html | base2.html | forms, table, inline JS, inline CSS | Not Started |
| announcements/_banner.html |  | AJAX, inline JS, Bootstrap controls | Not Started |
| announcements/hub.html | base2.html | forms, AJAX, inline JS, inline CSS, SweetAlert | Not Started |
| approvals/_pending_queues.html |  | table, AJAX, inline JS, inline CSS | Not Started |
| approvals/my_approvals.html | base2.html, approvals/_pending_queues.html |  | Not Started |
| attendance/attendance_register.html | base2.html | forms, table, AJAX, inline JS, inline CSS, pagination | In Progress |
| attendance/attendance_request_status.html | base2.html | forms, table, modal, AJAX, inline JS, inline CSS, DataTables, Bootstrap controls | In Progress |
| attendance/attendance_upload.html | base2.html | forms, AJAX, inline JS, inline CSS, upload | In Progress |
| attendance/biometric_sync.html | base2.html | forms, table, Bootstrap controls, messages | In Progress |
| attendance/comp_off_request.html | base2.html | forms, table, modal, AJAX, inline JS, inline CSS, DataTables, Bootstrap controls, upload | In Progress |
| attendance/comp_off_request_table.html |  | table, modal, inline CSS, Bootstrap controls | Not Started |
| attendance/employee_attendance_detail.html | base2.html | forms, table, modal, AJAX, inline JS, inline CSS, Bootstrap controls, pagination, upload | In Progress |
| attendance/late_attendance_review.html | base2.html | forms, table, AJAX, inline JS, inline CSS, pagination | In Progress |
| attendance/shift_roster.html | base2.html | forms, table, modal, AJAX, inline JS, inline CSS, Bootstrap controls, pagination | In Progress |
| attendance/today.html | base2.html | forms, table, modal, AJAX, inline JS, inline CSS, DataTables, Bootstrap controls, upload | In Progress |
| audit/audit_log.html | base2.html | forms, table, inline CSS, pagination | Not Started |
| auth/_auth_shell.html |  | inline CSS | Not Started |
| auth/_password_rules.html |  |  | Not Started |
| auth/change_password.html | auth/_password_rules.html | forms, inline JS, inline CSS, messages | Not Started |
| auth/create_user.html |  | forms | Not Started |
| auth/login.html |  | forms, inline JS, inline CSS, messages | Not Started |
| auth/password_reset_complete.html | auth/_auth_shell.html |  | Not Started |
| auth/password_reset_confirm.html | auth/_auth_shell.html, auth/_password_rules.html | forms, inline JS | Not Started |
| auth/password_reset_done.html | auth/_auth_shell.html |  | Not Started |
| auth/password_reset_email.txt |  |  | Not Started |
| auth/password_reset_form.html | auth/_auth_shell.html | forms | Not Started |
| auth/password_reset_subject.txt |  |  | Not Started |
| base2.html |  | AJAX, inline JS, inline CSS, Select2, DataTables, Bootstrap controls, chart, SweetAlert, messages | Not Started |
| branch/_edit_branch_form.html |  | forms | Not Started |
| branch/create-branch.html | base2.html, Modal/branch/branch_create.html | forms, table, modal, AJAX, inline JS, inline CSS, DataTables, Bootstrap controls, SweetAlert | Not Started |
| company/_edit_company_form.html |  | forms, inline CSS, upload | Not Started |
| company/home2.html | base2.html | forms, table, modal, AJAX, inline JS, inline CSS, DataTables, Bootstrap controls, SweetAlert, upload | Not Started |
| d/f.html | base2.html, announcements/_banner.html, employee/_onboarding_bar.html, employee/_birthdays_card.html | forms, table, modal, AJAX, inline JS, inline CSS, Bootstrap controls, SweetAlert, upload | Not Started |
| department/department_list.html | base2.html | forms, table, modal, inline JS, Bootstrap controls | Not Started |
| employee/_birthdays_card.html |  | inline CSS | Not Started |
| employee/_onboarding_bar.html |  | inline CSS | Not Started |
| employee/_reporting_line.html | employee/_reporting_person_tile.html, employee/_reporting_person_tile.html, employee/_reporting_person_tile.html |  | Not Started |
| employee/_reporting_person_tile.html |  | inline CSS | Not Started |
| employee/change_request_detail.html | base2.html | forms, table, inline CSS | Not Started |
| employee/change_requests.html | base2.html | forms, table, inline JS, inline CSS | Not Started |
| employee/create_employee2.html | base2.html, employee/_onboarding_bar.html | forms, table, modal, AJAX, inline JS, inline CSS, DataTables, Bootstrap controls, SweetAlert, upload | Not Started |
| employee/employee_dashboard.html | base2.html, announcements/_banner.html, employee/_reporting_line.html, employee/_birthdays_card.html, approvals/_pending_queues.html | table, inline CSS | Not Started |
| employee/employee_detail.html | base2.html, employee/_onboarding_bar.html, employee/_reporting_line.html | table, inline CSS, DataTables, Bootstrap controls | Not Started |
| employee/offboarding2.html | base2.html | forms, table, modal, AJAX, inline JS, inline CSS, DataTables, Bootstrap controls, SweetAlert, upload, messages | Not Started |
| field_duty/_capture_modal.html |  | forms, modal, Bootstrap controls | Not Started |
| field_duty/_detail.html |  | inline CSS | Not Started |
| field_duty/home.html | base2.html, field_duty/_capture_modal.html | forms, table, modal, inline JS, upload | Not Started |
| field_duty/log.html | base2.html | forms, table, modal, AJAX, inline JS, Bootstrap controls | Not Started |
| holiday_calendar/dashboard.html | base2.html | forms, table, modal, AJAX, inline JS, inline CSS, messages | Not Started |
| leave_balance/_compoff_modal_table.html |  | table | Not Started |
| leave_balance/_leave_history_table.html |  | table | Not Started |
| leave_balance/leave_apply.html | base2.html | forms, table, modal, Bootstrap controls, pagination | In Progress |
| leave_balance/leave_balance_report.html | base2.html | forms, table, AJAX, inline JS, inline CSS, pagination | In Progress |
| leave_policy/leave_credit_policy.html | base2.html | forms | In Progress |
| Modal/branch/branch_create.html |  | forms, modal, Bootstrap controls | Not Started |
| partials/salary_compare.html |  | table, modal, Bootstrap controls | Not Started |
| partials/salary_history_detail.html |  | table, modal, Bootstrap controls | Not Started |
| payroll/payroll_pdf_template.html |  | table, inline CSS | Not Started |
| payroll/run_create.html | base2.html | forms, AJAX, inline JS | Not Started |
| payroll/run_detail.html | base2.html | table, modal, AJAX, inline JS, inline CSS, Bootstrap controls | Not Started |
| payroll/run_list.html | base2.html | forms, table, inline CSS | Not Started |
| payroll/salary_slip.html |  | table, inline CSS | Not Started |
| payroll/salary_slips_list.html | base2.html | forms, table, inline JS, inline CSS | Not Started |
| payroll/salary_statement.html |  | table, inline CSS | Not Started |
| salary/create_salary4.html | base2.html | forms, table, modal, AJAX, inline JS, inline CSS, DataTables, Bootstrap controls, upload | Not Started |
| salary_increment/create_increment.html | base2.html | forms, table, modal, AJAX, inline JS, inline CSS, DataTables, Bootstrap controls, pagination | Not Started |
| salary_increment/salary_history_list.html | base2.html | table, modal, AJAX, inline JS, inline CSS, DataTables | Not Started |
| settings/company_settings_hub.html | base2.html | forms, AJAX, inline JS, inline CSS, Bootstrap controls, SweetAlert | Not Started |
| settings/no_company.html |  | inline CSS | Not Started |
| settings/roles_permissions_hub.html | base2.html | forms, table, AJAX, inline JS, inline CSS, Bootstrap controls, SweetAlert | Not Started |
| settings/settings_page.html | base2.html | forms, AJAX, inline JS, Bootstrap controls, SweetAlert | Not Started |

## Database model relationships

| Model | Declared relation fields and targets |
|---|---|
| Company | — |
| Branch | — |
| Department | reporting_person → 'Employee', manager → 'Employee' |
| Employee | user → User, company → 'Company', branch → 'Branch', reporting_person → 'self', manager → 'self' |
| PreviousEmployment | employee → Employee |
| PreviousEmploymentAttachment | previous_employment → PreviousEmployment |
| EmployeeAttachment | employee → Employee |
| EmployeeChangeRequest | employee → Employee, requested_by → User, decided_by → User |
| EmployeeChangeRequestFile | request → EmployeeChangeRequest |
| Offboarding | employee → Employee |
| AssetHandover | offboarding → Offboarding |
| SalaryMaster | employee → Employee |
| LeaveApplication | employee → 'Employee' |
| LeaveRecord | employee → Employee |
| LeaveSettings | company → 'Company' |
| CompOff | employee → 'Employee' |
| CompOffRequest | employee → Employee |
| LeaveBalance | employee → 'Employee' |
| LeaveBalanceHistory | employee → 'Employee' |
| LeaveCreditPolicy | company → 'Company' |
| PayrollSettings | company → 'Company' |
| SalaryIncrement | employee → Employee |
| SalaryHistory | employee → Employee |
| AdvanceMaster | employee → Employee |
| AdvanceSchedule | advance → AdvanceMaster |
| AdvancePayment | advance → AdvanceMaster |
| PayrollRun | company → Company |
| PayrollRecord | payroll → 'PayrollRun', employee → 'Employee' |
| HolidayType | — |
| HolidayCalendar | branch → 'Branch', created_by → User |
| Holiday | holiday_calendar → HolidayCalendar, holiday_type → HolidayType, branches → 'Branch', specific_employees → 'Employee', created_by → User |
| MonthlyEarnedLeaves | payroll_settings → PayrollSettings |
| HalfDayScenario | branch → 'Branch', created_by → User, approved_by → User |
| Attendance | employee → 'Employee', holiday → Holiday, half_day_scenario → HalfDayScenario |
| AttendanceConfigurable | employee → 'Employee' |
| AttendanceUpload | — |
| EmployeeImportUpload | — |
| SalaryUpload | created_by → User |
| ShiftAssignment | employee → 'Employee', created_by → User |
| AttendanceCorrectionRequest | attendance → Attendance |
| BiometricPunch | employee → 'Employee' |
| BiometricSyncRun | — |
| Feature | — |
| RoleFeaturePermission | role → Group, feature → Feature, updated_by → User |
| Announcement | company → 'Company', created_by → User |
| AnnouncementRead | announcement → Announcement, user → User |
| AuditLog | actor → User, employee → 'Employee', company → 'Company' |
| FieldDuty | employee → 'Employee' |

## Form classes

| Class | Base | Model if declared |
|---|---|---|
| FastSelect | forms.Select |  |
| EmployeeForm | forms.ModelForm | Employee |
| EmployeeAttachmentForm | forms.ModelForm | EmployeeAttachment |
| BranchForm | forms.ModelForm | Branch |
| OffboardingForm | forms.ModelForm | Offboarding |
| AssetHandoverForm | forms.ModelForm | AssetHandover |
| CompanyForm | forms.ModelForm | Company |
| SalaryMasterForm | forms.ModelForm | SalaryMaster |
| AttendanceForm | forms.ModelForm | Attendance |
| PayrollSettingsForm | forms.ModelForm | PayrollSettings |
| LeaveSettingsForm | forms.ModelForm | LeaveSettings |
| LeaveCreditPolicyForm | forms.ModelForm | LeaveCreditPolicy |
| LeaveApplicationForm | forms.ModelForm | LeaveApplication |
| AdvanceCreateForm | forms.ModelForm | AdvanceMaster |
| AdvanceEditForm | forms.ModelForm | AdvanceMaster |
| PaymentForm | forms.Form |  |
| SkipMonthForm | forms.Form |  |
| HolidayForm | forms.ModelForm | Holiday |
| HolidayCalendarForm | forms.ModelForm | HolidayCalendar |
| MonthlyEarnedLeavesForm | forms.ModelForm | MonthlyEarnedLeaves |
| HalfDayScenarioForm | forms.ModelForm | HalfDayScenario |
| BulkHolidayImportForm | forms.Form |  |
| PayrollSettingsForm | forms.ModelForm | PayrollSettings |

## Permission registry

| Category | Feature | Supported actions |
|---|---|---|
| Employee Lifecycle | employee_records | view, create, edit |
| Employee Lifecycle | employee_delete | edit |
| Employee Lifecycle | employee_change_approval | approve |
| Employee Lifecycle | department_management | view, edit |
| Employee Lifecycle | offboarding | view, create, edit |
| Organization Setup | company_management | view, edit |
| Organization Setup | branch_management | view, edit |
| Organization Setup | holiday_calendar | edit |
| Attendance & Scheduling | attendance_data | edit |
| Attendance & Scheduling | attendance_review | view, edit |
| Attendance & Scheduling | attendance_register | view, edit |
| Attendance & Scheduling | shift_roster | view, edit |
| Attendance & Scheduling | attendance_corrections | view, create, approve |
| Attendance & Scheduling | field_duty | view, edit |
| Leave & Comp-Off | leave_management | view, create, edit, approve |
| Leave & Comp-Off | comp_off | view, create, edit, approve |
| Compensation | salary_structure | view, create, edit |
| Compensation | salary_history | view |
| Compensation | payroll | view, edit |
| Compensation | advances | view, edit |
| Administration | company_settings | view, edit |
| Administration | company_settings_broadcast | edit |
| Administration | user_accounts | edit |
| Administration | admin_dashboard | view |
| Administration | announcements | view, edit |
| Administration | audit_log | view |
| Administration | archive_records | edit |

## Module implementation checklist

Each row covers backend and database review, forms, tables, workflows, permission tests, integrations, responsive layouts and functional QA. Status describes the transformation work, independently of existing capabilities.

| Module | Current workflow and next change | Status |
|---|---|---|
| Shared shell and navigation | Shared desktop menu and mobile toggle. Use permission-filtered destinations for keyboard navigation and search. | Not Started |
| Authentication | Login, password change and reset with separate templates. Verify invalid and expired tokens and focus handling. | Not Started |
| Dashboards | Shared heading and summary styling implemented. Verify every panel and action with representative role and company data. | In Progress |
| Organization | Company, branch and department directories updated. Create/edit validation and role controls reviewed. Deployed integration review remains open. | In Progress |
| Employee lifecycle | Directory, profile, change queue, decision detail and offboarding updated. Assigned onboarding tasks, clearance and resignation workflows remain open. | In Progress |
| Attendance and field duty | Registers, imports, shifts, late review, correction, biometric sync and field visits. Preserve punch reconciliation, camera and upload flows. | In Progress |
| Leave and holidays | Applications, policy, balance history, compensatory leave and holiday rules. Preserve accruals and approval effects. | In Progress |
| Payroll and advances | Salary structures, increments, advances, payroll runs, statements and slips. Verify calculations, period locking, PDF and spreadsheet exports. | In Progress |
| Approvals | Manager queues and employee change review. Retain reporting-line and object scope. | Not Started |
| Administration | Settings, role grants, announcement publishing and audit history. Verify tenant filters and protected operations. | Not Started |
| Recruitment | Add requisitions, candidates, applications, interviews and offers. Convert accepted offers into onboarding records. | Not Started |
| Performance | Add review cycles, objectives, evaluations and sign-off linked to reporting lines. | Not Started |
| Learning | Add course catalogue, assignments, completions and certification records. | Not Started |
| Assets | Extend exit handovers with an inventory, allocation history and returns. | Not Started |
| Travel and expenses | Add claims, receipts, manager review, finance settlement and reporting. | Not Started |
| Documents | Extend existing attachments with policies, version history, acknowledgements and scoped downloads. | Not Started |
| Helpdesk | Add employee tickets, queues, replies and resolution tracking. | Not Started |
| Engagement | Extend announcements with surveys, responses and aggregated results. | Not Started |
| Workforce planning | Add approved positions, headcount budgets and hiring demand. | Not Started |
| Resignation and exit | Extend existing offboarding with resignation approval, clearance and settlement. | Not Started |
| Analytics | Extend existing attendance and payroll reports with permission-scoped cross-module analysis. | Not Started |

## Integrations and verification order

1. Preserve eSSL sync, scheduled Celery tasks, email delivery, file access checks and payroll exports. Use local test fixtures for workflow verification.
2. Establish design tokens and a shared horizontal shell. Inventory child-template overrides before retiring vendor assets. The shell loads DataTables, Select2, SweetAlert, ApexCharts and Bootstrap-oriented styles. Inline page scripts rely on their DOM contracts.
3. Convert dashboards, organization, employee lifecycle, attendance, leave, payroll and administration. Verify employee, manager, HR and admin access at each step.
4. Build missing modules in lifecycle order, starting with recruitment and onboarding. Introduce real models, scoped views, forms, migrations and tests before exposing module links.
5. Verify mobile navigation, keyboard access, exports, invalid submissions, object permissions and integration failure handling. Run the full Django suite and migration checks before release.

## Open audit findings

- Both api-earned-leaves declarations resolve to the same literal path. Record current resolver behavior before modifying either handler.
- The topbar now highlights matching destinations, including the pending-onboarding filter. Detail routes without a corresponding menu link still need parent-module mapping.
- Source enumeration cannot verify runtime data, accessibility or responsive behavior. Browser review and role-based workflow testing remain pending.

## Proposed horizontal navigation

| Group | Existing destinations and actions |
|---|---|
| Home | Role-specific dashboard, My Approvals |
| Organization | Entity, Branch, Departments |
| Employees | Employee list and export, Add Employee, Pending Onboarding, Change Approvals, Employee Offboarding |
| Attendance | Attendance List, Excel upload, Biometric Sync, Attendance Correction, My Attendance, Field Duty, Correction Request Status, Shift Roster, Attendance Register, Late Attendance Review |
| Leave | Leave Balance, Apply Comp-Off, Comp-Off Request Status, Leave Credit Policy, Leave Apply, Recalculate Leaves, Holiday Management |
| Payroll | Create Salary Structure, Salary Increment, Salary History, Payroll Run, All Advances, Create Advance |
| Administration | Settings Hub, Roles & Permissions, Announcements, Audit Log |
| Account and notifications | Retain existing user dropdown, account actions, theme and announcements bell |

Overflow groups belong in a More dropdown. Show groups only when they contain accessible destinations. Preserve the existing constraints on actions such as export and leave recalculation. A future command palette should distinguish navigation from actions that submit changes.

## Baseline verification

Django system checks passed with SQLite. The migration dry run detected no model changes. The Django template loader compiled all 75 application template files. The app registry contains 48 website models, with 59 numbered migration files on disk. The permission registry declares 27 features. Django resolves the duplicate earned-leave URL to api_earned_leaves. These checks establish a source and configuration baseline. Authenticated browser walkthroughs, deployed integrations and the full workflow suite remain to be verified.


## Shared shell implementation, 21 November 2026

| Deliverable | Status | Evidence and outstanding work |
|---|---|---|
| Application shell | In Progress | The shared Django template uses a fixed horizontal topbar, grouped native disclosures, an overflow menu and a compact mobile dropdown. The announcement and account controls retain their existing actions. Standalone pages still need individual review. |
| Design system | In Progress | Shared tokens and component rules cover shell, focus, cards, form controls, tables, headings and dashboard summaries. Existing modules still have page-specific styles. |
| Search | In Progress | Ctrl/Cmd+K searches authorized navigation. Users with employee directory access can search names and employee codes and open profiles. The existing employee search endpoint now returns no suggestions for an unassigned account without global access. Other record types are pending. |
| Dashboard | In Progress | Both role dashboards use the shared page heading. The workforce dashboard uses the shared summary and chart styles. Metric and workflow review across companies remains outstanding. |

### Verification of this phase

- Django system check and migration drift check passed. All current HTML templates compiled.
- 66 dashboard, employee self-service, branding and page-render regression tests passed. Another 29 tests covering employee search and dashboard absentees passed.
- Chrome rendered the workforce dashboard with a synthetic administrator. At 320, 375, 768, 1200 and 1440 pixels, the module dropdown, keyboard search and profile dropdown opened, the account menu stayed inside the viewport and the page had no horizontal overflow. The browser run used local assets with external requests blocked. It recorded no uncaught JavaScript exceptions.
- Browser verification used a rendered fixture. Authenticated end-to-end testing with representative company data, the full suite and visual review of every module remain pending.

The next implementation phase covers existing module screens, beginning with organization and employee management. Recruitment is the first missing lifecycle module in the development sequence.


## Organization and employee workflow implementation

| Screen | Implemented |
|---|---|
| Companies | Direct status-filtered Excel export, shared status navigation, grouped actions and a single set of accessible fields for create and edit. Invalid submissions preserve entered values and show errors in the modal. |
| Branches | Direct Excel export, shared status navigation and model-form validation on create. Blank names are rejected. Invalid edits return to the directory with the edit dialog open. |
| Departments | Name search works together with the active/archive filter. Reporting-line editing and membership drill-down remain available. |
| Employee directory | Permission-aware create, import, edit and bulk actions. Searchable table, named selection controls, status badges and composable branch, status and onboarding filters. |
| Employee profile | Identity header with employee code, organization and joining date. Directory return and edit actions follow feature permissions. |
| Change approvals and detail | Search by employee name or code. Server-side pagination replaces the former 200-record limit. Status and search carry through pagination. Bulk decisions apply to selected requests on the page. |
| Employee offboarding | Status filters, direct export and permission-aware row actions. The existing handover and asset forms retain their original routes. |

Authenticated Chrome checks used an isolated SQLite database with synthetic staff and employee records. All eight screens loaded at 375 and 1440 pixels without page overflow or uncaught JavaScript exceptions. The read-only directory offered profile access and hid creation, import and bulk controls. Invalid branch creation retained the address, and invalid company editing returned to the open dialog with a field error. External CDN requests were blocked during this browser pass.

Attendance and leave are the next existing workflow areas. Assigned onboarding tasks, expanded exit workflows and the new modules remain open.

## Attendance and leave workflow implementation

| Area | Implemented |
|---|---|
| Leave applications | Search by employee, employee code or leave type. Search and status persist across pages. Each authorized record expands to show its reason and submission date. Reversed dates and finalized payroll conflicts return to the application form with retained values. |
| Attendance review | Shared page headings on the daily list, register, employee history and late review. Filters have associated labels. History links back to attendance records for viewers with access. |
| Shift roster and requests | Assignment and edit actions follow roster permissions. Archive requires the additional archive permission. Roster filters carry across status changes and pagination. Correction and comp-off queues have reset links. |
| Imports and configuration | Attendance file upload reports progress to assistive technology. Import errors display as text. Biometric sync uses the shared message area. The policy form displays field errors. Leave balance pagination retains filter parameters. |

Chrome checks used an isolated SQLite fixture, synthetic records and locally served assets. Eleven pages loaded at 375 and 1440 pixels with no horizontal overflow or uncaught JavaScript exceptions. The browser opened a leave record and confirmed that an invalid date range retains the reason and reopens the form. A separate authenticated Django check exercised the company-specific credit policy page and its invalid-form response. All 76 HTML templates compiled. Live biometric hardware and production data were outside this verification pass.

The overnight field-duty test now fixes its start at 18:00 on the previous local date. Its former clock-relative fixture sometimes ended on the same day, which prevented it from testing the intended midnight crossing.

The full Django suite ran 1,091 tests on SQLite with a fast test-only password hasher. 1,090 passed, one was skipped and none failed. Django system checks and the migration drift check passed.

## Payroll and employee advances

| Workflow | Changes |
|---|---|
| Payroll runs and slips | Updated the run list, creation form, run detail and salary slip list. The run list paginates results and shows company totals across statuses. |
| Salary master and increments | The master uses the actual table count. Increment status filters work with the archive selection. Search covers all table pages and carries into Excel export. |
| Salary history | The employee and date filters apply to both the paginated list and Excel export. Older date parameter names retain their original behavior. |
| Employee advances | Updated the list, creation form, detail and edit screens. The list shows repayment progress and scoped outstanding totals. Forms validate the repayment term and retain the date when editing. |

Chrome checks used synthetic payroll records at 375 and 1440 pixels. All 11 screens loaded without horizontal overflow or uncaught JavaScript exceptions. The checks opened the salary calculator, increment form, advance payment dialog and salary history detail, and found an increment beyond the first page using employee appraisal text and its date. At the end of this phase, visual review of printed payslips and combined salary statements remained open.

The full Django suite ran 1,093 tests on SQLite. 1,092 passed and one was skipped. All 41 targeted salary and search tests passed after the final template edits. All 77 templates compiled, the Django system check passed and the migration check found no changes.

## Payslips and combined salary statements

The two employee-facing payroll documents now have a consistent browser toolbar with a direct return to the employee's slip list, printing and PDF download. The printed documents emphasize the title and net pay. Individual draft slips carry their status. Long combined statements use separate landscape pages with employee identification and repeated month and amount headings.

Verification used synthetic records through the Django download routes. Visual inspection covered a one-page portrait payslip and a three-month landscape statement. Chrome checked both browser previews at 375 and 1440 pixels and hid the toolbar in print mode. A separate regression test exercises a five-year statement for pagination, month coverage and the final total.

## Field duty

Updated the employee visit page and the reviewer log to use the shared page headings. Report upload progress and errors appear beside the selected file, and a failed upload re-enables the submit button. Team leaders can select themselves or a direct report in the employee filter.

The review log now paginates all matching visits in groups of 50. Summary counts cover the entire filtered result. Search can combine employee name, employee code and visit purpose, and pagination retains the active filters.

All 65 field-duty tests passed, including a regression for retrieving the 501st matching visit. All 77 templates compiled. Chrome checks at 375 and 1440 pixels opened the capture dialog and loaded a visit detail without page overflow or uncaught errors. A simulated rejected report showed its error inline and allowed retry. Physical camera and GPS capture still require a device check.

## Page layout redesign

The admin dashboard, employee workspace, payroll runs, advances, holiday calendar, leave balance report, approvals and field-duty log now group their headline information into a single summary panel. The employee directory and field-duty log use a separate desktop filter column, and the field-duty employee page places capture and reporting beside the visit history. The layouts stack on phones. The existing top navigation stays in place.

All ten pages rendered in an authenticated Chrome session at 375 and 1440 pixels without horizontal page overflow. The screenshots and browser checks used synthetic employee and payroll data. Additional screens still need individual layout review.

## Admin dashboard reference layout

The admin dashboard uses the supplied screenshot's four KPI cards, dated quick-action strip, full-width onboarding and absence tables, and paired payroll and workforce panels. The top navigation uses the existing shared component. The dashboard stacks on phones and keeps summary counts, dates, and scoped records live.

Approval counts link to the matching on-page queues available to the reviewer. Draft and finalized payroll totals open their filtered run lists. The dashboard excludes future starts from new and recent joiners, uses the configured local date, and limits upcoming exits to active offboarding records within the dashboard's company scope. The attendance breakdown distinguishes late from other present employees and avoids counting no-punch absences again as unmarked.

Authenticated Chrome checks covered 1440px and 375px using synthetic records, including the leave queue link and a seven-employee no-punch case.

## Employee and management dashboards

The employee home follows the dashboard sample with a greeting, shift and punch history, leave balances, request statuses, announcements, team leave, birthdays and work anniversaries. Payroll, profile completion, upcoming leave and reporting-line approvals remain accessible from the same page.

Admin and HR users can filter their operational overview by company. Management reports support month, company, branch and department filters, section visibility saved in the browser, Excel export, and print. Managers and HODs see their reporting hierarchy. The Director permission opens aggregate executive workforce and finalized payroll reports. Migration 0060 creates the executive feature and default grants.

Payroll editors can record or correct an individual salary payment date from a finalized payroll run. The employee dashboard and salary slip list show the recorded date. Workforce and executive payroll reports count confirmed payslips and those awaiting confirmation for the selected payroll period. Migration 0061 adds the nullable date and audit action.

Recruitment, performance, training, revenue and compliance-case widgets require additional source data or workflows.

## Employee attendance

The employee dashboard opens a Monday-first attendance calendar with a selectable day detail, punch history, worked duration, regularization and next week's roster. The calendar follows the selected payroll cycle or custom range. Dates without records and days without a shift assignment have explicit empty states. The list, filters, comp-off requests and attendance download remain available.

## Leave workspace

Apply leave from the dashboard to see the inline application form, latest published balance, comp-off credited in that period, request history and upcoming applicable holidays. The date preview shows inclusive calendar days, matching the application history. Existing employee selection, status filters, search, pagination and finalized-payroll checks remain available where applicable.
