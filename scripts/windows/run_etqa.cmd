@echo off
rem Starts all of ETqa in one go: PostgreSQL, Ollama (if installed), migrations, both workers, the web server.
rem Optional parts are skipped with a warning instead of stopping:
rem   - Ollama missing:    the app runs; chat answers, embeddings and image descriptions wait until it is available.
rem   - Tesseract missing: the app runs; images and scanned PDF pages are stored without text, flagged needs_review.
rem Run from anywhere:  scripts\windows\run_etqa.cmd      Stop: Ctrl+C here, and close the worker windows.
setlocal
cd /d "%~dp0..\.."

if not exist ".venv\Scripts\python.exe" (
    echo [ETqa] No .venv found. First run:  powershell -ExecutionPolicy Bypass -File scripts\windows\setup_dev.ps1
    exit /b 1
)
if not exist ".env" (
    echo [ETqa] No .env found. Copy .env.example to .env and set ETQA_DATABASE_URL.
    exit /b 1
)

rem ---------------------------------------------------------------- PostgreSQL (required)
if "%PGHOME%"=="" set "PGHOME=%USERPROFILE%\pgsql"
if "%PGDATA%"=="" set "PGDATA=%USERPROFILE%\etqa-pgdata"
if not exist "%PGHOME%\bin\pg_isready.exe" (
    echo [ETqa] PostgreSQL binaries not found in %PGHOME%; assuming a PostgreSQL server is already running.
    goto pg_done
)
"%PGHOME%\bin\pg_isready.exe" -h 127.0.0.1 -q
if not errorlevel 1 (
    echo [ETqa] PostgreSQL is already running.
    goto pg_done
)
echo [ETqa] Starting PostgreSQL...
call scripts\windows\start_postgres.cmd >nul
for /l %%i in (1,1,30) do (
    "%PGHOME%\bin\pg_isready.exe" -h 127.0.0.1 -q && goto pg_done
    timeout /t 1 /nobreak >nul
)
echo [ETqa] PostgreSQL did not start. See %PGDATA%\postgres.log
exit /b 1
:pg_done

rem ---------------------------------------------------------------- Tesseract (optional)
where tesseract >nul 2>&1 && goto tess_found
for %%d in ("%LOCALAPPDATA%\Programs\Tesseract-OCR" "%ProgramFiles%\Tesseract-OCR") do (
    if exist "%%~d\tesseract.exe" set "PATH=%PATH%;%%~d" & goto tess_found
)
echo [ETqa] WARNING: Tesseract not found. OCR is off: images and scanned PDF pages will be flagged needs_review.
goto tess_done
:tess_found
echo [ETqa] Tesseract found.
:tess_done

rem ---------------------------------------------------------------- Ollama (optional)
where ollama >nul 2>&1 && goto ollama_found
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
    set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Ollama"
    goto ollama_found
)
echo [ETqa] WARNING: Ollama not found. Chat answers and semantic search wait until it is installed and running.
goto ollama_done
:ollama_found
curl.exe -s -o nul http://127.0.0.1:11434/api/version
if not errorlevel 1 (
    echo [ETqa] Ollama is already running.
    goto ollama_done
)
echo [ETqa] Starting Ollama in its own window...
start "Ollama" cmd /c scripts\windows\start_ollama.cmd
timeout /t 3 /nobreak >nul
:ollama_done

rem ---------------------------------------------------------------- ETqa
echo [ETqa] Applying database migrations (if any)...
".venv\Scripts\python.exe" manage.py migrate --noinput -v 0 || exit /b 1

echo [ETqa] Starting workers in their own windows...
call scripts\windows\start_workers.cmd

echo [ETqa] Starting the web server on http://127.0.0.1:8000  (Ctrl+C to stop)
start "" cmd /c "timeout /t 5 /nobreak >nul & start http://127.0.0.1:8000"
call scripts\windows\start_web.cmd
