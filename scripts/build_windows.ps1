$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Python依存のインストール失敗" }
python -c "from windows_toasts import WindowsToaster, Toast; print('Windows toast runtime import OK')"
if ($LASTEXITCODE -ne 0) { throw "Windows通知ライブラリが利用できません" }
python scripts/prepare_icon.py
if ($LASTEXITCODE -ne 0) { throw "アイコン生成失敗" }
Push-Location frontend
try {
    npm install --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "React build failed" }
} finally { Pop-Location }
$djangoLocale = (python -c "from pathlib import Path; import django; print(Path(django.__file__).parent / 'conf' / 'locale' / 'ja')").Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path (Join-Path $djangoLocale 'LC_MESSAGES/django.mo') -PathType Leaf)) {
    throw "Djangoの日本語翻訳ファイルがありません"
}
$env:PYTHONPATH = (Resolve-Path "backend").Path
$argsList = @(
    "-m", "nuitka", "--mode=standalone", "--assume-yes-for-downloads",
    "--windows-console-mode=disable", "--output-dir=build",
    "--output-filename=SparePartsManagement.exe",
    "--windows-icon-from-ico=assets/spare_parts.ico",
    "--include-data-file=assets/spare_parts.ico=assets/spare_parts.ico",
    "--include-package=config", "--include-package=inventory", "--include-package=django",
    "--module-parameter=django-settings-module=config.settings",
    "--include-package=waitress", "--include-package=windows_toasts",
    "--include-data-dir=$djangoLocale=django/conf/locale/ja",
    "--include-data-dir=frontend/dist=frontend/dist", "launcher.py"
)
python @argsList
if ($LASTEXITCODE -ne 0) { throw "Nuitka standaloneビルド失敗" }
$dist = "build/launcher.dist"
if (-not (Test-Path "$dist/SparePartsManagement.exe" -PathType Leaf)) {
    throw "Nuitka本体EXEがありません"
}
$package = "build/SparePartsManagement-package"
if (Test-Path $package) { Remove-Item $package -Recurse -Force }
New-Item -ItemType Directory -Force -Path $package | Out-Null
Move-Item -Path $dist -Destination "$package/src"
if (-not (Test-Path "$package/src/django/conf/locale/ja/LC_MESSAGES/django.mo" -PathType Leaf)) {
    throw "Django日本語翻訳ファイルが配布物に含まれていません"
}
# pywebview JS resources must still be supplied by Nuitka's package configuration.
foreach ($requiredJs in @("webview/js/api.js", "webview/js/finish.js")) {
    if (-not (Test-Path "$package/src/$requiredJs" -PathType Leaf)) {
        throw "pywebviewのJSリソースが同梱されていません: $requiredJs"
    }
}
& ./scripts/build_native_launcher.ps1 -OutputFile "$package/SparePartsManagement.exe"
python scripts/verify_windows_icon.py "$package/SparePartsManagement.exe"
if ($LASTEXITCODE -ne 0) { throw "ランチャーのアイコン検査失敗" }
python scripts/verify_windows_icon.py "$package/src/SparePartsManagement.exe"
if ($LASTEXITCODE -ne 0) { throw "本体のアイコン検査失敗" }
Write-Host "standaloneの配布一式が完成: $package"
