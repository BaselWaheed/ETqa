# ETqa

On-premises AI QA engineering platform for e& Egypt: a modular Django monolith with PostgreSQL, local models
through Ollama, Arabic and English. The architecture lives in the "ETqa — Architecture Proposal" doc; section
numbers below refer to it.

## Status (v0.6.0)

| Phase | State |
| --- | --- |
| 0. Environment spike | Scripts in `scripts/phase0/`; **must be run on the target Windows machine** |
| 1. Foundation | Done: accounts, roles, collections, audit, health, bilingual UI |
| 2. Background processing | Done: PostgreSQL queue with leases, heartbeats, retries, dead-letter, recovery |
| 3. Document management | Done: validated uploads, versions, PDF/DOCX/XLSX/CSV/TXT/images, OCR, section-aware chunking |
| 4. Model orchestration | Done: model registry, task routes, fallback, output validation, token budgets, vision window |
| 5. RAG assistant | Done: hybrid search, access-scoped retrieval, cited answers, unsaved Viewer chat, evaluation command |
| 6. Test case engineering | Done: templates, generation, validation, de-duplication, traceability, Excel export |

**What "done" means here:** 202 automated tests pass on Linux with PostgreSQL 16 (including pgvector 0.6) and
Tesseract 5, with a stand-in for Ollama. Nothing has yet run on Windows or against real models, so answer
quality, speed and memory are unmeasured. Phase 0 and the 100+ question evaluation produce those numbers.

## Running it (Windows, standard user)

See `documentation/setup-windows.md`. In short:
```
powershell -ExecutionPolicy Bypass -File scripts\windows\setup_dev.ps1
.venv\Scripts\python manage.py create_user yourname --role Admin
ollama pull qwen2.5:7b-instruct-q4_K_M & ollama pull qwen2.5:1.5b-instruct-q4_K_M & ollama pull bge-m3 & ollama pull qwen3-vl:4b
scripts\windows\start_all.cmd
```
Four processes run: the web server, a `general` worker (documents, embeddings), an `inference` worker (answers,
test cases, vision) and Ollama. Admin health (`/api/v1/ops/health/`) shows a queue with no live worker.

## Configuration
Every tunable value is a runtime setting (`documentation/configuration.md`, 54 keys): chunk sizes, OCR, upload
limits, retrieval weights, timeouts, retry and lease timing, vision window caps, test case limits, the
insufficient-evidence messages. Models, task routes, prompts and Excel templates are rows in the admin site.
Changing the main model is a registry edit, not a code change.

## Checks
```
python -m pytest            # needs PostgreSQL; Tesseract for the OCR tests
lint-imports                # module boundaries (pyproject.toml)
python scripts/check_secrets.py
python manage.py evaluate_rag documentation/eval/questions.jsonl --user <evaluator> --answers
```

## Decisions taken while implementing
- Static files through WhiteNoise (no separate web server on Windows).
- Admins read all active collections; unreadable collections and documents return 404, not 403.
- Upload enqueues ingestion in the same transaction as the version row.
- Keyword search is available as soon as a document is chunked; semantic search follows when embeddings finish.
  If Ollama is down, embedding jobs are deferred (no attempts used) instead of failing.
- Vector search runs on pgvector when the extension is installed (`manage.py enable_pgvector`), otherwise on the
  array backend, which refuses scopes above `retrieval.array_max_candidates`.
- Answers without a valid citation are shown with an "unverified" warning, not hidden.
- The Folder column of generated test cases uses the requirement section (common parent when sections merge).
- Brand red `#e00800` is a placeholder until the official e& value is supplied.
