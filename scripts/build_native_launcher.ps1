param([string]$OutputFile = "build/SparePartsManagement-package/SparePartsManagement.exe")
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$programFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
if (-not $programFilesX86) { throw "Windows x64環境で実行してください" }
$vswhere = Join-Path $programFilesX86 "Microsoft Visual Studio/Installer/vswhere.exe"
if (-not (Test-Path $vswhere -PathType Leaf)) { throw "Visual Studio C++ Build Toolsが必要です" }
$installation = (& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Select-Object -First 1)
if (-not $installation) { throw "MSVC x64が見つかりません" }
$vsDevCmd = Join-Path $installation "Common7/Tools/VsDevCmd.bat"
if (-not (Test-Path $vsDevCmd -PathType Leaf)) { throw "VsDevCmd.batが見つかりません" }
if (-not (Test-Path "assets/spare_parts.ico" -PathType Leaf)) { throw "アプリアイコンがありません" }

# Import the MSVC/Windows SDK compiler environment into this PowerShell process.
$envCommand = '""{0}" -no_logo -arch=x64 -host_arch=x64 >nul && set"' -f $vsDevCmd
$environment = & cmd.exe /d /s /c $envCommand
if ($LASTEXITCODE -ne 0) { throw "MSVC環境の初期化に失敗しました" }
foreach ($line in $environment) {
    if ($line -match '^([^=]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], "Process")
    }
}
$target = [System.IO.Path]::GetFullPath($OutputFile)
New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent), "build" | Out-Null
& rc.exe /nologo /fo "build/launcher-icon.res" "scripts/windows_launcher.rc"
if ($LASTEXITCODE -ne 0) { throw "Windowsアイコンリソース作成に失敗しました" }
& cl.exe /nologo /O2 /W4 /MT /DUNICODE /D_UNICODE "/Fobuild/windows_launcher.obj" "scripts/windows_launcher.c" "build/launcher-icon.res" /link /SUBSYSTEM:WINDOWS /INCREMENTAL:NO user32.lib "/OUT:$target"
if ($LASTEXITCODE -ne 0) { throw "C製Windowsランチャーのコンパイルに失敗しました" }
if (-not (Test-Path $target -PathType Leaf)) { throw "ランチャーEXEがありません: $target" }
Write-Host "C製Windowsランチャー: $target"
