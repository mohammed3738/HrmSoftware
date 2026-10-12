"""HR sees only its own attendance-correction and comp-off requests: drop
HR's company-wide view on both. Everyone still sees their own requests
without any grant (see attendance_correction_requests_list and
comp_off_requests_list)."""
from django.db import migrations

FEATURES = ("attendance_corrections", "comp_off")


def hr_own_only(apps, schema_editor):
    RoleFeaturePermission = apps.get_model("website", "RoleFeaturePermission")
    RoleFeaturePermission.objects.filter(role__name="HR", feature__key__in=FEATURES).update(can_view=False)


def hr_sees_all(apps, schema_editor):
    RoleFeaturePermission = apps.get_model("website", "RoleFeaturePermission")
    RoleFeaturePermission.objects.filter(role__name="HR", feature__key__in=FEATURES).update(can_view=True)


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0043_archive_records_permission"),
    ]

    operations = [
        migrations.RunPython(hr_own_only, hr_sees_all),
    ]
