"""
Single source of truth for the Roles & Permissions feature registry and its
seed data. Inert data only (no model imports) so it's safe to import from a
migration. See website/models.py (Feature, RoleFeaturePermission) and
website/utils/decorators.py (feature_required) for how this is consumed.

FEATURES defines the permission matrix rows shown in the Roles & Permissions
UI. SEED_GRANTS is the golden mapping used both to seed initial
RoleFeaturePermission rows (migration 0019) and to verify, in tests, that
every migrated @feature_required(...) call site grants exactly the same
access as its original @group_required(...) decorator did.

Only actions with a real, currently-decorated view get an entry here —
never invent a seed value for a page that isn't gated today, since that
would silently lock down something that's currently open to any logged-in
user.
"""

FEATURES = [
    {"key": "employee_records", "name": "Employee Records", "category": "Employee Lifecycle",
     "has_view": True, "has_edit": True, "has_approve": False, "sort_order": 10},
    {"key": "offboarding", "name": "Offboarding", "category": "Employee Lifecycle",
     "has_view": True, "has_edit": True, "has_approve": False, "sort_order": 20},

    {"key": "company_management", "name": "Company Management", "category": "Organization Setup",
     "has_view": True, "has_edit": True, "has_approve": False, "sort_order": 10},
    {"key": "branch_management", "name": "Branch Management", "category": "Organization Setup",
     "has_view": True, "has_edit": True, "has_approve": False, "sort_order": 20},
    {"key": "holiday_calendar", "name": "Holiday Calendar", "category": "Organization Setup",
     "has_view": False, "has_edit": True, "has_approve": False, "sort_order": 30},

    {"key": "attendance_data", "name": "Attendance Data Management", "category": "Attendance & Scheduling",
     "has_view": False, "has_edit": True, "has_approve": False, "sort_order": 10},
    {"key": "attendance_review", "name": "Attendance Monitoring & Review", "category": "Attendance & Scheduling",
     "has_view": True, "has_edit": True, "has_approve": False, "sort_order": 20},
    {"key": "shift_roster", "name": "Shift Roster", "category": "Attendance & Scheduling",
     "has_view": True, "has_edit": True, "has_approve": False, "sort_order": 30},
    {"key": "attendance_corrections", "name": "Attendance Corrections", "category": "Attendance & Scheduling",
     "has_view": True, "has_edit": False, "has_approve": True, "sort_order": 40},

    {"key": "leave_management", "name": "Leave Management", "category": "Leave & Comp-Off",
     "has_view": True, "has_edit": True, "has_approve": True, "sort_order": 10},
    {"key": "comp_off", "name": "Comp-Off", "category": "Leave & Comp-Off",
     "has_view": True, "has_edit": False, "has_approve": True, "sort_order": 20},

    {"key": "salary_structure", "name": "Salary Structure & History", "category": "Compensation",
     "has_view": True, "has_edit": True, "has_approve": False, "sort_order": 10},
    {"key": "payroll", "name": "Payroll Processing", "category": "Compensation",
     "has_view": False, "has_edit": True, "has_approve": False, "sort_order": 20},
    {"key": "advances", "name": "Employee Advances", "category": "Compensation",
     "has_view": True, "has_edit": True, "has_approve": False, "sort_order": 30},

    {"key": "company_settings_broadcast", "name": "Company Settings Broadcast", "category": "Administration",
     "has_view": False, "has_edit": True, "has_approve": False, "sort_order": 10},
    {"key": "user_accounts", "name": "User Account Creation", "category": "Administration",
     "has_view": False, "has_edit": True, "has_approve": False, "sort_order": 20},
    {"key": "admin_dashboard", "name": "Admin Dashboard", "category": "Administration",
     "has_view": True, "has_edit": False, "has_approve": False, "sort_order": 30},
    {"key": "announcements", "name": "Announcements Management", "category": "Administration",
     "has_view": True, "has_edit": True, "has_approve": False, "sort_order": 40},
]

SYSTEM_ROLES = ("Admin", "HR", "Manager", "Employee")

# {(feature_key, action): (group_names granted access today,)}
SEED_GRANTS = {
    ("employee_records", "view"): ("Admin", "HR"),
    ("employee_records", "edit"): ("Admin", "HR"),
    ("offboarding", "edit"): ("Admin", "HR"),

    ("company_management", "view"): ("Admin", "HR"),
    ("company_management", "edit"): ("Admin",),
    ("branch_management", "view"): ("Admin", "HR"),
    ("branch_management", "edit"): ("Admin", "HR"),
    ("holiday_calendar", "edit"): ("Admin", "HR"),

    ("attendance_data", "edit"): ("Admin", "HR"),
    ("attendance_review", "view"): ("Admin", "HR", "Manager"),
    ("attendance_review", "edit"): ("Admin", "HR", "Manager"),
    ("shift_roster", "view"): ("Admin", "HR", "Manager"),
    ("shift_roster", "edit"): ("Admin", "HR", "Manager"),
    ("attendance_corrections", "view"): ("Admin", "HR", "Manager"),
    ("attendance_corrections", "approve"): ("Admin", "HR", "Manager"),

    ("leave_management", "view"): ("Admin", "HR"),
    ("leave_management", "edit"): ("Admin", "HR"),
    ("leave_management", "approve"): ("Admin", "HR", "Manager"),
    ("comp_off", "view"): ("Admin", "HR", "Manager"),
    ("comp_off", "approve"): ("Admin", "HR", "Manager"),

    ("salary_structure", "view"): ("Admin", "HR", "Manager"),
    ("salary_structure", "edit"): ("Admin", "HR"),
    ("payroll", "edit"): ("Admin", "HR"),
    ("advances", "view"): ("Admin", "HR"),
    ("advances", "edit"): ("Admin", "HR"),

    ("company_settings_broadcast", "edit"): ("Admin",),
    ("user_accounts", "edit"): ("Admin",),
    ("admin_dashboard", "view"): ("Admin", "HR"),
    ("announcements", "view"): ("Admin", "HR"),
    ("announcements", "edit"): ("Admin", "HR"),
}
