"""Register the 'field_duty' Feature and its role grants.

Separate from 0057 (which creates the table) so the schema change and the
permission seeding can be reasoned about -- and reversed -- independently.
Follows 0028's pattern: read the live registry, seed only this one feature,
and pass only the fields the Feature model had at this point in history.
"""
from django.db import migrations

from website.permissions_registry import FEATURES, SEED_GRANTS, SYSTEM_ROLES

_FIELD_DUTY_FEATURE = next(row for row in FEATURES if row["key"] == "field_duty")


def _defaults_for(model, row):
    known = {f.name for f in model._meta.get_fields()}
    return {k: v for k, v in row.items() if k in known and k != "key"}


def seed_field_duty_feature(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Feature = apps.get_model("website", "Feature")
    RoleFeaturePermission = apps.get_model("website", "RoleFeaturePermission")

    feature, _ = Feature.objects.get_or_create(
        key=_FIELD_DUTY_FEATURE["key"], defaults=_defaults_for(Feature, _FIELD_DUTY_FEATURE),
    )

    for role_name in SYSTEM_ROLES:
        group, _ = Group.objects.get_or_create(name=role_name)
        rfp, _ = RoleFeaturePermission.objects.get_or_create(role=group, feature=feature)
        for action in ("view", "create", "edit", "approve"):
            granted = SEED_GRANTS.get(("field_duty", action), ())
            setattr(rfp, f"can_{action}", role_name in granted)
        rfp.save()


def unseed_field_duty_feature(apps, schema_editor):
    Feature = apps.get_model("website", "Feature")
    Feature.objects.filter(key="field_duty").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0057_fieldduty"),
    ]

    operations = [
        migrations.RunPython(seed_field_duty_feature, unseed_field_duty_feature),
    ]
