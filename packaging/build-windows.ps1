# Build the Windows release (one-folder bundle + zip).
#
#   powershell -ExecutionPolicy Bypass -File packaging\build-windows.ps1
#
# Needs Python 3.12 with PyInstaller (pip install pyinstaller).
# NOTE: keep this file ASCII-only -- PowerShell 5.1 reads .ps1 as ANSI,
#       non-ASCII here would break the script.
$ErrorActionPreference = 'Stop'

$ver  = '1.0.0'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Output '--- 1. PyInstaller'
python -m PyInstaller --noconfirm ObraDinnInstructor.spec
if (-not (Test-Path 'dist\ObraDinnInstructor\ObraDinnInstructor.exe')) {
    throw 'build failed: exe not found'
}

Write-Output '--- 2. stage'
$name = "ObraDinnInstructor-$ver-windows-x64"
Remove-Item "dist\$name", "dist\$name.zip" -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory "dist\$name" | Out-Null
Copy-Item 'dist\ObraDinnInstructor\*' "dist\$name\" -Recurse

Write-Output '--- 3. zip'
# NOTE: pass the folder itself (no \*) so the archive keeps a top-level folder --
# Compress-Archive with 'path\*' would spray the files into the archive root.
Compress-Archive -Path "dist\$name" -DestinationPath "dist\$name.zip" -Force

Write-Output '--- result'
Get-Item "dist\$name.zip" | ForEach-Object {
    '{0}  {1:N1} MB' -f $_.Name, ($_.Length / 1MB)
}
Get-FileHash "dist\$name.zip" -Algorithm SHA256 |
    ForEach-Object { 'sha256 ' + $_.Hash.ToLower() }
