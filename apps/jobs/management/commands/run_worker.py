import signal
import threading

from django.core.management.base import BaseCommand

from apps.jobs.worker import default_worker_id, run_forever


class Command(BaseCommand):
    help = "Run a background worker for one queue (inference or general). Ctrl+C stops it after the current job."

    def add_arguments(self, parser):
        parser.add_argument("--queue", default="general", choices=["general", "inference"])
        parser.add_argument("--worker-id", default="")

    def handle(self, *args, queue, worker_id, **options):
        stop = threading.Event()

        def _stop(*_):
            self.stdout.write("Stopping after the current job...")
            stop.set()

        for name in ("SIGINT", "SIGTERM", "SIGBREAK"):  # SIGBREAK: Ctrl+Break / service stop on Windows
            if hasattr(signal, name):
                signal.signal(getattr(signal, name), _stop)
        run_forever(queue, worker_id or default_worker_id(queue), stop)
