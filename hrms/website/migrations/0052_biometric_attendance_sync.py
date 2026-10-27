"""Biometric (eSSL / eTimeTrackLite) attendance sync.

Adds:
  Employee.is_night_shift            — duty crosses midnight, so the day's
                                       in-time is its LAST punch
  Employee.biometric_device_user_id  — only for staff whose punch-machine
                                       user ID differs from their code
  Attendance.times_locked            — times set by hand (Excel upload or an
                                       approved correction); the sync skips
                                       these days
  BiometricPunch                     — the raw punch feed
  BiometricSyncRun                   — one sync attempt, so the Biometric
                                       Sync page can show the automation is
                                       actually running

Every default is the status quo: nobody is night shift and no day is locked
until something says so, so applying this changes no existing attendance.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0051_raise_for_others_and_register_edit"),
    ]

    operations = [
        migrations.AddField(
            model_name="employee",
            name="is_night_shift",
            field=models.BooleanField(
                default=False,
                help_text="Duty runs across midnight, so a day's in-time is that day's LAST "
                          "punch and its out-time the NEXT day's first punch. A Shift Roster "
                          "entry whose timings cross midnight overrides this for those dates.",
                verbose_name="Night shift employee",
            ),
        ),
        migrations.AddField(
            model_name="employee",
            name="biometric_device_user_id",
            field=models.CharField(
                blank=True, max_length=50, null=True,
                help_text="Only needed when the punch machine's user ID differs from the "
                          "employee code. Leave blank to match on employee code.",
                verbose_name="Biometric device user ID",
            ),
        ),
        migrations.AddField(
            model_name="attendance",
            name="times_locked",
            field=models.BooleanField(
                default=False,
                help_text="In/out time came from an Excel upload or an approved correction, "
                          "not from the punch machine. The biometric sync leaves these alone.",
                verbose_name="Punch times set manually",
            ),
        ),
        migrations.CreateModel(
            name="BiometricPunch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("device_user_id", models.CharField(help_text="DeviceLogs.UserId on the eSSL side", max_length=50)),
                ("employee_code", models.CharField(blank=True, help_text="eSSL Employees.EmployeeCode, when the agent could resolve it", max_length=50)),
                ("employee_name", models.CharField(blank=True, max_length=255)),
                ("punch_date", models.DateField()),
                ("punch_time", models.TimeField()),
                ("device_id", models.IntegerField(blank=True, null=True)),
                ("direction", models.CharField(blank=True, help_text="DeviceLogs.Direction / AttDirection, when the device reports one", max_length=32)),
                ("source_log_id", models.BigIntegerField(blank=True, help_text="DeviceLogs.DeviceLogId, for tracing a punch back to eSSL", null=True)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("employee", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="biometric_punches", to="website.employee",
                )),
            ],
            options={
                "ordering": ["punch_date", "punch_time"],
            },
        ),
        migrations.AddIndex(
            model_name="biometricpunch",
            index=models.Index(fields=["employee", "punch_date"], name="website_bio_employe_5add6b_idx"),
        ),
        migrations.AddIndex(
            model_name="biometricpunch",
            index=models.Index(fields=["punch_date"], name="website_bio_punch_d_75acc6_idx"),
        ),
        migrations.AddIndex(
            model_name="biometricpunch",
            index=models.Index(fields=["device_user_id", "punch_date"], name="website_bio_device__c52f8b_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="biometricpunch",
            unique_together={("device_user_id", "punch_date", "punch_time")},
        ),
        migrations.CreateModel(
            name="BiometricSyncRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(choices=[
                    ("agent", "Windows agent push"),
                    ("scheduled", "Scheduled task"),
                    ("manual", "Manual (Biometric Sync page)"),
                    ("command", "Management command"),
                ], default="agent", max_length=20)),
                ("status", models.CharField(choices=[
                    ("running", "Running"),
                    ("success", "Success"),
                    ("failed", "Failed"),
                ], default="running", max_length=20)),
                ("from_date", models.DateField(blank=True, null=True)),
                ("to_date", models.DateField(blank=True, null=True)),
                ("punches_received", models.IntegerField(default=0)),
                ("punches_stored", models.IntegerField(default=0, help_text="New punches; the rest were already held from an earlier overlapping run.")),
                ("punches_unmatched", models.IntegerField(default=0, help_text="Punches whose device user ID matched no employee.")),
                ("attendance_created", models.IntegerField(default=0)),
                ("attendance_updated", models.IntegerField(default=0)),
                ("attendance_skipped", models.IntegerField(default=0, help_text="Days left alone: manual times, finalized payroll, or before joining.")),
                ("message", models.TextField(blank=True)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "ordering": ["-started_at"],
            },
        ),
        migrations.AddIndex(
            model_name="biometricsyncrun",
            index=models.Index(fields=["-started_at"], name="website_bio_started_772e63_idx"),
        ),
    ]
