from django.db import migrations


def remove_duplicate_attendance(apps, schema_editor):
    """Keep the latest attendance record per (employee, date), delete the rest."""
    Attendance = apps.get_model('website', 'Attendance')
    db_alias = schema_editor.connection.alias

    seen = set()
    for record in Attendance.objects.using(db_alias).order_by('employee_id', 'date', '-id'):
        key = (record.employee_id, record.date)
        if key in seen:
            record.delete()
        else:
            seen.add(key)


class Migration(migrations.Migration):

    dependencies = [
        ('website', '0003_alter_employee_emergency_contact_mobile2'),
    ]

    operations = [
        migrations.RunPython(remove_duplicate_attendance, migrations.RunPython.noop),
        migrations.AlterUniqueTogether(
            name='attendance',
            unique_together={('employee', 'date')},
        ),
    ]
