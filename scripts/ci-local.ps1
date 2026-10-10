param([switch]$List, [switch]$Offline)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$act = Join-Path (Get-Location).Path '.tools\act\act.exe'
if (-not (Test-Path -LiteralPath $act)) { throw 'Download portable act into .tools/act (see docs/lab2-defense.md)' }
New-Item -ItemType Directory -Force .cache\act,.cache\actions,.cache\artifacts | Out-Null
$options = @('push','-W','.github/workflows/main.yml','-P','ubuntu-latest=catthehacker/ubuntu:act-22.04','--action-cache-path', (Join-Path (Get-Location).Path '.cache\actions'), '--cache-server-path', (Join-Path (Get-Location).Path '.cache\act'), '--artifact-server-path', (Join-Path (Get-Location).Path '.cache\artifacts'), '--container-daemon-socket','/var/run/docker.sock','--workflows','.github/workflows/main.yml')
if ($List) { $options += '--list' }
if ($Offline) { $options += '--action-offline-mode' }
& $act @options
exit $LASTEXITCODE
