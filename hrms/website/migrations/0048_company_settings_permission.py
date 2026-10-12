"""The settings hub (payroll, leave and attendance rules) gets its own
permission. It used to be open to any logged-in user (the save endpoints)
or to every global-access role (the hub); now it's held by the roles that
may broadcast settings -- Super Admin, Admin and Payroll Officer, not HR."""
from django.db import migrations

FEATURE = {
    "key": "company_settings", "name": "Company Settings", "category": "Administration",
    "has_view": True, "has_create": False, "has_edit": True, "has_approve": False, "sort_order": 5,
}


def add_feature(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Feature = apps.get_model("website", "Feature")
    RoleFeaturePermission = apps.get_model("website", "RoleFeaturePermission")

    feature, _ = Feature.objects.update_or_create(
        key=FEATURE["key"], defaults={k: v for k, v in FEATURE.items() if k != "key"},
    )
    holders = set(
        RoleFeaturePermission.objects.filter(feature__key="company_settings_broadcast", can_edit=True)
        .values_list("role_id", flat=True)
    )
    for group in Group.objects.all():
        rfp, _ = RoleFeaturePermission.objects.get_or_create(role=group, feature=feature)
        allowed = group.id in holders and group.name != "HR"
        rfp.can_view = rfp.can_edit = allowed
        rfp.save()


def remove_feature(apps, schema_editor):
    apps.get_model("website", "Feature").objects.filter(key=FEATURE["key"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0047_salary_history_permission"),
    ]

    operations = [
        migrations.RunPython(add_feature, remove_feature),
    ]
