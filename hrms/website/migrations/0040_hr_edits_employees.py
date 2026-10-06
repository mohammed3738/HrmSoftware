"""HR may now edit employee details; deleting (archiving) an employee becomes
its own "Delete Employees" permission.

Unlike 0034 this does not re-seed the whole matrix, so any grants changed by
hand on the Roles & Permissions page are kept. "Delete Employees" goes to
whichever roles could edit employees before this migration -- deleting used
to come with that permission -- and HR then gets Employee Records > Edit.
"""
from django.db import migrations

FEATURE = {
    "key": "employee_delete", "name": "Delete Employees", "category": "Employee Lifecycle",
    "has_view": False, "has_create": False, "has_edit": True, "has_approve": False, "sort_order": 12,
}


def forwards(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Feature = apps.get_model("website", "Feature")
    RoleFeaturePermission = apps.get_model("website", "RoleFeaturePermission")

    records = Feature.objects.filter(key="employee_records").first()
    delete_feature, _ = Feature.objects.update_or_create(
        key=FEATURE["key"], defaults={k: v for k, v in FEATURE.items() if k != "key"},
    )
    could_edit = set()
    if records:
        could_edit = set(
            RoleFeaturePermission.objects.filter(feature=records, can_edit=True).values_list("role_id", flat=True)
        )
    for group in Group.objects.all():
        rfp, _ = RoleFeaturePermission.objects.get_or_create(role=group, feature=delete_feature)
        # HR never gets delete. (On a fresh database the earlier seeding
        # migrations read the current registry, so HR can already edit here.)
        rfp.can_edit = group.id in could_edit and group.name != "HR"
        rfp.save()

    hr = Group.objects.filter(name="HR").first()
    if hr and records:
        rfp, _ = RoleFeaturePermission.objects.get_or_create(role=hr, feature=records)
        rfp.can_edit = True
        rfp.save()


def backwards(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Feature = apps.get_model("website", "Feature")
    RoleFeaturePermission = apps.get_model("website", "RoleFeaturePermission")

    hr = Group.objects.filter(name="HR").first()
    if hr:
        RoleFeaturePermission.objects.filter(role=hr, feature__key="employee_records").update(can_edit=False)
    Feature.objects.filter(key=FEATURE["key"]).delete()


class Migration(migrations.Migration):
    dependencies = [("website", "0039_alter_auditlog_action")]
    operations = [migrations.RunPython(forwards, backwards)]
