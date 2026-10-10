# Official portable tools, pinned versions; nothing is added to global PATH.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
New-Item -ItemType Directory -Force .tools\act | Out-Null
$downloads = @(
    @('https://github.com/nektos/act/releases/download/v0.2.89/act_Windows_x86_64.zip', '.tools/act.zip', '0F8CF866AD7E32421A219FC551A0A0EA5D12EAD464DE12EBFEAFD334A5973B50')
)
foreach ($download in $downloads) {
    if (-not (Test-Path -LiteralPath $download[1])) { Invoke-WebRequest $download[0] -OutFile $download[1] }
    if ((Get-FileHash -LiteralPath $download[1] -Algorithm SHA256).Hash -ne $download[2]) { throw "Checksum mismatch: $($download[1])" }
}
if (-not (Test-Path .tools/act/act.exe)) { Expand-Archive .tools/act.zip -DestinationPath .tools/act }
& ./.tools/act/act.exe --version
Write-Output 'Portable tools ready in .tools; no global installation.'
