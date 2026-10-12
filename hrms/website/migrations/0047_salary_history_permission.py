"""Seeing everyone's salary history becomes its own permission, held by
everyone who could open Salary History before (salary_structure:view)
except HR, who now sees only their own."""
from django.db import migrations

FEATURE = {
    "key": "salary_history", "name": "Salary History (all employees)", "category": "Compensation",
    "has_view": True, "has_create": False, "has_edit": False, "has_approve": False, "sort_order": 15,
}


def add_feature(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Feature = apps.get_model("website", "Feature")
    RoleFeaturePermission = apps.get_model("website", "RoleFeaturePermission")

    feature, _ = Feature.objects.update_or_create(
        key=FEATURE["key"], defaults={k: v for k, v in FEATURE.items() if k != "key"},
    )
    viewers = set(
        RoleFeaturePermission.objects.filter(feature__key="salary_structure", can_view=True)
        .values_list("role_id", flat=True)
    )
    for group in Group.objects.all():
        rfp, _ = RoleFeaturePermission.objects.get_or_create(role=group, feature=feature)
        rfp.can_view = group.id in viewers and group.name != "HR"
        rfp.save()


def remove_feature(apps, schema_editor):
    apps.get_model("website", "Feature").objects.filter(key=FEATURE["key"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0046_leave_type_optional"),
    ]

    operations = [
        migrations.RunPython(add_feature, remove_feature),
    ]
