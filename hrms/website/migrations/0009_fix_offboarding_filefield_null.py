from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('website', '0008_employee_salutation_choices'),
    ]

    operations = [
        migrations.AlterField(
            model_name='offboarding',
            name='other_documents',
            field=models.FileField(blank=True, null=True, upload_to='offboarding/other_documents/', verbose_name='Other Documents'),
        ),
        migrations.AlterField(
            model_name='offboarding',
            name='fnf_documents',
            field=models.FileField(blank=True, null=True, upload_to='offboarding/fnf/', verbose_name='FNF Document'),
        ),
    ]
