# your_project/celery.py
from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from django.conf import settings
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hrms.settings')

# Create a Celery instance
app = Celery('hrms')
app.conf.enable_utc = False

app.conf.update(timezone= 'Asia/Kolkata')
# Load configuration from Django settings with the prefix 'CELERY_'
app.config_from_object('django.conf:settings', namespace='CELERY')



app.conf.beat_schedule = {
    'check-leaving-status-every-minute': {
        'task': 'website.tasks.check_and_update_status',
        'schedule': crontab(minute='*'),  # Runs every minute
    },
}


# app.conf.beat_schedule.update({
#     'process-salary-increments-daily': {
#         'task': 'website.tasks.process_salary_increments',
#         'schedule': crontab(minute='*'),  # Every midnight
#     },
# })

CELERY_BEAT_SCHEDULE = {
    "process-salary-increments-every-midnight": {
        "task": "salary.tasks.process_salary_increments",
        "schedule": crontab(hour=0, minute=1),
    }
}



# ✅ Schedule for monthly leave reset (runs every 1st day at 2 AM)
app.conf.beat_schedule = {
    'reset-monthly-leave-balances': {
        'task': 'website.tasks.reset_monthly_leave_balances_task',
        'schedule': crontab(hour=2, minute=0, day_of_month=1),
    },
}


# Automatically discover tasks in all Django apps
app.autodiscover_tasks()
@app.task(bind = True)
def debug_task(self):
    print(f'Request: {self.request!r}')