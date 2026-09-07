"""Replace the four-role structure (Admin / HR / Manager / Employee) with
six: Super Admin, Admin, Payroll Officer, HR, HOD, Employee.

  * "Manager" becomes "HOD" -- the group is renamed in place so every user
    already in it keeps their membership and nothing has to be reassigned
    by hand.
  * Super Admin and Payroll Officer are created empty; someone has to be
    put in them deliberately.
  * The whole permission matrix is re-seeded from SEED_GRANTS, including
    the new `create` action, so the shipped roles match the registry
    exactly rather than carrying forward whatever the old rows said.

Reversing restores the previous four-role matrix: HOD is renamed back to
Manager and the new groups are removed.
"""
from django.db import migrations

from website.permissions_registry import FEATURES, SEED_GRANTS, SYSTEM_ROLES

_ACTIONS = ("view", "create", "edit", "approve")

# The matrix as it stood before this migration, so a reverse restores it.
_LEGACY_ROLES = ("Admin", "HR", "Manager", "Employee")
_LEGACY_GRANTS = {
    ("employee_records", "view"): ("Admin", "HR"),
    ("employee_records", "edit"): ("Admin", "HR"),
    ("offboarding", "edit"): ("Admin", "HR"),
    ("department_management", "view"): ("Admin", "HR", "Manager"),
    ("department_management", "edit"): ("Admin", "HR"),
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
    ("audit_log", "view"): ("Admin", "HR"),
}


def _sync_feature_flags(apps):
    """Keep the Feature rows' has_* flags in step with the registry, so the
    matrix UI renders the right columns (payroll gained a View column, and
    three features gained Create)."""
    Feature = apps.get_model("website", "Feature")
    for row in FEATURES:
        Feature.objects.update_or_create(
            key=row["key"],
            defaults={k: v for k, v in row.items() if k != "key"},
        )


def _reseed(apps, roles, grants):
    Group = apps.get_model("auth", "Group")
    Feature = apps.get_model("website", "Feature")
    RoleFeaturePermission = apps.get_model("website", "RoleFeaturePermission")

    for role_name in roles:
        group, _ = Group.objects.get_or_create(name=role_name)
        for feature in Feature.objects.all():
            rfp, _ = RoleFeaturePermission.objects.get_or_create(role=group, feature=feature)
            for action in _ACTIONS:
                granted = grants.get((feature.key, action), ())
                setattr(rfp, f"can_{action}", role_name in granted)
            rfp.save()


def apply_new_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")

    # Rename in place so existing Manager users become HODs without losing
    # their group membership.
    manager = Group.objects.filter(name="Manager").first()
    if manager and not Group.objects.filter(name="HOD").exists():
        manager.name = "HOD"
        manager.save()
    elif manager:
        # A HOD group somehow already exists -- move the users across, then
        # drop the now-empty Manager group.
        hod = Group.objects.get(name="HOD")
        for user in manager.user_set.all():
            user.groups.add(hod)
        manager.delete()

    _sync_feature_flags(apps)
    _reseed(apps, SYSTEM_ROLES, SEED_GRANTS)

    # Roles no longer part of the structure shouldn't linger in the matrix.
    Group.objects.filter(name="Manager").delete()


def revert_to_legacy_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")

    hod = Group.objects.filter(name="HOD").first()
    if hod and not Group.objects.filter(name="Manager").exists():
        hod.name = "Manager"
        hod.save()

    _reseed(apps, _LEGACY_ROLES, _LEGACY_GRANTS)
    Group.objects.filter(name__in=("Super Admin", "Payroll Officer", "HOD")).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0032_feature_has_create_rolefeaturepermission_can_create"),
    ]

    operations = [
        migrations.RunPython(apply_new_roles, revert_to_legacy_roles),
    ]
