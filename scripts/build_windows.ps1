param([switch]$Standalone, [switch]$Both)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if ($Standalone -and $Both) { throw "StandaloneとBothは同時に指定できません" }

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

# Django's gettext files are data resources, not Python modules.
# A missing ja .mo makes django.setup() fail before SQLite migrations.
$djangoLocale = (python -c "from pathlib import Path; import django; print(Path(django.__file__).parent / 'conf' / 'locale' / 'ja')").Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path (Join-Path $djangoLocale 'LC_MESSAGES/django.mo') -PathType Leaf)) {
    throw "Django日本語翻訳ファイルを確認できません: $djangoLocale"
}

# Install dependencies/compile React once, then compile both distribution types.
$modes = if ($Both) { @("--mode=onefile", "--mode=standalone") } elseif ($Standalone) { @("--mode=standalone") } else { @("--mode=onefile") }
$env:PYTHONPATH = (Resolve-Path "backend").Path
foreach ($mode in $modes) {
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
        "--include-data-dir=$djangoLocale=django/conf/locale/ja",
        "--include-data-dir=frontend/dist=frontend/dist",
        "launcher.py"
    )
    Write-Host "Nuitka compilation: $mode"
    python @argsList
    if ($LASTEXITCODE -ne 0) { throw "Nuitka build failed: $mode" }
    $exePath = if ($mode -eq "--mode=standalone") { "build/launcher.dist/SparePartsManagement.exe" } else { "build/SparePartsManagement.exe" }
    if (-not (Test-Path $exePath -PathType Leaf)) { throw "Compiled EXE missing: $exePath" }
    python scripts/verify_windows_icon.py $exePath
    if ($LASTEXITCODE -ne 0) { throw "Windows icon verification failed: $mode" }
    if ($mode -eq "--mode=standalone" -and -not (Test-Path "build/launcher.dist/django/conf/locale/ja/LC_MESSAGES/django.mo")) {
        throw "Django日本語翻訳ファイルがstandalone配布物に含まれていません"
    }
}
Write-Host "Nuitka compilation complete. Keep external data/inventory.sqlite3 when upgrading."
