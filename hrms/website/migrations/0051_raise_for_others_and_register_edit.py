"""Four new, separately tickable rights on Roles & Permissions:

  Leave Management        -> Create : apply leave on someone else's behalf
  Attendance Corrections  -> Create : raise a correction for someone else's day
  Comp-Off                -> Edit   : raise a comp-off for someone else
  Attendance Register     -> Edit   : change a day's status from the register

Each starts out held by exactly the roles that could already do that thing
(through the broader permission it used to piggy-back on), so nobody gains
or loses anything until an admin ticks or unticks a box.
"""
from django.db import migrations

NEW_ACTIONS = [
    # feature, flag on Feature, action granted, [(feature, action) that used to allow it]
    ("leave_management", "has_create", "create", [("leave_management", "edit"), ("leave_management", "approve")]),
    ("attendance_corrections", "has_create", "create", [("attendance_corrections", "view")]),
    ("comp_off", "has_edit", "edit", [("comp_off", "approve")]),
    ("attendance_register", "has_edit", "edit", [("attendance_review", "edit")]),
]


def add_actions(apps, schema_editor):
    Feature = apps.get_model("website", "Feature")
    RoleFeaturePermission = apps.get_model("website", "RoleFeaturePermission")
    Group = apps.get_model("auth", "Group")

    for key, flag, action, sources in NEW_ACTIONS:
        feature = Feature.objects.filter(key=key).first()
        if feature is None:
            continue
        setattr(feature, flag, True)
        feature.save(update_fields=[flag])

        holders = set()
        for src_key, src_action in sources:
            holders |= set(RoleFeaturePermission.objects.filter(
                feature__key=src_key, **{f"can_{src_action}": True},
            ).values_list("role_id", flat=True))
        for group in Group.objects.all():
            rfp, _ = RoleFeaturePermission.objects.get_or_create(role=group, feature=feature)
            setattr(rfp, f"can_{action}", group.id in holders)
            rfp.save()


def remove_actions(apps, schema_editor):
    Feature = apps.get_model("website", "Feature")
    RoleFeaturePermission = apps.get_model("website", "RoleFeaturePermission")
    for key, flag, action, _sources in NEW_ACTIONS:
        Feature.objects.filter(key=key).update(**{flag: False})
        RoleFeaturePermission.objects.filter(feature__key=key).update(**{f"can_{action}": False})


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0050_holiday_branches"),
    ]

    operations = [
        migrations.RunPython(add_actions, remove_actions),
    ]
