"""New box on Roles & Permissions: "Employees' Own Profile Changes -> Approve".

Holders approve or reject the changes employees send from My Details
(personal and bank details). Granted to every staff role, so HR can now
decide them; HR's own edits to other employees still need "Approve
Employee Changes", which HR doesn't hold.
"""
from django.db import migrations

FEATURE = {
    "key": "employee_self_change_approval", "name": "Employees' Own Profile Changes",
    "category": "Employee Lifecycle", "has_view": False, "has_create": False,
    "has_edit": False, "has_approve": True, "sort_order": 14,
}
ROLES = ("Super Admin", "Admin", "Payroll Officer", "HR")


def forwards(apps, schema_editor):
    Feature = apps.get_model("website", "Feature")
    RoleFeaturePermission = apps.get_model("website", "RoleFeaturePermission")
    Group = apps.get_model("auth", "Group")
    defaults = {k: v for k, v in FEATURE.items() if k != "key"}
    feature, _ = Feature.objects.update_or_create(key=FEATURE["key"], defaults=defaults)
    for group in Group.objects.filter(name__in=ROLES):
        rfp, _ = RoleFeaturePermission.objects.get_or_create(role=group, feature=feature)
        rfp.can_approve = True
        rfp.save()


def backwards(apps, schema_editor):
    apps.get_model("website", "Feature").objects.filter(key=FEATURE["key"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0063_more_working_permissions"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
