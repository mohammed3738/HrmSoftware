"""
Single source of truth for the Roles & Permissions feature registry and its
seed data. Inert data only (no model imports) so it's safe to import from a
migration. See website/models.py (Feature, RoleFeaturePermission) and
website/utils/decorators.py (feature_required) for how this is consumed.

FEATURES defines the permission matrix rows shown in the Roles & Permissions
UI. SEED_GRANTS is the golden mapping used both to seed
RoleFeaturePermission rows and to verify, in tests, that every
@feature_required(...) call site grants exactly the access intended.

Actions
-------
view    — can open the page / read the records
create  — can add new records, but not change existing ones
edit    — can change (and archive) existing records
approve — can approve/reject requests

`create` exists because "add but don't touch what's already there" is a real
separation of duties: HR onboards employees and drafts salary structures,
while corrections to an existing record stay with Admin. A feature only
offers the actions its `has_*` flags declare.

Only actions with a real, currently-decorated view get an entry here —
never invent a seed value for a page that isn't gated today, since that
would silently lock down something that's currently open to any logged-in
user.
"""

FEATURES = [
    {"key": "employee_records", "name": "Employee Records", "category": "Employee Lifecycle",
     "has_view": True, "has_create": True, "has_edit": True, "has_approve": False, "sort_order": 10},
    {"key": "department_management", "name": "Departments & Reporting Line", "category": "Employee Lifecycle",
     "has_view": True, "has_create": False, "has_edit": True, "has_approve": False, "sort_order": 15},
    {"key": "offboarding", "name": "Offboarding", "category": "Employee Lifecycle",
     "has_view": True, "has_create": True, "has_edit": True, "has_approve": False, "sort_order": 20},

    {"key": "company_management", "name": "Company Management", "category": "Organization Setup",
     "has_view": True, "has_create": False, "has_edit": True, "has_approve": False, "sort_order": 10},
    {"key": "branch_management", "name": "Branch Management", "category": "Organization Setup",
     "has_view": True, "has_create": False, "has_edit": True, "has_approve": False, "sort_order": 20},
    {"key": "holiday_calendar", "name": "Holiday Calendar", "category": "Organization Setup",
     "has_view": False, "has_create": False, "has_edit": True, "has_approve": False, "sort_order": 30},

    {"key": "attendance_data", "name": "Attendance Data Management", "category": "Attendance & Scheduling",
     "has_view": False, "has_create": False, "has_edit": True, "has_approve": False, "sort_order": 10},
    {"key": "attendance_review", "name": "Attendance Monitoring & Review", "category": "Attendance & Scheduling",
     "has_view": True, "has_create": False, "has_edit": True, "has_approve": False, "sort_order": 20},
    {"key": "shift_roster", "name": "Shift Roster", "category": "Attendance & Scheduling",
     "has_view": True, "has_create": False, "has_edit": True, "has_approve": False, "sort_order": 30},
    {"key": "attendance_corrections", "name": "Attendance Corrections", "category": "Attendance & Scheduling",
     "has_view": True, "has_create": False, "has_edit": False, "has_approve": True, "sort_order": 40},

    {"key": "leave_management", "name": "Leave Management", "category": "Leave & Comp-Off",
     "has_view": True, "has_create": False, "has_edit": True, "has_approve": True, "sort_order": 10},
    {"key": "comp_off", "name": "Comp-Off", "category": "Leave & Comp-Off",
     "has_view": True, "has_create": False, "has_edit": False, "has_approve": True, "sort_order": 20},

    {"key": "salary_structure", "name": "Salary Structure & History", "category": "Compensation",
     "has_view": True, "has_create": True, "has_edit": True, "has_approve": False, "sort_order": 10},
    {"key": "payroll", "name": "Payroll Processing", "category": "Compensation",
     "has_view": True, "has_create": False, "has_edit": True, "has_approve": False, "sort_order": 20},
    {"key": "advances", "name": "Employee Advances", "category": "Compensation",
     "has_view": True, "has_create": False, "has_edit": True, "has_approve": False, "sort_order": 30},

    {"key": "company_settings_broadcast", "name": "Company Settings Broadcast", "category": "Administration",
     "has_view": False, "has_create": False, "has_edit": True, "has_approve": False, "sort_order": 10},
    {"key": "user_accounts", "name": "User Account Creation", "category": "Administration",
     "has_view": False, "has_create": False, "has_edit": True, "has_approve": False, "sort_order": 20},
    {"key": "admin_dashboard", "name": "Admin Dashboard", "category": "Administration",
     "has_view": True, "has_create": False, "has_edit": False, "has_approve": False, "sort_order": 30},
    {"key": "announcements", "name": "Announcements Management", "category": "Administration",
     "has_view": True, "has_create": False, "has_edit": True, "has_approve": False, "sort_order": 40},
    {"key": "audit_log", "name": "Audit Log", "category": "Administration",
     "has_view": True, "has_create": False, "has_edit": False, "has_approve": False, "sort_order": 50},
]

