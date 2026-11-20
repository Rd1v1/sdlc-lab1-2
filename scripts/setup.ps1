param([switch]$Dev)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repo
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    if (Get-Command py -ErrorAction SilentlyContinue) { & py -3.13 -m venv .venv }
    else { & python -m venv .venv }
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.13+ is required' }
}
& $python -c 'import sys, pyexpat; assert sys.version_info >= (3,13); assert sys.prefix != sys.base_prefix; assert pyexpat.version_info >= (2,7,2), "Update Python: Expat 2.7.2+ is required"'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.13+ with Expat 2.7.2+ is required in .venv' }
$requirements = if ($Dev) { 'requirements-dev.txt' } else { 'requirements.txt' }
& $python -m pip install --disable-pip-version-check --cache-dir .cache/pip -r $requirements
if ($LASTEXITCODE -ne 0) { throw 'Local dependency restore failed' }
Write-Output 'Ready. All Python packages are inside .venv.'
