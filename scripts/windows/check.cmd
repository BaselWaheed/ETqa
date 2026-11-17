@echo off
rem Runs the same checks as CI: tests, module boundaries, secret scan.
cd /d "%~dp0..\.."
".venv\Scripts\python.exe" -m pytest || exit /b 1
".venv\Scripts\lint-imports.exe" || exit /b 1
".venv\Scripts\python.exe" scripts\check_secrets.py || exit /b 1
echo All checks passed.
