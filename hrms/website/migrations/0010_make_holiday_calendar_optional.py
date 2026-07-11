from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('website', '0009_fix_offboarding_filefield_null'),
    ]

    operations = [
        # Drop the old composite unique_together constraint first
        migrations.AlterUniqueTogether(
            name='holiday',
            unique_together=set(),
        ),
        # Drop the composite index that referenced holiday_calendar
        migrations.RemoveIndex(
            model_name='holiday',
            name='website_hol_holiday_a906c7_idx',
        ),
        # Make holiday_calendar nullable (SET_NULL so existing rows keep their ref)
        migrations.AlterField(
            model_name='holiday',
            name='holiday_calendar',
            field=models.ForeignKey(
                'website.HolidayCalendar',
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='holidays',
                null=True,
                blank=True,
            ),
        ),
        # Add a simple uniqueness constraint on holiday_date alone
        migrations.AddConstraint(
            model_name='holiday',
            constraint=models.UniqueConstraint(
                fields=['holiday_date'],
                name='unique_holiday_date',
            ),
        ),
    ]
