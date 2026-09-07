"""Narrow HR's permissions to match the intended separation of duties.

HR now:
  * has no payroll access at all -- not even read. Payroll belongs to the
    Payroll Officer (and Super Admin);
  * uploads and reads attendance, but does not correct recorded days;
  * reads leave balances (their own and everyone's) without editing them;
  * approves nothing. Sign-off sits with Admin/Super Admin/Payroll Officer,
    and with HODs through their reporting line.

Everything HR could already do that isn't listed above is unchanged: adding
and viewing employees, salary structures and offboardings (without editing
them), branches, holidays, departments, announcements and the audit log.

Re-seeds the whole matrix from SEED_GRANTS rather than toggling individual
rows, so the shipped roles always match the registry. Reversing restores
the grants HR held before this migration.
"""
from django.db import migrations

from website.permissions_registry import SEED_GRANTS, SYSTEM_ROLES

_ACTIONS = ("view", "create", "edit", "approve")

# HR's grants as they stood before this migration, so a reverse is exact.
_PREVIOUS_HR_GRANTS = {
    ("attendance_review", "edit"),
    ("attendance_corrections", "approve"),
    ("leave_management", "edit"),
    ("leave_management", "approve"),
    ("comp_off", "approve"),
    ("payroll", "view"),
    ("payroll", "edit"),
}


def _reseed(apps, grants):
    Group = apps.get_model("auth", "Group")
    Feature = apps.get_model("website", "Feature")
    RoleFeaturePermission = apps.get_model("website", "RoleFeaturePermission")

    for role_name in SYSTEM_ROLES:
        group, _ = Group.objects.get_or_create(name=role_name)
        for feature in Feature.objects.all():
            rfp, _ = RoleFeaturePermission.objects.get_or_create(role=group, feature=feature)
            for action in _ACTIONS:
                setattr(rfp, f"can_{action}", role_name in grants.get((feature.key, action), ()))
            rfp.save()


def restrict_hr(apps, schema_editor):
    _reseed(apps, SEED_GRANTS)


def restore_hr(apps, schema_editor):
    grants = {key: tuple(value) for key, value in SEED_GRANTS.items()}
    for key in _PREVIOUS_HR_GRANTS:
        grants[key] = tuple(sorted(set(grants.get(key, ())) | {"HR"}))
    _reseed(apps, grants)


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0033_new_role_structure"),
    ]

    operations = [
        migrations.RunPython(restrict_hr, restore_hr),
    ]
