"""Archiving / restoring any record now needs "Archive & Restore Records",
held by Super Admin, Admin and Payroll Officer -- not HR."""
from django.db import migrations

FEATURE = {
    "key": "archive_records", "name": "Archive & Restore Records", "category": "Administration",
    "has_view": False, "has_create": False, "has_edit": True, "has_approve": False, "sort_order": 60,
}


def add_archive_feature(apps, schema_editor):
    """Grant it to the roles that may delete employees -- i.e. not HR (see
    0040). Customisations made on the Roles & Permissions page are respected
    because it copies the current grants."""
    Group = apps.get_model("auth", "Group")
    Feature = apps.get_model("website", "Feature")
    RoleFeaturePermission = apps.get_model("website", "RoleFeaturePermission")

    feature, _ = Feature.objects.update_or_create(
        key=FEATURE["key"], defaults={k: v for k, v in FEATURE.items() if k != "key"},
    )
    archivers = set(
        RoleFeaturePermission.objects.filter(feature__key="employee_delete", can_edit=True)
        .values_list("role_id", flat=True)
    )
    for group in Group.objects.all():
        rfp, _ = RoleFeaturePermission.objects.get_or_create(role=group, feature=feature)
        rfp.can_edit = group.id in archivers and group.name != "HR"
        rfp.save()


def remove_archive_feature(apps, schema_editor):
    apps.get_model("website", "Feature").objects.filter(key=FEATURE["key"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0042_employee_onboarding"),
    ]

    operations = [
        migrations.RunPython(add_archive_feature, remove_archive_feature),
    ]
