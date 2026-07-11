from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('website', '0010_make_holiday_calendar_optional'),
    ]

    operations = [
        # Remove the old composite unique_together (covers branch+date when branch not null)
        migrations.AlterUniqueTogether(
            name='halfdayscenario',
            unique_together=set(),
        ),
        # Remove old composite index
        migrations.RemoveIndex(
            model_name='halfdayscenario',
            name='website_hal_branch__21bfdb_idx',
        ),
        # Make branch nullable (SET_NULL so existing rows keep their branch)
        migrations.AlterField(
            model_name='halfdayscenario',
            name='branch',
            field=models.ForeignKey(
                'website.Branch',
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='half_day_scenarios',
                null=True,
                blank=True,
            ),
        ),
        # Partial unique: only one scenario per branch+date when branch is set
        migrations.AddConstraint(
            model_name='halfdayscenario',
            constraint=models.UniqueConstraint(
                fields=['branch', 'scenario_date'],
                condition=models.Q(branch__isnull=False),
                name='unique_branch_scenario_date',
            ),
        ),
        # Partial unique: only one "all-branches" scenario per date
        migrations.AddConstraint(
            model_name='halfdayscenario',
            constraint=models.UniqueConstraint(
                fields=['scenario_date'],
                condition=models.Q(branch__isnull=True),
                name='unique_allbranch_scenario_date',
            ),
        ),
        # Restore branch+scenario_date index (branch can now be null)
        migrations.AddIndex(
            model_name='halfdayscenario',
            index=models.Index(fields=['branch', 'scenario_date'], name='hal_branch_scenario_idx'),
        ),
    ]
