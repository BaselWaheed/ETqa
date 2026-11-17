# Changelog

## 0.6.0 (Phases 2-6)
- Phase 2: PostgreSQL job queue (SKIP LOCKED claims, 180 s leases, 30 s heartbeats, reaper, priority boost,
  retry with backoff, dead-letter, defer, idempotency keys, cancel, ephemeral jobs), workers, job API and admin.
- Phase 3: uploads with magic-byte, size, macro and zip-bomb checks; content-addressed storage; versions and
  duplicates; extraction for PDF (text layer or OCR of page images), DOCX, XLSX, CSV, TXT, PNG/JPG; Arabic
  normalization; section-aware chunking; injection flagging; antivirus hook; embeddings by job.
- Phase 4: model registry and task routes, Ollama client, fallback and no-downgrade, JSON schema validation,
  token budgets (exact with a tokenizer file, estimated otherwise), availability gate, vision window, prompts
  overridable in the admin site.
- Phase 5: hybrid retrieval (full text, identifier trigram, vectors, RRF) filtered by access scope inside SQL on
  both vector backends; cited answers with citation checks; insufficient-evidence path without a model call;
  saved and unsaved chats; feedback capture; streamed drafts; `evaluate_rag` command.
- Phase 6: configurable templates, generation per section, Python validation, de-duplication, traceability to
  passages, assumptions flagged, Excel export in template order with a Sources sheet.
- Runtime settings store (54 keys) with admin editing and audit; UI pages for Chat, Documents and Test cases.

## 0.1.0 (Phase 0 tooling + Phase 1 foundation)
- Phase 0 scripts: environment check, Ollama benchmarks (speed, memory, embeddings, structured output, cancel,
  vision), Arabic PDF order check, OCR accuracy check.
- Phase 1: accounts, roles and capabilities, collections and grants with AccessScope, audit events, health
  checks, Waitress serving, bilingual sign-in and home pages, module layer contracts, secret scan.
