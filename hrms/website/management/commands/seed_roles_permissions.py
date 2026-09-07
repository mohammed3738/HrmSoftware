"""Bring the roles, features and permission matrix in line with
website/permissions_registry.py.

The matrix is normally seeded by migrations, but a database where those
data migrations didn't take (restored from an older dump, migrated with a
different registry, or partially applied) ends up with an empty Roles &
Permissions page -- no features to tick, and missing roles. This command
reconciles it without needing to unpick migration history.

Safe to run repeatedly: it creates what's missing and updates what drifted,
and never deletes a role someone added by hand.

    python manage.py seed_roles_permissions            # apply
    python manage.py seed_roles_permissions --dry-run  # report only
"""
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

from website.permissions_registry import FEATURES, SEED_GRANTS, SYSTEM_ROLES

ACTIONS = ("view", "create", "edit", "approve")


class Command(BaseCommand):
    help = "Create/refresh the roles, features and permission matrix from the registry."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Report what would change without writing.")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        from website.models import Feature, RoleFeaturePermission

        created_groups, created_features, updated_features = [], [], []
        grant_changes = 0

        with transaction.atomic():
            for name in SYSTEM_ROLES:
                if not Group.objects.filter(name=name).exists():
                    created_groups.append(name)
                    if not dry:
                        Group.objects.create(name=name)

            for row in FEATURES:
                defaults = {k: v for k, v in row.items() if k != "key"}
                existing = Feature.objects.filter(key=row["key"]).first()
                if existing is None:
                    created_features.append(row["key"])
                    if not dry:
                        Feature.objects.create(**row)
                else:
                    drifted = [k for k, v in defaults.items() if getattr(existing, k) != v]
                    if drifted:
                        updated_features.append(f"{row['key']} ({', '.join(drifted)})")
                        if not dry:
                            for k, v in defaults.items():
                                setattr(existing, k, v)
                            existing.save()

            if not dry:
                for name in SYSTEM_ROLES:
                    group = Group.objects.get(name=name)
                    for feature in Feature.objects.all():
                        rfp, _ = RoleFeaturePermission.objects.get_or_create(
                            role=group, feature=feature
                        )
                        before = [getattr(rfp, f"can_{a}") for a in ACTIONS]
                        for action in ACTIONS:
                            setattr(rfp, f"can_{action}",
                                    name in SEED_GRANTS.get((feature.key, action), ()))
                        after = [getattr(rfp, f"can_{a}") for a in ACTIONS]
                        if before != after:
                            grant_changes += 1
                        rfp.save()

            if dry:
                transaction.set_rollback(True)

        label = "WOULD CREATE" if dry else "created"
        self.stdout.write(f"\nRoles {label}: {', '.join(created_groups) or 'none (all present)'}")
        self.stdout.write(f"Features {label}: {', '.join(created_features) or 'none (all present)'}")
        if updated_features:
            self.stdout.write(f"Features updated: {', '.join(updated_features)}")
        if not dry:
            self.stdout.write(f"Permission rows changed: {grant_changes}")

        self.stdout.write("")
        self.stdout.write(f"Roles now      : {Group.objects.count()}")
        self.stdout.write(f"Features now   : {Feature.objects.filter(is_active=True).count()} active")
        self.stdout.write(f"Matrix rows now: {RoleFeaturePermission.objects.count()}")
        if dry:
            self.stdout.write(self.style.WARNING("\nDry run - nothing was written."))
        else:
            self.stdout.write(self.style.SUCCESS("\nDone. Reload the Roles & Permissions page."))
