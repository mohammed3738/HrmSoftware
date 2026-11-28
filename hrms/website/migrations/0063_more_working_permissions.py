"""Four more boxes on Roles & Permissions that now do something:

  Payroll           -> Approve : finalize a payroll run (was part of Edit)
  Employee Changes  -> View    : see the change-request queue
  Archive Records   -> View    : see the "Archived" / "All" tabs on lists
  Advances          -> Approve : approve an advance created by someone
                                 without it; until then it isn't deducted

Each starts with exactly the roles that could already do that thing, so
nobody gains or loses anything until a Super Admin ticks or unticks a box.

Also: advances get two new statuses (awaiting approval, rejected).
"""
from django.db import migrations, models

STAFF = ("Super Admin", "Admin", "Payroll Officer", "HR")
NOT_HR = ("Super Admin", "Admin", "Payroll Officer")

NEW = [
    # feature, flag, action, holders: (feature, action) whose holders get it, or role names
    ("payroll", "has_approve", "approve", [("payroll", "edit")]),
    ("employee_change_approval", "has_view", "view", STAFF),
    ("archive_records", "has_view", "view", STAFF),
    ("advances", "has_approve", "approve", [("advances", "edit")]),
]


def forwards(apps, schema_editor):
    Feature = apps.get_model("website", "Feature")
    RoleFeaturePermission = apps.get_model("website", "RoleFeaturePermission")
    Group = apps.get_model("auth", "Group")
    for key, flag, action, source in NEW:
        feature = Feature.objects.filter(key=key).first()
        if feature is None:
            continue
        setattr(feature, flag, True)
        feature.save(update_fields=[flag])
        if source and isinstance(source[0], tuple):
            holders = set()
            for src_key, src_action in source:
                holders |= set(RoleFeaturePermission.objects.filter(
                    feature__key=src_key, **{f"can_{src_action}": True},
                ).values_list("role_id", flat=True))
        else:
            holders = set(Group.objects.filter(name__in=source).values_list("id", flat=True))
        for group in Group.objects.filter(id__in=holders):
            rfp, _ = RoleFeaturePermission.objects.get_or_create(role=group, feature=feature)
            setattr(rfp, f"can_{action}", True)
            rfp.save()


def backwards(apps, schema_editor):
    Feature = apps.get_model("website", "Feature")
    RoleFeaturePermission = apps.get_model("website", "RoleFeaturePermission")
    for key, flag, action, _ in NEW:
        Feature.objects.filter(key=key).update(**{flag: False})
        RoleFeaturePermission.objects.filter(feature__key=key).update(**{f"can_{action}": False})


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0062_create_rights_on_more_features"),
    ]

    operations = [
        migrations.AlterField(
            model_name="advancemaster",
            name="status",
            field=models.CharField(
                choices=[("awaiting_approval", "Awaiting approval"), ("active", "Active"),
                         ("completed", "Completed"), ("rejected", "Rejected")],
                default="active", max_length=20,
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
