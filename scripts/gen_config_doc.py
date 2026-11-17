"""Regenerates documentation/configuration.md from apps/sysconfig/defaults.py (run after adding a setting)."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from apps.sysconfig.defaults import DEFAULTS  # noqa: E402

lines = ["# Runtime configuration", "",
         "Every value below can be changed without a code change or restart: Administration > System settings, "
         "add a row with the key and a JSON value. Changes apply within about 5 seconds and are audited. "
         "Delete the row to return to the default. Models, task routes, prompts and test case templates are "
         "edited in their own admin pages. Start-up settings (database, secret key, TLS proxy) are environment "
         "variables in `.env`, listed at the end.", "",
         "| Key | Default | Meaning |", "| --- | --- | --- |"]
for key, (default, help_text) in sorted(DEFAULTS.items()):
    value = json.dumps(default, ensure_ascii=False).replace("|", "\\|")
    lines.append(f"| `{key}` | `{value}` | {help_text.replace('|', '/')} |")
lines += ["", "## Environment variables (.env)", "",
          "| Variable | Meaning |", "| --- | --- |",
          "| `ETQA_DATABASE_URL` | PostgreSQL connection URL |",
          "| `ETQA_SECRET_KEY` | Django secret key (50+ random characters in production) |",
          "| `ETQA_ALLOWED_HOSTS` | Comma-separated host names |",
          "| `ETQA_OLLAMA_URL` | Ollama address, default `http://127.0.0.1:11434` |",
          "| `ETQA_FILE_ROOT` | Where original documents are stored |",
          "| `ETQA_SERVE_HOST`, `ETQA_SERVE_PORT`, `ETQA_SERVE_THREADS` | Waitress binding (default 127.0.0.1:8000, 8 threads) |",
          "| `ETQA_BEHIND_TLS_PROXY` | `true` when a TLS terminator is in front: secure cookies, HTTPS redirect |",
          "| `ETQA_SSL_REDIRECT`, `ETQA_HSTS_SECONDS` | Fine control when behind TLS (HSTS off by default) |",
          "| `ETQA_SESSION_IDLE_MINUTES`, `ETQA_SESSION_ABSOLUTE_HOURS` | Session timeouts |",
          "| `ETQA_LOGIN_MAX_FAILURES`, `ETQA_LOGIN_LOCK_MINUTES` | Sign-in lockout |"]
(ROOT / "documentation" / "configuration.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"{len(DEFAULTS)} settings documented")
