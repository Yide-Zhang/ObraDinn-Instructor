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
# PyInstaller 会重写 dist\ObraDinnInstructor\，把别人放在里面的 zip 一并清掉。
# 先挪去临时目录，产完再放回来。
$zips = @(Get-ChildItem 'dist\ObraDinnInstructor' -Filter *.zip -ErrorAction SilentlyContinue)
$park = Join-Path $env:TEMP ('obd-build-zips-' + [guid]::NewGuid().ToString('N'))
if ($zips.Count) {
    New-Item -ItemType Directory $park -Force | Out-Null
    $zips | ForEach-Object { Move-Item $_.FullName $park -Force }
    Write-Output ("parked $($zips.Count) zip(s) out of dist")
}
python -m PyInstaller --noconfirm ObraDinnInstructor.spec
if ($zips.Count) {
    $zips | ForEach-Object { Move-Item (Join-Path $park $_.Name) 'dist\ObraDinnInstructor\' -Force }
    Write-Output ("restored $($zips.Count) zip(s)")
}
if (-not (Test-Path 'dist\ObraDinnInstructor\ObraDinnInstructor.exe')) {
    throw 'build failed: exe not found'
}

Write-Output '--- 2. stage'
$name = "ObraDinnInstructor-$ver-windows-x64"
Remove-Item "dist\$name", "dist\$name.zip" -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory "dist\$name" | Out-Null
# 只搬程序本身：dist\ObraDinnInstructor\ 里可能还有别人放的 zip
robocopy 'dist\ObraDinnInstructor' "dist\$name" /E /XF *.zip /NFL /NDL /NJH /NJS /NP | Out-Null

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
