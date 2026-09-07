"""Explain why a given login can or cannot manage Roles & Permissions.

The Roles & Permissions page and its create/rename/delete endpoints are
gated on the Super Admin or Admin group, and every request additionally
passes through ForcePasswordChangeMiddleware. When either blocks an AJAX
call the browser receives HTML rather than JSON, which the page reports as
a generic failure -- this command names the actual cause instead.

    python manage.py diagnose_role_access <username>
    python manage.py diagnose_role_access --all
"""
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

ALLOWED_GROUPS = ("Super Admin", "Admin")


class Command(BaseCommand):
    help = "Report whether a user can manage roles, and why not if they can't."

    def add_arguments(self, parser):
        parser.add_argument("username", nargs="?", help="Login to check.")
        parser.add_argument("--all", action="store_true",
                            help="List every account that can manage roles.")

    def handle(self, *args, **options):
        if options["all"] or not options["username"]:
            self._list_capable()
            return
        self._diagnose(options["username"])

    # ── one account ───────────────────────────────────────────────────

    def _diagnose(self, username):
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'No user named "{username}".'))
            self._list_capable()
            return

        groups = sorted(g.name for g in user.groups.all())
        employee = getattr(user, "employee_profile", None)
        must_change = bool(employee and employee.force_password_change)
        privileged = user.is_superuser or user.is_staff
        in_group = any(g in ALLOWED_GROUPS for g in groups)

        self.stdout.write(f"\nUser        : {user.username}")
        self.stdout.write(f"Groups      : {', '.join(groups) or '(none)'}")
        self.stdout.write(f"Superuser   : {user.is_superuser}    Staff: {user.is_staff}")
        self.stdout.write(f"Employee    : {employee or '(no linked employee record)'}")
        self.stdout.write(f"Must change password: {must_change}")

        blockers = []
        if must_change:
            blockers.append(
                "Temporary password not yet changed. Every request from this account is "
                "redirected to the change-password page, including background ones, which "
                "is what surfaces as a generic error.\n"
                "    Fix: sign in as this user and set a new password."
            )
        if not (privileged or in_group):
            blockers.append(
                f"Not in {' or '.join(ALLOWED_GROUPS)} (and not a superuser), so the "
                f"roles endpoints refuse the request.\n"
                f"    Fix: add this account to Super Admin, or use one that already is."
            )

        self.stdout.write("")
        if blockers:
            self.stdout.write(self.style.ERROR("CANNOT manage roles:"))
            for i, b in enumerate(blockers, 1):
                self.stdout.write(f"  {i}. {b}")
            self.stdout.write("")
            self._list_capable()
        else:
            self.stdout.write(self.style.SUCCESS("CAN manage roles - nothing blocking this account."))

    # ── who can ───────────────────────────────────────────────────────

    def _list_capable(self):
        self.stdout.write("\nAccounts that can manage roles right now:")
        found = False
        # Combined with Q rather than |ing two already-distinct querysets,
        # which SQLite rejects.
        from django.db.models import Q
        candidates = User.objects.filter(
            Q(groups__name__in=ALLOWED_GROUPS) | Q(is_superuser=True)
        ).distinct().order_by("username")
        for user in candidates:
            employee = getattr(user, "employee_profile", None)
            if employee and employee.force_password_change:
                self.stdout.write(
                    f"   {user.username:24} BLOCKED - must change their temporary password first"
                )
                continue
            label = "superuser" if user.is_superuser else ", ".join(
                sorted(g.name for g in user.groups.all())
            )
            self.stdout.write(self.style.SUCCESS(f"   {user.username:24} {label}"))
            found = True
        if not found:
            self.stdout.write(self.style.WARNING(
                "   None. Every privileged account is blocked by an unchanged temporary "
                "password, or no account holds Super Admin/Admin."
            ))
        for name in ALLOWED_GROUPS:
            if not Group.objects.filter(name=name).exists():
                self.stdout.write(self.style.WARNING(f'   (group "{name}" does not exist)'))
