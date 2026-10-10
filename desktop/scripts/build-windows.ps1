#requires -Version 7.0
[CmdletBinding()]
param(
    [ValidateSet('dev', 'release')][string]$Channel = 'dev',
    [string]$OutputDirectory = '',
    [string]$Dotnet = 'dotnet',
    [string]$Cargo = '',
    # Allows cross-building the UI on another OS with an already built Windows gateway.
    [string]$GatewayExecutable = ''
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
# A desktop build does not need ASP.NET development certificates or SDK telemetry.
$env:DOTNET_GENERATE_ASPNET_CERTIFICATE = 'false'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE = '1'
$repo = Split-Path $PSScriptRoot -Parent
if (!$OutputDirectory) { $OutputDirectory = Join-Path $repo "dist/windows-$Channel" }
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
if (!$Cargo) {
    $cargoName = if ($IsWindows) { 'cargo.exe' } else { 'cargo' }
    $Cargo = Join-Path $HOME ".cargo/bin/$cargoName"
}
function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}
$version = (Get-Content -LiteralPath (Join-Path $repo 'VERSION') -Raw).Trim()
if ($version -notmatch '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$') { throw 'Invalid desktop/VERSION' }
Push-Location $repo
try {
    if (!$GatewayExecutable) {
        if (!$IsWindows) { throw 'Building the Rust Windows executable requires Windows. Supply -GatewayExecutable to cross-build the WPF UI with an existing Windows x64 backend.' }
        Invoke-Checked $Cargo @('build', '--locked', '--release', '--target', 'x86_64-pc-windows-msvc')
        $GatewayExecutable = Join-Path $repo 'target/x86_64-pc-windows-msvc/release/umbod-gateway.exe'
    }
    if (!(Test-Path -LiteralPath $GatewayExecutable -PathType Leaf)) { throw "Missing Windows gateway: $GatewayExecutable" }
    # Unique staging avoids mixing stale outputs and never deletes a user-supplied directory.
    New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
    $publish = Join-Path $OutputDirectory ('publish-' + [Guid]::NewGuid().ToString('N'))
    Invoke-Checked $Dotnet @('publish', 'windows/Umbod.Windows/Umbod.Windows.csproj', '-c', 'Release',
        "-p:Version=$version", '-r', 'win-x64', '--self-contained', 'true', '-p:EnableWindowsTargeting=true', '-o', $publish)
    Copy-Item -LiteralPath $GatewayExecutable -Destination (Join-Path $publish 'umbod-gateway.exe')
    [IO.File]::WriteAllText((Join-Path $publish 'umbod-profile'), "$Channel`n", [Text.UTF8Encoding]::new($false))
    Write-Host "Built $publish"
    # The caller receives only this object; native build output remains visible through Out-Host.
    return $publish
} finally { Pop-Location }
