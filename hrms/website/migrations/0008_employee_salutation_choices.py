# Generated migration - adds choices to Employee.salutation (no DB schema change)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('website', '0007_add_lwp_overridden_to_leavebalance'),
    ]

    operations = [
        migrations.AlterField(
            model_name='employee',
            name='salutation',
            field=models.CharField(
                blank=True,
                choices=[
                    ('Mr.', 'Mr.'),
                    ('Mrs.', 'Mrs.'),
                    ('Ms.', 'Ms.'),
                    ('Dr.', 'Dr.'),
                    ('Prof.', 'Prof.'),
                ],
                max_length=10,
                null=True,
                verbose_name='Salutation',
            ),
        ),
    ]
