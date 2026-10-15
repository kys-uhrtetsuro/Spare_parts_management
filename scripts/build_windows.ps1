param([switch]$Onefile)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

python -m pip install -r requirements.txt
Push-Location frontend
try {
    npm install --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "React build failed" }
} finally {
    Pop-Location
}
$mode = if ($Onefile) { "--mode=onefile" } else { "--mode=standalone" }
$argsList = @(
    "-m", "nuitka", $mode,
    "--assume-yes-for-downloads",
    "--windows-console-mode=disable",
    "--output-dir=build",
    "--output-filename=SparePartsManagement.exe",
    "--include-package=config",
    "--include-package=inventory",
    "--include-package=django",
    "--include-package=waitress",
    "--include-package=webview",
    "--include-package-data=webview",
    "--include-data-dir=frontend/dist=frontend/dist",
    "launcher.py"
)
python @argsList
if ($LASTEXITCODE -ne 0) { throw "Nuitka build failed" }
Write-Host "Nuitka compilation completed. Keep the data directory when upgrading."
