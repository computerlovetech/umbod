#requires -Version 7.0
[CmdletBinding()]
param(
    [ValidateSet('dev', 'release')][string]$Channel = 'release',
    [string]$OutputDirectory = '',
    [string]$Dotnet = 'dotnet',
    [string]$Cargo = '',
    [string]$Python = 'python',
    [string]$GatewayExecutable = ''
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = Split-Path $PSScriptRoot -Parent
if (!$OutputDirectory) { $OutputDirectory = Join-Path $repo 'dist' }
$publish = & (Join-Path $PSScriptRoot 'build-windows.ps1') -Channel $Channel -OutputDirectory $OutputDirectory `
    -Dotnet $Dotnet -Cargo $Cargo -GatewayExecutable $GatewayExecutable
# Package inputs contain only freshly published files. Move the two package-managed inputs
# to sibling staging so the packager can reject accidentally included runtime/profile files.
$stagingGateway = Join-Path (Split-Path $publish -Parent) ('gateway-' + [Guid]::NewGuid().ToString('N') + '.exe')
try {
    Move-Item -LiteralPath (Join-Path $publish 'umbod-gateway.exe') -Destination $stagingGateway
    Remove-Item -LiteralPath (Join-Path $publish 'umbod-profile')
    & $Python (Join-Path $PSScriptRoot 'package-windows.py') --publish $publish --gateway $stagingGateway --channel $Channel --output $OutputDirectory
    if ($LASTEXITCODE -ne 0) { throw "Windows packaging failed with exit code $LASTEXITCODE" }
} finally {
    # Restore the runnable build directory even when archive validation fails.
    if (Test-Path -LiteralPath $stagingGateway) {
        Move-Item -LiteralPath $stagingGateway -Destination (Join-Path $publish 'umbod-gateway.exe')
    }
    [IO.File]::WriteAllText((Join-Path $publish 'umbod-profile'), "$Channel`n", [Text.UTF8Encoding]::new($false))
}
