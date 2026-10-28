from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from celery.schedules import crontab
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hrms.settings')

app = Celery('hrms')
app.conf.enable_utc = False
app.conf.update(timezone='Asia/Kolkata')

app.config_from_object('django.conf:settings', namespace='CELERY')


def _biometric_sync_hours():
    """Hours the biometric sync runs at, from BIOMETRIC_SYNC_HOURS (see
    hrms/settings.py). Crontab wants a string like '10,12,14'; an unreadable
    setting falls back to the default rather than taking beat down."""
    raw = getattr(settings, 'BIOMETRIC_SYNC_HOURS', '') or ''
    hours = []
    for part in raw.split(','):
        part = part.strip()
        if part.isdigit() and 0 <= int(part) <= 23:
            hours.append(str(int(part)))
    return ','.join(dict.fromkeys(hours)) or '10,12,14,16,18,20,22,0'

# 🟢 Correct combined schedule
app.conf.beat_schedule = {
    'check-leaving-status-every-minute': {
        'task': 'website.tasks.check_and_update_status',
        'schedule': crontab(minute='*'),
    },

    'process-salary-increments-every-minute': {  
        'task': 'website.tasks.process_salary_increments',
        'schedule': crontab(minute='*/1'),  # for testing
    },

    'reset-monthly-leave-balances': {
        'task': 'website.tasks.reset_monthly_leave_balances_task',
        'schedule': crontab(hour=2, minute=0, day_of_month=1),
    },
    'process-monthly-leave-balance': {
        'task': 'website.tasks.auto_process_all_companies_leave_balance',
        'schedule': crontab(hour=23, minute=55, day_of_month=25),  # ✅ Fixed: 25 not '25'
    },

    'backfill-holiday-attendance-daily': {
        'task': 'website.tasks.backfill_holiday_attendance_task',
        'schedule': crontab(hour=1, minute=0),
    },

    # Biometric (eSSL) punches -> attendance in/out times. Every second hour
    # from 10:00, which BIOMETRIC_SYNC_HOURS in .env can change without
    # touching this file. Midnight is in the default list on purpose: a night
    # shift's out-punch lands after it, and that run is what closes the
    # previous day.
    # Finished shift rotations leave the active roster, so it stays readable
    # as night duty rotates. Attendance for those dates is untouched -- see
    # website/services/shift_roster_cleanup.py.
    'archive-past-shift-assignments': {
        'task': 'website.tasks.archive_past_shift_assignments_task',
        'schedule': crontab(hour=1, minute=30),
    },

    'sync-biometric-attendance': {
        'task': 'website.tasks.sync_biometric_attendance_task',
        'schedule': crontab(minute=0, hour=_biometric_sync_hours()),
    },

}


app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
