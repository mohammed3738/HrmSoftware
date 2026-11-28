"""Relabel existing payroll runs: a 27 Mar - 26 Apr run is April's payroll
(the month picked on the Create form), but was stored and shown as March.
Label only -- no dates or amounts change."""
from django.db import migrations


def forwards(apps, schema_editor):
    PayrollRun = apps.get_model("website", "PayrollRun")
    PayrollRecord = apps.get_model("website", "PayrollRecord")
    for run in PayrollRun.objects.exclude(end_date__isnull=True):
        month = run.end_date.replace(day=1)
        if run.month != month:
            PayrollRun.objects.filter(pk=run.pk).update(month=month)
        PayrollRecord.objects.filter(payroll=run).update(month_display=month.strftime("%b %Y"))


def backwards(apps, schema_editor):
    PayrollRun = apps.get_model("website", "PayrollRun")
    PayrollRecord = apps.get_model("website", "PayrollRecord")
    for run in PayrollRun.objects.exclude(start_date__isnull=True):
        month = run.start_date.replace(day=1)
        PayrollRun.objects.filter(pk=run.pk).update(month=month)
        PayrollRecord.objects.filter(payroll=run).update(month_display=month.strftime("%b %Y"))


class Migration(migrations.Migration):
    dependencies = [("website", "0059_attendance_auto_absent")]
    operations = [migrations.RunPython(forwards, backwards)]
