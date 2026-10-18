# Portable local runner; no system installation or PATH changes.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
New-Item -ItemType Directory -Force .tools/act | Out-Null
$archive = '.tools/act.zip'
$url = 'https://github.com/nektos/act/releases/download/v0.2.89/act_Windows_x86_64.zip'
$expected = '0F8CF866AD7E32421A219FC551A0A0EA5D12EAD464DE12EBFEAFD334A5973B50'
if (-not (Test-Path -LiteralPath $archive)) { Invoke-WebRequest $url -OutFile $archive }
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expected) { throw 'Runner archive checksum mismatch' }
if (-not (Test-Path .tools/act/act.exe)) { Expand-Archive -LiteralPath $archive -DestinationPath .tools/act }
& .tools/act/act.exe --version
if ($LASTEXITCODE -ne 0) { throw 'Runner verification failed' }
