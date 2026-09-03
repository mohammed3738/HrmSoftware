from django.db import migrations

from website.permissions_registry import FEATURES, SEED_GRANTS, SYSTEM_ROLES

_DEPARTMENT_FEATURE = next(row for row in FEATURES if row["key"] == "department_management")


def seed_department_feature(apps, schema_editor):
    """Register the 'department_management' Feature + its
    RoleFeaturePermission rows. Migration 0019 seeded the original matrix,
    so this only adds the one new feature rather than re-seeding."""
    Group = apps.get_model("auth", "Group")
    Feature = apps.get_model("website", "Feature")
    RoleFeaturePermission = apps.get_model("website", "RoleFeaturePermission")

    feature, _ = Feature.objects.get_or_create(
        key=_DEPARTMENT_FEATURE["key"], defaults=_DEPARTMENT_FEATURE,
    )

    for role_name in SYSTEM_ROLES:
        group, _ = Group.objects.get_or_create(name=role_name)
        rfp, _ = RoleFeaturePermission.objects.get_or_create(role=group, feature=feature)
        for action in ("view", "edit", "approve"):
            granted = SEED_GRANTS.get(("department_management", action), ())
            setattr(rfp, f"can_{action}", role_name in granted)
        rfp.save()


def unseed_department_feature(apps, schema_editor):
    Feature = apps.get_model("website", "Feature")
    Feature.objects.filter(key="department_management").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0027_employee_manager_employee_reporting_person_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_department_feature, unseed_department_feature),
    ]
