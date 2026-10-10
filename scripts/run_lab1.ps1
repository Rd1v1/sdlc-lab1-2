$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if (Test-Path .venv\Scripts\python.exe) { & .\.venv\Scripts\python.exe -m lab1.src.app @args }
elseif (Get-Command py -ErrorAction SilentlyContinue) { & py -3.13 -m lab1.src.app @args }
else { & python -m lab1.src.app @args }
exit $LASTEXITCODE
