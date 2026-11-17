from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Serve ETqa with Waitress (ADR-03). Binds 127.0.0.1 by default; TLS is terminated in front."

    def add_arguments(self, parser):
        parser.add_argument("--host", default=settings.ETQA_SERVE_HOST)
        parser.add_argument("--port", type=int, default=settings.ETQA_SERVE_PORT)
        parser.add_argument("--threads", type=int, default=settings.ETQA_SERVE_THREADS)

    def handle(self, *args, host, port, threads, **options):
        from waitress import serve

        from config.wsgi import application

        self.stdout.write(f"ETqa {settings.ETQA_VERSION} on http://{host}:{port} ({threads} threads)")
        serve(application, host=host, port=port, threads=threads, ident="ETqa",
              max_request_body_size=60 * 1024 * 1024, channel_timeout=120)
