# Runtime configuration

Every value below can be changed without a code change or restart: Administration > System settings, add a row with the key and a JSON value. Changes apply within about 5 seconds and are audited. Delete the row to return to the default. Models, task routes, prompts and test case templates are edited in their own admin pages. Start-up settings (database, secret key, TLS proxy) are environment variables in `.env`, listed at the end.

| Key | Default | Meaning |
| --- | --- | --- |
| `ai.char_per_token` | `3.0` | Token estimate when no tokenizer file is configured for a model. |
| `ai.health_cache_seconds` | `15` | How long an Ollama availability check is trusted. |
| `chat.answer_max_tokens` | `700` | Maximum answer length. |
| `chat.context_tokens` | `8192` | Context window requested for answers. |
| `chat.history_turns` | `4` | Previous turns sent with each question. |
| `chat.insufficient_ar` | `"الوثائق المتاحة لا توفر معلومات كافية للإجابة عن هذا السؤال."` | Insufficient-evidence answer (Arabic). |
| `chat.insufficient_en` | `"The available documentation does not provide sufficient information to answer this question."` | Insufficient-evidence answer (English). |
| `chat.poll_idle_ms` | `1500` | UI poll interval while queued. |
| `chat.poll_running_ms` | `500` | UI poll interval while an answer streams. |
| `chat.reserve_ratio` | `0.08` | Share of the context kept free (token-count safety margin). |
| `chunk.max_tokens` | `1200` | Hard cap; a single table row or paragraph larger than this is split. |
| `chunk.overlap_ratio` | `0.12` | Overlap between consecutive chunks of the same section (0.10-0.15 recommended). |
| `chunk.target_tokens` | `500` | Target chunk size in tokens. |
| `embed.batch_size` | `16` | Chunks per embedding request. |
| `jobs.boost_after_minutes` | `15` | Waiting time before a job gets a priority boost. |
| `jobs.boost_cap` | `50` | Maximum total boost. |
| `jobs.boost_step` | `10` | Boost added per waiting period. |
| `jobs.completed_retention_days` | `30` | Completed and cancelled jobs are purged after this. |
| `jobs.ephemeral_ttl_minutes` | `60` | Unsaved-chat job text is cleared this long after completion if never fetched. |
| `jobs.heartbeat_seconds` | `30` | Heartbeat interval while a handler runs. |
| `jobs.lease_seconds` | `180` | Lease length; a worker may miss lease/heartbeat beats before its job is recovered. |
| `jobs.max_attempts` | `3` | Attempts before a job is marked failed. |
| `jobs.poll_idle_seconds` | `1.0` | Worker idle polling interval. |
| `jobs.progress_interval_seconds` | `1.0` | Minimum interval between progress (streaming) writes. |
| `jobs.reaper_seconds` | `60` | How often each worker recovers expired leases. |
| `jobs.retry_base_seconds` | `10` | First retry delay; doubles per attempt with +/-20% jitter. |
| `jobs.retry_max_seconds` | `600` | Retry delay cap. |
| `ocr.enabled` | `true` | Run OCR on images and on PDF pages without a text layer. |
| `ocr.languages` | `"ara+eng"` | Tesseract language codes. |
| `ocr.min_text_chars` | `40` | A PDF page with fewer extracted characters is treated as scanned. |
| `ocr.review_confidence` | `60` | Pages with mean OCR confidence below this are flagged needs_review. |
| `ocr.tesseract_command` | `"tesseract"` | Path to tesseract.exe if it is not on PATH. |
| `retrieval.array_max_candidates` | `60000` | ArrayVectorStore refuses scopes larger than this (dev backend). |
| `retrieval.final_k` | `8` | Passages passed to the model. |
| `retrieval.k_fts` | `30` | Candidates from full-text search. |
| `retrieval.k_trigram` | `15` | Candidates from identifier (trigram) search. |
| `retrieval.k_vector` | `30` | Candidates from vector search. |
| `retrieval.min_vector_similarity` | `0.45` | Vector-only hits below this cosine similarity are ignored. |
| `retrieval.rrf_k` | `60` | Reciprocal Rank Fusion constant. |
| `retrieval.trigram_threshold` | `0.35` | Minimum trigram similarity for identifier matches. |
| `retrieval.vector_backend` | `"auto"` | auto / array / pgvector. auto uses pgvector when the extension is installed. |
| `security.av_command` | `""` | Antivirus command run before extraction; {path} is replaced. Empty disables the hook. Example: C:\Program Files\Windows Defender\MpCmdRun.exe -Scan -ScanType 3 -File {path} -DisableRemediation |
| `security.injection_patterns` | `["ignore (all )?(previous\|prior) instructions", "you are now", "system prompt", "disregard (the )?(above\|previous)", "تجاهل (جميع )?التعليمات", "أنت الآن"]` | Regexes that flag passages addressed to an AI assistant (logged, not blocked). |
| `tc.cases_per_section` | `8` | Upper bound requested from the model per section. |
| `tc.duplicate_threshold` | `0.9` | Similarity (0-1) above which two test cases are duplicates. |
| `tc.max_sections_per_set` | `20` | Requirement sections processed per generation request. |
| `upload.max_mb` | `{"pdf": 50, "docx": 25, "xlsx": 25, "csv": 20, "txt": 10, "png": 15, "jpg": 15}` | Maximum upload size per file type, in MB. |
| `upload.text_encodings` | `["utf-8-sig", "cp1256"]` | Encodings tried for CSV/TXT, in order. |
| `upload.zip_max_entries` | `5000` | DOCX/XLSX zip-bomb guard: number of entries. |
| `upload.zip_max_uncompressed_mb` | `200` | DOCX/XLSX zip-bomb guard: total uncompressed size. |
| `vision.defer_seconds` | `60` | Delay before retrying a vision job deferred because chats are waiting. |
| `vision.enabled` | `true` | Describe images and diagrams with the vision model. |
| `vision.window_max_jobs` | `3` | Vision jobs per exclusive window. |
| `vision.window_max_minutes` | `10` | Exclusive window time cap. |

## Environment variables (.env)

| Variable | Meaning |
| --- | --- |
| `ETQA_DATABASE_URL` | PostgreSQL connection URL |
| `ETQA_SECRET_KEY` | Django secret key (50+ random characters in production) |
| `ETQA_ALLOWED_HOSTS` | Comma-separated host names |
| `ETQA_OLLAMA_URL` | Ollama address, default `http://127.0.0.1:11434` |
| `ETQA_FILE_ROOT` | Where original documents are stored |
| `ETQA_SERVE_HOST`, `ETQA_SERVE_PORT`, `ETQA_SERVE_THREADS` | Waitress binding (default 127.0.0.1:8000, 8 threads) |
| `ETQA_BEHIND_TLS_PROXY` | `true` when a TLS terminator is in front: secure cookies, HTTPS redirect |
| `ETQA_SSL_REDIRECT`, `ETQA_HSTS_SECONDS` | Fine control when behind TLS (HSTS off by default) |
| `ETQA_SESSION_IDLE_MINUTES`, `ETQA_SESSION_ABSOLUTE_HOURS` | Session timeouts |
| `ETQA_LOGIN_MAX_FAILURES`, `ETQA_LOGIN_LOCK_MINUTES` | Sign-in lockout |
