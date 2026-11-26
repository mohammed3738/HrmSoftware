"""Create becomes its own, tickable right on nine more features:

  Departments, Companies, Branches, Holiday Calendar, Shift Roster,
  Payroll (new run), Advances, Announcements, User Accounts.

Until now Edit covered adding as well as changing. Edit still implies
Create (see utils.permissions.has_feature_permission), so every role that
holds Edit starts out with Create ticked too: nobody gains or loses
anything until a Super Admin ticks or unticks a box.
"""
from django.db import migrations

FEATURES = [
    "department_management", "company_management", "branch_management", "holiday_calendar",
    "shift_roster", "payroll", "advances", "announcements", "user_accounts",
]


def add_create(apps, schema_editor):
    Feature = apps.get_model("website", "Feature")
    RoleFeaturePermission = apps.get_model("website", "RoleFeaturePermission")
    for key in FEATURES:
        feature = Feature.objects.filter(key=key).first()
        if feature is None:
            continue
        feature.has_create = True
        feature.save(update_fields=["has_create"])
        RoleFeaturePermission.objects.filter(feature=feature, can_edit=True).update(can_create=True)


def remove_create(apps, schema_editor):
    Feature = apps.get_model("website", "Feature")
    RoleFeaturePermission = apps.get_model("website", "RoleFeaturePermission")
    Feature.objects.filter(key__in=FEATURES).update(has_create=False)
    RoleFeaturePermission.objects.filter(feature__key__in=FEATURES).update(can_create=False)


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0061_employee_week_off_days"),
    ]

    operations = [
        migrations.RunPython(add_create, remove_create),
    ]