# Roles, most privileged first. "Manager" was renamed to "HOD"; Super Admin
# and Payroll Officer are new.
SYSTEM_ROLES = ("Super Admin", "Admin", "Payroll Officer", "HR", "HOD", "Employee")

# Roles that see company-wide data rather than only their own records.
# HOD and Employee are self-service: they read their own attendance, leave
# balance, salary structure, payslips and advances, and HODs additionally
# approve for the people who report to them (see website/utils/permissions.py
# can_approve_for_employee -- that authority comes from the reporting line,
# not from a blanket role grant, so a HOD signs off for their own department
# rather than the whole company).
GLOBAL_ACCESS_ROLES = ("Super Admin", "Admin", "Payroll Officer", "HR")

# Roles whose landing page is the self-service employee dashboard.
SELF_SERVICE_ROLES = ("HOD", "Employee")

_ALL_STAFF = ("Super Admin", "Admin", "Payroll Officer", "HR")
_NOT_HR = ("Super Admin", "Admin", "Payroll Officer")

# {(feature_key, action): (role names granted access,)}
SEED_GRANTS = {
    # ── Employee Lifecycle ────────────────────────────────────────────
    # HR onboards and offboards, but corrections to an existing record
    # are Admin's -- hence create without edit.
    ("employee_records", "view"): _ALL_STAFF,
    ("employee_records", "create"): _ALL_STAFF,
    ("employee_records", "edit"): _NOT_HR,
    ("department_management", "view"): _ALL_STAFF,
    ("department_management", "edit"): _ALL_STAFF,
    ("offboarding", "view"): _ALL_STAFF,
    ("offboarding", "create"): _ALL_STAFF,
    ("offboarding", "edit"): _NOT_HR,

    # ── Organization Setup ────────────────────────────────────────────
    # Only Super Admin may change companies; everyone else reads them.
    ("company_management", "view"): _ALL_STAFF,
    ("company_management", "edit"): ("Super Admin",),
    ("branch_management", "view"): _ALL_STAFF,
    ("branch_management", "edit"): _ALL_STAFF,
    ("holiday_calendar", "edit"): _ALL_STAFF,

    # ── Attendance & Scheduling ───────────────────────────────────────
    # HR uploads attendance and reads it back, but doesn't correct it:
    # editing a recorded day is a change to someone's pay.
    ("attendance_data", "edit"): _ALL_STAFF,
    ("attendance_review", "view"): _ALL_STAFF,
    ("attendance_review", "edit"): _NOT_HR,
    ("shift_roster", "view"): _ALL_STAFF,
    ("shift_roster", "edit"): _ALL_STAFF,
    ("attendance_corrections", "view"): _ALL_STAFF,
    ("attendance_corrections", "approve"): _NOT_HR,

    # ── Leave & Comp-Off ──────────────────────────────────────────────
    # HR reads leave balances -- their own and everyone's -- but neither
    # edits them nor signs off on requests. Approvals belong to Admin,
    # Super Admin, and to HODs through their reporting line.
    ("leave_management", "view"): _ALL_STAFF,
    ("leave_management", "edit"): _NOT_HR,
    ("leave_management", "approve"): _NOT_HR,
    ("comp_off", "view"): _ALL_STAFF,
    ("comp_off", "approve"): _NOT_HR,

    # ── Compensation ──────────────────────────────────────────────────
    # HR drafts a structure; changing an existing one stays with Admin.
    ("salary_structure", "view"): _ALL_STAFF,
    ("salary_structure", "create"): _ALL_STAFF,
    ("salary_structure", "edit"): _NOT_HR,
    # Payroll is the Payroll Officer's alone to run. Admin can read a run
    # but not create, edit, recalculate or finalize one; HR has no payroll
    # access at all, not even read.
    ("payroll", "view"): _NOT_HR,
    ("payroll", "edit"): ("Super Admin", "Payroll Officer"),
    # Advances are a payroll matter, so HR administers none of them.
    # Everyone can still see their OWN advance -- that's self-service on
    # advance_list, not a grant (see advance_list / advance_detail).
    ("advances", "view"): _NOT_HR,
    ("advances", "edit"): _NOT_HR,

    # ── Administration ────────────────────────────────────────────────
    ("company_settings_broadcast", "edit"): _NOT_HR,
    ("user_accounts", "edit"): _NOT_HR,
    ("admin_dashboard", "view"): _ALL_STAFF,
    ("announcements", "view"): _ALL_STAFF,
    ("announcements", "edit"): _ALL_STAFF,
    ("audit_log", "view"): _ALL_STAFF,
}
