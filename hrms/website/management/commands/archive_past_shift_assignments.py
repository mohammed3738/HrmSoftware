"""Clear finished rotations out of the active Shift Roster.

Runs nightly as a Celery task (see website/tasks.py); this is the same thing
by hand, plus a --dry-run for looking before leaping.

    python manage.py archive_past_shift_assignments --dry-run
    python manage.py archive_past_shift_assignments
    python manage.py archive_past_shift_assignments --grace-days 30

Archiving here does not change any attendance: the biometric sync keeps
honouring auto-archived entries for the dates they covered, so an old night
shift still recalculates as a night shift.
"""
from django.core.management.base import BaseCommand

from website.services import shift_roster_cleanup


class Command(BaseCommand):
    help = ("Archive Shift Roster entries whose end date has passed. Attendance "
            "for those dates is unaffected.")

    def add_arguments(self, parser):
        parser.add_argument(
            "--grace-days", type=int, dest="grace_days",
            help="Leave entries alone until their end date is this many days past. "
                 "Defaults to SHIFT_ROSTER_ARCHIVE_AFTER_DAYS (%d)."
                 % shift_roster_cleanup.DEFAULT_GRACE_DAYS,
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="List what would be archived and change nothing.",
        )

    def handle(self, *args, **options):
        grace = options["grace_days"]
        dry_run = options["dry_run"]

        count, rows = shift_roster_cleanup.archive_past_assignments(
            grace=grace, dry_run=dry_run,
        )

        if not count:
            self.stdout.write("Nothing to archive -- no finished rotation is past "
                              "the grace period.")
            return

        self.stdout.write(f"{'Would archive' if dry_run else 'Archived'} "
                          f"{count} finished rotation(s):")
        self.stdout.write("")
        self.stdout.write("  %-10s %-26s %-18s %-12s %-12s %s"
                          % ("code", "employee", "shift", "from", "to", "night"))
        for row in rows:
            self.stdout.write("  %-10s %-26s %-18s %-12s %-12s %s" % (
                row["employee_code"] or "-",
                row["employee"][:26],
                (row["shift_name"] or "")[:18],
                row["start_date"],
                row["end_date"],
                "yes" if row["is_night_shift"] else "",
            ))
        self.stdout.write("")
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run: nothing was changed."))
        else:
            self.stdout.write(self.style.SUCCESS(
                "Attendance for those dates is unaffected -- the biometric sync "
                "still honours these entries when recalculating them."
            ))
