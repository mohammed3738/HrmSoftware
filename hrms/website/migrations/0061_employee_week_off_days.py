"""Employee weekly off: one day -> one or more days.

week_off_day (a single weekday number) becomes week_off_days ("5,6" for
Saturday + Sunday). Each employee's existing day is carried over, so
nobody's weekly off changes by deploying this.
"""
from django.db import migrations, models


def copy_forward(apps, schema_editor):
    Employee = apps.get_model("website", "Employee")
    for emp in Employee.objects.exclude(week_off_day__isnull=True).only("id", "week_off_day"):
        Employee.objects.filter(pk=emp.pk).update(week_off_days=str(emp.week_off_day))


def copy_back(apps, schema_editor):
    # Going back keeps only the first day; the old field held one.
    Employee = apps.get_model("website", "Employee")
    for emp in Employee.objects.exclude(week_off_days="").only("id", "week_off_days"):
        first = emp.week_off_days.split(",")[0].strip()
        if first.isdigit():
            Employee.objects.filter(pk=emp.pk).update(week_off_day=int(first))


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0060_payroll_month_is_ending_month"),
    ]

    operations = [
        migrations.AddField(
            model_name="employee",
            name="week_off_days",
            field=models.CharField(
                blank=True, default="", max_length=20, verbose_name="Weekly Off Days",
                help_text="Overrides the company's default weekly off -- one or more days "
                          "(e.g. Saturday and Sunday, or Friday and Saturday). Leave blank to "
                          "use the company default.",
            ),
        ),
        migrations.RunPython(copy_forward, copy_back),
        migrations.RemoveField(model_name="employee", name="week_off_day"),
    ]
