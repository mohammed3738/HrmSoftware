from django.db import migrations


def seed(apps, schema_editor):
    Feature = apps.get_model("website", "Feature")
    Group = apps.get_model("auth", "Group")
    Grant = apps.get_model("website", "RoleFeaturePermission")
    feature, _ = Feature.objects.get_or_create(key="executive_dashboard", defaults={
        "name": "Executive workforce and payroll summaries", "category": "Administration",
        "has_view": True, "has_create": False, "has_edit": False, "has_approve": False, "sort_order": 31,
    })
    for name in ("Director", "Super Admin"):
        group, _ = Group.objects.get_or_create(name=name)
        Grant.objects.update_or_create(role=group, feature=feature, defaults={"can_view": True})


def unseed(apps, schema_editor):
    apps.get_model("website", "Feature").objects.filter(key="executive_dashboard").delete()


class Migration(migrations.Migration):
    dependencies = [("website", "0059_attendance_auto_absent")]
    operations = [migrations.RunPython(seed, unseed)]
