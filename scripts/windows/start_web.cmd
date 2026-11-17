@echo off
rem Starts ETqa on http://127.0.0.1:8000 with Waitress. Ctrl+C stops it.
cd /d "%~dp0..\.."
".venv\Scripts\python.exe" manage.py serve %*
