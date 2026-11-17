@echo off
rem Starts Ollama, both workers and the web server. PostgreSQL must already be running.
cd /d "%~dp0..\.."
start "Ollama" cmd /c scripts\windows\start_ollama.cmd
timeout /t 3 /nobreak >nul
call scripts\windows\start_workers.cmd
call scripts\windows\start_web.cmd
