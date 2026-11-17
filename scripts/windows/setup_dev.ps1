# ETqa developer setup for Windows, as a standard user (no admin rights).
# Run from the repository root:
#   powershell -ExecutionPolicy Bypass -File scripts\windows\setup_dev.ps1
# Prerequisites (see documentation/setup-windows.md): Python 3.11+ on PATH, PostgreSQL running, .env filled in.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment .venv"
    python -m venv .venv
}
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements-dev.txt

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    $key = & $py -c "import secrets; print(secrets.token_urlsafe(64))"
    # Write UTF-8 without a BOM: Windows PowerShell 5.1's "Set-Content -Encoding UTF8" adds one, which breaks .env parsing.
    $text = (Get-Content ".env" -Raw) -replace "change-me-to-a-long-random-string", $key
    [IO.File]::WriteAllText((Join-Path (Get-Location) ".env"), $text, (New-Object Text.UTF8Encoding $false))
    Write-Host "Created .env with a new secret key. Edit ETQA_DATABASE_URL before continuing if needed."
}

& $py manage.py migrate
& $py manage.py bootstrap_roles
& $py manage.py seed_ai_models
& $py manage.py check
Write-Host ""
Write-Host "Done. Create your first admin with:"
Write-Host "  .venv\Scripts\python manage.py create_user <name> --role Admin"
Write-Host "Then start everything with scripts\windows\start_all.cmd (PostgreSQL must be running)."
