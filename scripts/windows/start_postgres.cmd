@echo off
rem Starts a user-owned PostgreSQL (zip binaries, no service, no admin). Set PGHOME and PGDATA to your paths.
if "%PGHOME%"=="" set PGHOME=%USERPROFILE%\pgsql
if "%PGDATA%"=="" set PGDATA=%USERPROFILE%\etqa-pgdata
"%PGHOME%\bin\pg_ctl.exe" -D "%PGDATA%" -l "%PGDATA%\postgres.log" start
