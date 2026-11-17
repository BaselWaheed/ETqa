from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.retrieval.models import EmbeddingSpace


class Command(BaseCommand):
    help = ("Install the pgvector extension (needs a PostgreSQL role allowed to create it) and build an HNSW index "
            "per embedding space. Safe to re-run. Then set retrieval.vector_backend to auto or pgvector.")

    def handle(self, *args, **options):
        with connection.cursor() as cur:
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            except Exception as exc:  # noqa: BLE001
                raise CommandError(f"Could not create the vector extension: {exc}") from exc
            cur.execute("SET CONSTRAINTS ALL IMMEDIATE")  # index builds refuse pending deferred FK checks
            for space in EmbeddingSpace.objects.all():
                name = f"chunk_emb_hnsw_space_{space.id}"
                cur.execute(f"CREATE INDEX IF NOT EXISTS {name} ON retrieval_chunkembedding USING hnsw "
                            f"((vector::vector({int(space.dims)})) vector_cosine_ops) WHERE space_id = {int(space.id)}")
                self.stdout.write(f"index {name} ready")
