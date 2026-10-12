"""The Attendance Register gets its own view permission, held by everyone
who could open it before (attendance_review:view) except HR."""
from django.db import migrations

FEATURE = {
    "key": "attendance_register", "name": "Attendance Register", "category": "Attendance & Scheduling",
    "has_view": True, "has_create": False, "has_edit": False, "has_approve": False, "sort_order": 25,
}


def add_register_feature(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Feature = apps.get_model("website", "Feature")
    RoleFeaturePermission = apps.get_model("website", "RoleFeaturePermission")

    feature, _ = Feature.objects.update_or_create(
        key=FEATURE["key"], defaults={k: v for k, v in FEATURE.items() if k != "key"},
    )
    viewers = set(
        RoleFeaturePermission.objects.filter(feature__key="attendance_review", can_view=True)
        .values_list("role_id", flat=True)
    )
    for group in Group.objects.all():
        rfp, _ = RoleFeaturePermission.objects.get_or_create(role=group, feature=feature)
        rfp.can_view = group.id in viewers and group.name != "HR"
        rfp.save()


def remove_register_feature(apps, schema_editor):
    apps.get_model("website", "Feature").objects.filter(key=FEATURE["key"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0044_hr_own_requests_only"),
    ]

    operations = [
        migrations.RunPython(add_register_feature, remove_register_feature),
    ]
