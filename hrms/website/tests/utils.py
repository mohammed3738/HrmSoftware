from website.models import Attendance
from datetime import time

def create_attendance(employee, date, count=1, late=0):
    """
    Create attendance and FORCE status calculation
    (Django create() does not persist calculated fields reliably)
    """

    if count == 1:
        in_time = time(9, 0)
        out_time = time(18, 0)
    elif count == 0.5:
        in_time = time(9, 0)
        out_time = time(15, 0)
    else:
        in_time = None
        out_time = None

    att = Attendance.objects.create(
        employee=employee,
        date=date,
        in_time=in_time,
        out_time=out_time,
        late=late,
    )

    # 🔥 FORCE calculation after save
    if in_time and out_time:
        att.calculate_status()
        att.save(update_fields=["status", "count", "late"])

    return att
