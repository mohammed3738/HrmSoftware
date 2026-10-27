"""Rebuild attendance in/out times from biometric punches, by hand.

Three things this is for:

  Backfilling after setup. The agent's first run pushes months of history
  in; this turns a chosen range of it into attendance:
      python manage.py sync_biometric_attendance --from 2026-09-01 --to 2026-09-30

  Checking the rules against reality before trusting them:
      python manage.py sync_biometric_attendance --from 2026-10-23 --to 2026-10-23 --dry-run

  Pulling straight from the eSSL SQL Server, from a machine that can
  actually reach it (the development PC on the same LAN -- the Ubuntu
  server cannot, which is why the agent pushes):
      python manage.py sync_biometric_attendance --pull --from 2026-10-01
"""
import datetime

from django.core.management.base import BaseCommand, CommandError

from website.models import BiometricSyncRun, Employee
from website.services import biometric_sync


class Command(BaseCommand):
    help = "Rebuild attendance in/out times from stored biometric punches (or pull them from the eSSL SQL Server first)."

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="from_date", help="First date to rebuild, YYYY-MM-DD. Defaults to BIOMETRIC_SYNC_LOOKBACK_DAYS ago.")
        parser.add_argument("--to", dest="to_date", help="Last date to rebuild, YYYY-MM-DD. Defaults to today.")
        parser.add_argument("--days", type=int,
                            help="Rebuild the last N days (ending today), instead of giving --from. "
                                 "Same flag the Windows agent takes.")
        parser.add_argument("--employee", action="append", dest="employee_codes", default=[],
                            help="Limit to this employee code. Repeatable.")
        parser.add_argument("--pull", action="store_true",
                            help="Read punches from the eSSL SQL Server first (needs pyodbc and a route to it).")
        parser.add_argument("--test-connection", action="store_true", dest="test_connection",
                            help="Check the eSSL SQL Server connection and stop. Reads nothing, writes nothing.")
        parser.add_argument("--force", action="store_true",
                            help="Also overwrite days whose times were set by hand. Days inside a finalized payroll run are still never touched.")
        parser.add_argument("--dry-run", action="store_true",
                            help="Report what the rules would produce, change nothing.")

    def handle(self, *args, **options):
        if options["test_connection"]:
            return self._test_connection()

        from_date = self._parse_date(options["from_date"], "--from")
        to_date = self._parse_date(options["to_date"], "--to") or datetime.date.today()
        if options["days"] is not None:
            if from_date is not None:
                raise CommandError("Give either --days or --from, not both.")
            if options["days"] < 1:
                raise CommandError("--days must be 1 or more.")
            # N days ending today, so --days 1 is today alone.
            from_date = to_date - datetime.timedelta(days=options["days"] - 1)
        if from_date is None:
            from_date = to_date - datetime.timedelta(days=biometric_sync.lookback_days())
        if from_date > to_date:
            raise CommandError("--from cannot be after --to.")

        employees = None
        if options["employee_codes"]:
            employees = list(Employee.objects.filter(employee_code__in=options["employee_codes"]))
            found = {e.employee_code for e in employees}
            missing = set(options["employee_codes"]) - found
            if missing:
                raise CommandError(f"No employee with code: {', '.join(sorted(missing))}")

        if options["dry_run"]:
            return self._dry_run(from_date, to_date, employees)

        if options["pull"]:
            self.stdout.write(f"Pulling punches from the eSSL SQL Server for {from_date} .. {to_date} ...")
            run = biometric_sync.pull_from_sql_server(
                from_date=from_date, to_date=to_date,
                source=BiometricSyncRun.SOURCE_COMMAND, force=options["force"],
            )
        else:
            run = biometric_sync.resync_window(
                from_date=from_date, to_date=to_date, employees=employees,
                source=BiometricSyncRun.SOURCE_COMMAND, force=options["force"],
            )

        self.stdout.write(self.style.SUCCESS(
            f"Run #{run.id} ({run.status}) {from_date} .. {to_date}\n"
            f"  punches considered : {run.punches_received}\n"
            f"  punches newly held : {run.punches_stored}\n"
            f"  unmatched punches  : {run.punches_unmatched}\n"
            f"  attendance created : {run.attendance_created}\n"
            f"  attendance updated : {run.attendance_updated}\n"
            f"  days left alone    : {run.attendance_skipped}"
        ))
        if run.message:
            self.stdout.write(run.message)

    def _dry_run(self, from_date, to_date, employees):
        """Print the in/out time each day would get, without writing. Reads
        the same derive_day_times() the real run does, so what it prints is
        what would happen."""
        from collections import defaultdict

        from website.models import Attendance, BiometricPunch

        punch_rows = BiometricPunch.objects.filter(
            employee__isnull=False,
            punch_date__gte=from_date,
            punch_date__lte=to_date + datetime.timedelta(days=1),
        ).select_related("employee")
        if employees:
            punch_rows = punch_rows.filter(employee__in=employees)

        by_employee = defaultdict(lambda: defaultdict(list))
        people = {}
        for punch in punch_rows.order_by("punch_date", "punch_time"):
            by_employee[punch.employee_id][punch.punch_date].append(punch.punch_time)
            people[punch.employee_id] = punch.employee

        if not people:
            self.stdout.write("No matched punches in that range.")
            return

        existing = {
            (row.employee_id, row.date): row
            for row in Attendance.objects.filter(
                employee_id__in=people, date__gte=from_date, date__lte=to_date,
            )
        }
        resolver = biometric_sync.NightShiftResolver(list(people.values()), from_date, to_date)

        day_count = (to_date - from_date).days + 1
        for employee_id, employee in sorted(people.items(), key=lambda kv: kv[1].employee_code or ""):
            punches = by_employee[employee_id]
            lines = []
            for offset in range(day_count):
                day = from_date + datetime.timedelta(days=offset)
                if day not in punches:
                    continue
                attendance = existing.get((employee_id, day))
                is_night = resolver.is_night(employee, day)
                in_time, out_time = biometric_sync.derive_day_times(
                    day, punches, is_night,
                    existing_in=None if attendance is None else attendance.in_time,
                    existing_out=None if attendance is None else attendance.out_time,
                )
                was = "-" if attendance is None else f"{attendance.in_time or '--'} / {attendance.out_time or '--'}"
                locked = " [manual, would be skipped]" if attendance is not None and attendance.times_locked else ""
                lines.append(
                    f"    {day}  {'night' if is_night else 'day  '}  "
                    f"punches={','.join(str(t)[:5] for t in punches[day])}  "
                    f"now={was}  ->  {in_time or '--'} / {out_time or '--'}{locked}"
                )
            if lines:
                self.stdout.write(f"  {employee.employee_code} {employee.first_name or ''} {employee.last_name or ''}".rstrip())
                self.stdout.write("\n".join(lines))

        self.stdout.write(self.style.WARNING("Dry run: nothing was written."))

    def _test_connection(self):
        """Say whether this machine can read the eSSL SQL Server, and if not,
        which of the several possible reasons it is. Runs one SELECT COUNT and
        writes nothing."""
        from django.conf import settings

        host = getattr(settings, "BIOMETRIC_MSSQL_HOST", "")
        trusted = getattr(settings, "BIOMETRIC_MSSQL_TRUSTED_CONNECTION", False)

        self.stdout.write(f"Host       : {host or '(BIOMETRIC_MSSQL_HOST is not set)'}")
        self.stdout.write(f"Database   : {settings.BIOMETRIC_MSSQL_DATABASE}")
        self.stdout.write(f"Driver     : {settings.BIOMETRIC_MSSQL_DRIVER}")
        self.stdout.write("Login      : " + (
            "Windows (trusted connection)" if trusted
            else f"SQL login {settings.BIOMETRIC_MSSQL_USER!r}"))
        self.stdout.write("")

        if not host:
            raise CommandError(
                "Set BIOMETRIC_MSSQL_HOST in hrms/.env first, e.g.\n"
                "    BIOMETRIC_MSSQL_HOST=192.168.1.135\\SQLEXPRESS\n"
                "Direct pull only works from a machine that can reach that SQL Server."
            )
        try:
            import pyodbc
        except ImportError:
            raise CommandError("pyodbc is not installed in this environment:  pip install pyodbc")

        if settings.BIOMETRIC_MSSQL_DRIVER not in pyodbc.drivers():
            self.stdout.write(self.style.WARNING(
                f"Driver {settings.BIOMETRIC_MSSQL_DRIVER!r} is not installed. Installed: "
                f"{pyodbc.drivers() or '(none)'}"))

        try:
            with pyodbc.connect(biometric_sync.mssql_connection_string(), timeout=15) as connection:
                cursor = connection.cursor()
                cursor.execute("SELECT SUSER_NAME(), DB_NAME()")
                login, database = cursor.fetchone()
                cursor.execute("SELECT COUNT(*), MIN(LogDate), MAX(LogDate) FROM dbo.DeviceLogs")
                total, oldest, newest = cursor.fetchone()
                cursor.execute("SELECT COUNT(*) FROM dbo.Employees WHERE RecordStatus = 1")
                employees = cursor.fetchone()[0]
        except Exception as exc:
            raise CommandError(
                f"Could not read dbo.DeviceLogs: {exc}\n\n"
                "ESSL_INTEGRATION_GUIDE.txt section 10 lists what each SQL error means. The "
                "usual causes from another machine are TCP/IP disabled on the SQL Express "
                "instance, the Windows firewall, or Windows Authentication not applying across "
                "machines (use the login eTimeTrackLite itself uses instead)."
            )

        self.stdout.write(self.style.SUCCESS(
            f"Connected as {login!r} to {database!r}\n"
            f"  punches held    : {total} ({oldest} .. {newest})\n"
            f"  active employees: {employees}"
        ))
        if not total:
            self.stdout.write(self.style.WARNING(
                "dbo.DeviceLogs is empty -- is this the database the devices write to?"))

    @staticmethod
    def _parse_date(value, flag):
        if not value:
            return None
        try:
            return datetime.date.fromisoformat(value.strip())
        except ValueError:
            raise CommandError(f"{flag} must be a date like 2026-10-23.")
