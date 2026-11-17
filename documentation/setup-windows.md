# Setting up ETqa on Windows without administrator rights

This guide is the U11 check itself: if any step needs admin rights on your machine, record it in the
Phase 0 report. Steps marked **[validate]** are believed to work as a standard user but are unconfirmed.

## 1. Python 3.11 or newer
Install from python.org with **"Install for all users" unchecked** (per-user install, no admin).
Tick "Add python.exe to PATH".

## 2. PostgreSQL 16 (user-owned, no Windows service)
1. Download the PostgreSQL **zip binaries** for Windows (not the installer) and unzip to `%USERPROFILE%\pgsql`.
2. Create a data directory and start the server:
   ```
   %USERPROFILE%\pgsql\bin\initdb.exe -D %USERPROFILE%\etqa-pgdata -U postgres -E UTF8 --no-locale -W
   scripts\windows\start_postgres.cmd
   ```
3. Create the development database (single owner role is fine for development):
   ```
   %USERPROFILE%\pgsql\bin\psql.exe -U postgres -c "CREATE ROLE etqa LOGIN PASSWORD 'choose-one' CREATEDB;"
   %USERPROFILE%\pgsql\bin\psql.exe -U postgres -c "CREATE DATABASE etqa OWNER etqa;"
   ```
4. pgvector (needed by Phase 5) **[validate]**: because this PostgreSQL lives in your own folder, its extension
   files can be copied in without admin rights. Look for a prebuilt Windows build matching your PostgreSQL
   version; compiling needs Visual Studio Build Tools. `env_check.py` reports whether `vector` is available.

For a production-like setup with separate migration and runtime roles, use `scripts/sql/01_roles.sql` and
re-run `scripts/sql/02_app_grants.sql` after every migration (it makes the audit table append-only).

## 3. Ollama **[validate]**
Run the Windows installer; it installs per-user. Quit the tray app and start Ollama with ETqa's settings
using `scripts\windows\start_ollama.cmd`. Ollama listens on 127.0.0.1 only.

## 4. Tesseract OCR (optional) **[validate]**
Install a Windows build with the Arabic (`ara`) and English (`eng`) language data, choosing a folder under
your user profile if the installer offers per-user installation. Add it to your user PATH.

Observed: the UB-Mannheim installer ignores `/D=<user folder>`, elevates and installs into `C:\Program Files`
(admin needed). Language files can still be added without admin: copy the whole `tessdata` folder (including
`configs`) to `%USERPROFILE%\tessdata`, add `ara.traineddata` there, and set the user variable `TESSDATA_PREFIX`
to that folder.

ETqa runs without Tesseract: images and scanned PDF pages are then stored without text and flagged
`needs_review` (images are still described by the vision model). `/api/v1/ops/health/` reports `ocr.status`.

## 5. Models
```
ollama pull qwen2.5:7b-instruct-q4_K_M
ollama pull qwen2.5:1.5b-instruct-q4_K_M
ollama pull bge-m3
ollama pull qwen3-vl:4b
```
Tags are starting points **[validate]**: check them with `ollama list`, then edit Administration > AI models if
a name differs. `/api/v1/ops/health/` lists each registered model and whether it is pulled.

## 6. ETqa
```
copy .env.example .env      (then set ETQA_DATABASE_URL)
powershell -ExecutionPolicy Bypass -File scripts\windows\setup_dev.ps1
.venv\Scripts\python manage.py create_user yourname --role Admin
scripts\windows\run_etqa.cmd
```
`run_etqa.cmd` starts everything in one go: PostgreSQL (if not running), Ollama and Tesseract if installed (a
warning otherwise), pending migrations, both workers and the web server, then opens the browser.
Open http://127.0.0.1:8000. In Administration, create a collection and grant your groups access, then upload a
document under Documents. Run all checks with `scripts\windows\check.cmd`.

## 7. pgvector (when available)
After installing the extension files: `.venv\Scripts\python manage.py enable_pgvector`. The setting
`retrieval.vector_backend` (default `auto`) then switches to indexed vector search.

## Access from other machines
Waitress binds to 127.0.0.1. Serving colleagues on the network needs the TLS terminator decided in Phase 1
(ADR-03); until then, ETqa is for the local user only.
