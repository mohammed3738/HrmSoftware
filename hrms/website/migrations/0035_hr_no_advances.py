"""Take advances away from HR.

Advances are a payroll matter, so HR administers none of them — no viewing
the company's advances, no creating or editing them. Everyone, HR included,
can still see their OWN advance: advance_list and advance_detail scope to
the signed-in employee's records when the viewer holds no advances:view
grant, so self-service doesn't depend on a company-wide permission.

Re-seeds the whole matrix from SEED_GRANTS. Reversing hands HR back the
advances grants it held before.
"""
from django.db import migrations

from website.permissions_registry import SEED_GRANTS, SYSTEM_ROLES

_ACTIONS = ("view", "create", "edit", "approve")

_PREVIOUS_HR_GRANTS = {
    ("advances", "view"),
    ("advances", "edit"),
}


def _reseed(apps, grants):
    Group = apps.get_model("auth", "Group")
    Feature = apps.get_model("website", "Feature")
    RoleFeaturePermission = apps.get_model("website", "RoleFeaturePermission")

    for role_name in SYSTEM_ROLES:
        group, _ = Group.objects.get_or_create(name=role_name)
        for feature in Feature.objects.all():
            rfp, _ = RoleFeaturePermission.objects.get_or_create(role=group, feature=feature)
            for action in _ACTIONS:
                setattr(rfp, f"can_{action}", role_name in grants.get((feature.key, action), ()))
            rfp.save()


def remove_hr_advances(apps, schema_editor):
    _reseed(apps, SEED_GRANTS)


def restore_hr_advances(apps, schema_editor):
    grants = {key: tuple(value) for key, value in SEED_GRANTS.items()}
    for key in _PREVIOUS_HR_GRANTS:
        grants[key] = tuple(sorted(set(grants.get(key, ())) | {"HR"}))
    _reseed(apps, grants)


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0034_restrict_hr_permissions"),
    ]

    operations = [
        migrations.RunPython(remove_hr_advances, restore_hr_advances),
    ]
