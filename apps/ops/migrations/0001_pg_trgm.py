from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    """pg_trgm ships with PostgreSQL contrib and is a trusted extension (PG 13+), so the database
    owner can enable it without superuser rights. Needed for identifier search (ADR-05)."""

    initial = True
    dependencies = []
    operations = [TrigramExtension()]
