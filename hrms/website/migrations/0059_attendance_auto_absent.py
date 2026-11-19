from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0058_seed_field_duty_feature"),
    ]

    operations = [
        migrations.AddField(
            model_name="attendance",
            name="auto_absent",
            field=models.BooleanField(
                default=False,
                verbose_name="Marked absent at start of day",
                help_text="Created as Absent when the day began; replaced by the real status once a punch arrives.",
            ),
        ),
    ]
