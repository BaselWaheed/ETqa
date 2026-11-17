from django.core.management.base import BaseCommand

from apps.access.services import bootstrap_roles


class Command(BaseCommand):
    help = "Create the Admin, Reviewer, QA Engineer and Viewer roles with default capabilities (idempotent)."

    def handle(self, *args, **options):
        for role, added in bootstrap_roles().items():
            self.stdout.write(f"{role}: {added} permission(s) added")
