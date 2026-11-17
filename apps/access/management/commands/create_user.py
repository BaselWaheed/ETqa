import getpass

from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.access.roles import ADMIN, ROLES
from apps.audit.services import record


class Command(BaseCommand):
    help = "Create a local account with one role. Prompts for the password (never pass it on the command line)."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--role", required=True, choices=ROLES)
        parser.add_argument("--language", choices=["en", "ar"], default="en")

    def handle(self, *args, username, role, language, **options):
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            raise CommandError(f"User {username!r} already exists.")
        group = Group.objects.filter(name=role).first()
        if group is None:
            raise CommandError("Roles missing. Run: python manage.py bootstrap_roles")
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Password (again): "):
            raise CommandError("Passwords do not match.")
        user = User(username=username, preferred_language=language, is_staff=(role == ADMIN))
        try:
            password_validation.validate_password(password, user)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
        user.set_password(password)
        user.save()
        user.groups.add(group)
        record("accounts.user_created", obj=user, role=role, via="command")
        self.stdout.write(self.style.SUCCESS(f"Created {username} with role {role}."))
