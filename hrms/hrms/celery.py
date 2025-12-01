from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hrms.settings')

app = Celery('hrms')
app.conf.enable_utc = False
app.conf.update(timezone='Asia/Kolkata')

app.config_from_object('django.conf:settings', namespace='CELERY')

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
}

app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
