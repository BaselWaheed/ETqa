@echo off
rem Starts the two ETqa workers in their own windows (section 1). Close a window or press Ctrl+C to stop it
rem after its current job. Both must run for documents to be processed and questions to be answered.
cd /d "%~dp0..\.."
start "ETqa worker - general" ".venv\Scripts\python.exe" manage.py run_worker --queue general
start "ETqa worker - inference" ".venv\Scripts\python.exe" manage.py run_worker --queue inference
