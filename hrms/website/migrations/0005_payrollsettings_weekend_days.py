from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('website', '0004_attendance_unique_employee_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='payrollsettings',
            name='weekend_days',
            field=models.CharField(
                choices=[('sat_sun', 'Saturday & Sunday'), ('sun', 'Sunday Only')],
                default='sat_sun',
                help_text='Which days count as weekends (not worked).',
                max_length=10,
                verbose_name='Weekend Days',
            ),
        ),
    ]
