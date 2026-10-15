param([switch]$Standalone)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Python dependency install failed" }
python scripts/prepare_icon.py
if ($LASTEXITCODE -ne 0) { throw "Icon generation failed" }
Push-Location frontend
try {
    npm install --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "React build failed" }
} finally {
    Pop-Location
}
# Onefile is the only production distribution. Standalone remains for debugging.
$mode = if ($Standalone) { "--mode=standalone" } else { "--mode=onefile" }
$argsList = @(
    "-m", "nuitka", $mode,
    "--assume-yes-for-downloads",
    "--windows-console-mode=disable",
    "--output-dir=build",
    "--output-filename=SparePartsManagement.exe",
    "--windows-icon-from-ico=assets/spare_parts.ico",
    "--include-data-file=assets/spare_parts.ico=assets/spare_parts.ico",
    "--include-package=config",
    "--include-package=inventory",
    "--include-package=django",
    "--module-parameter=django-settings-module=config.settings",
    "--include-package=waitress",
    "--include-package-data=webview",
    "--include-data-dir=frontend/dist=frontend/dist",
    "launcher.py"
)
$env:PYTHONPATH = (Resolve-Path "backend").Path
python @argsList
if ($LASTEXITCODE -ne 0) { throw "Nuitka build failed" }
$exePath = if ($Standalone) { "build/launcher.dist/SparePartsManagement.exe" } else { "build/SparePartsManagement.exe" }
if (-not (Test-Path $exePath -PathType Leaf)) { throw "Compiled EXE missing: $exePath" }
python scripts/verify_windows_icon.py $exePath
if ($LASTEXITCODE -ne 0) { throw "Windows icon verification failed" }
Write-Host "Nuitka $mode completed: $exePath. SQLite lives in data/inventory.sqlite3 beside the original EXE."
