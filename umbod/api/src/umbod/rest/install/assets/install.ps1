[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BaseUrl,
    [Parameter(Mandatory = $true)][string]$ExpectedEndpoint,
    [Parameter(Mandatory = $true)][ValidateSet('codex', 'claude-code')][string]$Harness,
    [ValidateSet('windows')][string]$Platform = 'windows'
)

& {
    $ErrorActionPreference = 'Stop'
    Set-StrictMode -Version Latest

    function Assert-SafeUrl([string]$Value) {
        if (-not $Value -or $Value -match '[\s\x00-\x1f\x7f]') { throw 'URL must not contain whitespace or control characters' }
        if ($Value -match '[\\${}?#]') { throw 'URL must not contain placeholders, backslashes, a query, or a fragment' }
        $Parsed = $null
        if (-not [Uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$Parsed)) { throw 'An absolute HTTPS URL is required' }
        $Authority = [regex]::Match($Value, '\A[A-Za-z][A-Za-z0-9+.-]*://([^/]*)')
        if (-not $Authority.Success -or -not $Parsed.Host -or $Authority.Groups[1].Value.Contains('@') -or $Parsed.Scheme -notin @('https', 'http')) { throw 'An absolute HTTPS URL without credentials is required' }
        if ($Parsed.Scheme -eq 'http') {
            $Address = $null
            $Loopback = $Parsed.DnsSafeHost -eq 'localhost'
            if ([Net.IPAddress]::TryParse($Parsed.DnsSafeHost, [ref]$Address)) { $Loopback = [Net.IPAddress]::IsLoopback($Address) }
            if (-not $Loopback) { throw 'HTTP is allowed only for loopback hosts' }
        }
        return $Value
    }

    function Invoke-Harness([string[]]$Arguments) {
        $Stage = if ($Arguments -contains '--help') { 'Checking plugin command support' } elseif ($Arguments[0] -eq 'mcp') { 'Inspecting standalone MCP connections' } elseif ($Arguments[1] -eq 'list') { 'Inspecting local plugins' } elseif ($Arguments -contains 'list') { 'Inspecting configured marketplaces' } else { 'Registering Umbod plugin' }
        Write-Host "$Stage for $Cli..."
        $Output = & $Cli @Arguments 2>&1
        if ($LASTEXITCODE -ne 0) { throw "Harness command failed: $($Arguments -join ' '). Check the harness configuration and retry." }
        return ($Output -join "`n")
    }

    function Get-Metadata([string]$Path, [string]$Pattern) {
        $Bytes = [IO.File]::ReadAllBytes($Path)
        if ($Bytes.Length -gt 2048) { throw 'Invalid installer metadata' }
        $Value = [Text.UTF8Encoding]::new($false, $true).GetString($Bytes)
        if ($Value -cnotmatch "\A(?:$Pattern)\n\z") { throw "Invalid installer metadata: $Path" }
        return $Value.Substring(0, $Value.Length - 1)
    }

    function Get-EndpointIdentity([string]$Endpoint) {
        $Hasher = [Security.Cryptography.SHA256]::Create()
        try { return ([BitConverter]::ToString($Hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($Endpoint)))).Replace('-', '').ToLowerInvariant() } finally { $Hasher.Dispose() }
    }

    function Assert-NoLinks([string]$Path) {
        $Current = [IO.Path]::GetFullPath($Path)
        while ($Current) {
            if (Test-Path -LiteralPath $Current) {
                if ((Get-Item -Force -LiteralPath $Current).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing a linked installation directory' }
            }
            $Current = [IO.Path]::GetDirectoryName($Current)
        }
    }

    $Temporary = $null
    $Staging = $null
    $LockStream = $null
    $LockPath = $null
    try {
        if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Unsupported platform. Use install.sh on macOS or Linux.' }
        $Expected = Assert-SafeUrl $ExpectedEndpoint
        if (-not $Expected.EndsWith('/mcp')) { throw 'Expected endpoint must be a normalized MCP URL' }
        $Base = Assert-SafeUrl $BaseUrl.TrimEnd('/')
        if (-not ([Uri]$Base).AbsolutePath.EndsWith('/install/v1')) { throw 'Base URL must end with /install/v1' }
        $Cli = if ($Harness -eq 'codex') { 'codex' } else { 'claude' }
        Write-Host "Checking $Harness installer prerequisites..."
        foreach ($Command in @('curl.exe', $Cli)) {
            if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) { throw "Required command is missing: $Command" }
        }
        $Action = if ($Cli -eq 'codex') { 'add' } else { 'install' }
        $null = Invoke-Harness -Arguments @('plugin', 'marketplace', 'add', '--help')
        $null = Invoke-Harness -Arguments @('plugin', $Action, '--help')
        $null = Invoke-Harness -Arguments @('plugin', 'marketplace', 'list', '--help')
        $ExpectedMarketplace = 'umbod-' + (Get-EndpointIdentity $Expected).Substring(0, 12)
        $Marketplaces = @(ConvertFrom-Json (Invoke-Harness -Arguments @('plugin', 'marketplace', 'list', '--json')))
        if ($Cli -eq 'codex') {
            $Marketplaces = @($Marketplaces[0].marketplaces)
            $Names = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
            $null = $Names.Add($ExpectedMarketplace)
            foreach ($ConfiguredMarketplace in $Marketplaces) {
                $Name = $ConfiguredMarketplace.name
                if ($Name -isnot [string] -or -not $Name) { throw 'Unsupported marketplace name; update your harness' }
                if ($Name -ceq 'openai-curated-remote') { throw 'A configured marketplace uses the reserved Codex remote catalog name. Review your local marketplaces manually; nothing was changed.' }
                $null = $Names.Add($Name)
            }
            $InitialPlugins = @()
            foreach ($Name in $Names) {
                $Response = ConvertFrom-Json (Invoke-Harness -Arguments @('plugin', 'list', '--json', '--marketplace', $Name))
                $InitialPlugins += @($Response.installed)
            }
        } else {
            $InitialPlugins = @(ConvertFrom-Json (Invoke-Harness -Arguments @('plugin', 'list', '--json')))
        }
        foreach ($Plugin in $InitialPlugins) {
            $PluginIdentity = if ($Cli -eq 'codex') { $Plugin.pluginId } else { $Plugin.id }
            if ($PluginIdentity.StartsWith('umbod@') -and $PluginIdentity -cne "umbod@$ExpectedMarketplace" -and $Plugin.enabled -eq $true) { throw 'An active Umbod plugin for another instance exists. Review your harness plugin list and resolve it manually; nothing was replaced.' }
            if ($PluginIdentity -ceq "umbod@$ExpectedMarketplace" -and $Plugin.enabled -ne $true) { throw 'The Umbod plugin is already installed but disabled. Review your harness plugin settings manually.' }
        }
        if ($Cli -eq 'codex') {
            $Servers = @(ConvertFrom-Json (Invoke-Harness -Arguments @('mcp', 'list', '--json', '--disable', 'plugins')))
            $Conflict = @($Servers | Where-Object { $_.name -ieq 'umbod' }).Count -gt 0
        } else {
            $ErrorActionPreference = 'Continue'
            Write-Host "Inspecting standalone MCP connections for $Cli..."
            try { $Inspection = & $Cli mcp get umbod 2>&1; $Conflict = $LASTEXITCODE -eq 0 } finally { $ErrorActionPreference = 'Stop' }
            if (-not $Conflict -and ($Inspection -join "`n") -notlike '*No MCP server named "umbod"*') { throw 'Could not safely inspect standalone MCP connections; run claude mcp get umbod' }
        }
        if ($Conflict) { throw "A standalone umbod MCP connection already exists. Review it with $Cli mcp get umbod and resolve it manually before retrying; nothing was removed." }
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $Temporary = Join-Path ([IO.Path]::GetTempPath()) ('umbod-install-' + [Guid]::NewGuid().ToString('N'))
        $null = [IO.Directory]::CreateDirectory($Temporary)
        Write-Host 'Downloading and verifying Umbod plugin...'
        foreach ($Name in @('package.zip', 'package.sha256', 'marketplace.txt', 'endpoint.txt')) {
            & curl.exe -fsSL --proto '=https,http' --proto-redir '=https' --max-redirs 3 --connect-timeout 10 --max-time 120 --max-filesize 10485760 --output (Join-Path $Temporary $Name) "$Base/$Harness/$Name"
            if ($LASTEXITCODE -ne 0) { throw "Download failed: $Name" }
        }
        $Digest = Get-Metadata (Join-Path $Temporary 'package.sha256') '[0-9a-f]{64}'
        $Marketplace = Get-Metadata (Join-Path $Temporary 'marketplace.txt') 'umbod-[0-9a-f]{12}'
        $Endpoint = Assert-SafeUrl (Get-Metadata (Join-Path $Temporary 'endpoint.txt') '[^\r\n]+')
        if ($Endpoint -cne $Expected) { throw 'Downloaded endpoint does not match -ExpectedEndpoint; no configuration was changed' }
        $Identity = Get-EndpointIdentity $Endpoint
        if ($Marketplace -cne ('umbod-' + $Identity.Substring(0, 12))) { throw 'Marketplace does not match endpoint identity' }
        if ((Get-FileHash -LiteralPath (Join-Path $Temporary 'package.zip') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $Digest) { throw 'Package SHA256 mismatch; no configuration was changed' }
        $Catalog = if ($Cli -eq 'codex') { '.agents/plugins/marketplace.json' } else { '.claude-plugin/marketplace.json' }
        $Manifest = if ($Cli -eq 'codex') { 'plugins/umbod/.codex-plugin/plugin.json' } else { 'plugins/umbod/.claude-plugin/plugin.json' }
        $Allowed = @($Catalog, $Manifest, 'plugins/umbod/.mcp.json', 'plugins/umbod/skills/umbod-connected-apps/SKILL.md', 'plugins/umbod/LICENSE')
        $Extracted = Join-Path $Temporary 'extracted'
        $null = [IO.Directory]::CreateDirectory($Extracted)
        $Archive = [IO.Compression.ZipFile]::OpenRead((Join-Path $Temporary 'package.zip'))
        try {
            $Seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
            foreach ($Entry in $Archive.Entries) {
                $Mode = ($Entry.ExternalAttributes -shr 16) -band 61440
                if ($Allowed -cnotcontains $Entry.FullName -or -not $Seen.Add($Entry.FullName) -or $Mode -notin @(0, 32768) -or $Entry.Length -gt 2097152) { throw 'Package contains unexpected, duplicate, unsafe, or oversized ZIP entries' }
                $Target = Join-Path $Extracted $Entry.FullName
                $null = [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Target))
                [IO.Compression.ZipFileExtensions]::ExtractToFile($Entry, $Target)
            }
            if ($Seen.Count -ne $Allowed.Count) { throw 'Package is missing required entries' }
        } finally { $Archive.Dispose() }
        $CatalogData = Get-Content -Raw -LiteralPath (Join-Path $Extracted $Catalog) | ConvertFrom-Json
        if ($CatalogData.name -cne $Marketplace) { throw 'Package marketplace identity mismatch' }
        if (@($CatalogData.PSObject.Properties | Where-Object { @('name', 'plugins', 'interface', 'owner') -cnotcontains $_.Name }).Count -gt 0) { throw 'Package marketplace contains unsupported configuration' }
        if (@($CatalogData.plugins).Count -ne 1 -or $CatalogData.plugins[0].name -cne 'umbod') { throw 'Package marketplace source is unsafe' }
        if (@($CatalogData.plugins[0].PSObject.Properties | Where-Object { @('name', 'source', 'policy', 'category') -cnotcontains $_.Name }).Count -gt 0) { throw 'Package marketplace plugin contains unsupported configuration' }
        if ($Cli -eq 'codex') {
            if (@($CatalogData.plugins[0].source.PSObject.Properties).Count -ne 2) { throw 'Package marketplace source is unsafe' }
            if ($CatalogData.plugins[0].source.source -cne 'local' -or $CatalogData.plugins[0].source.path -cne './plugins/umbod') { throw 'Package marketplace source is unsafe' }
        } elseif ($CatalogData.plugins[0].source -cne './plugins/umbod') { throw 'Package marketplace source is unsafe' }
        $ManifestData = Get-Content -Raw -LiteralPath (Join-Path $Extracted $Manifest) | ConvertFrom-Json
        if ($ManifestData.version -cnotmatch '\A[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?\z') { throw 'Package plugin version is unsafe' }
        $ManifestKeys = @('name', 'version', 'description', 'author', 'homepage', 'repository', 'license', 'skills', 'mcpServers')
        if (@($ManifestData.PSObject.Properties | Where-Object { $ManifestKeys -cnotcontains $_.Name }).Count -gt 0 -or $ManifestData.name -cne 'umbod' -or $ManifestData.skills -cne './skills/' -or $ManifestData.mcpServers -cne './.mcp.json') { throw 'Package plugin manifest is unsafe' }
        $McpData = Get-Content -Raw -LiteralPath (Join-Path $Extracted 'plugins/umbod/.mcp.json') | ConvertFrom-Json
        if (@($McpData.PSObject.Properties).Count -ne 1 -or @($McpData.mcpServers.PSObject.Properties).Count -ne 1 -or @($McpData.mcpServers.umbod.PSObject.Properties).Count -ne 2 -or $McpData.mcpServers.umbod.type -cne 'http' -or $McpData.mcpServers.umbod.url -cne $Endpoint) { throw 'Package MCP endpoint mismatch' }
        $MarkerName = '.umbod-install.json'
        $Marker = [ordered]@{ schema = 1; endpoint = $Endpoint; harness = $Harness; marketplace = $Marketplace; sha256 = $Digest } | ConvertTo-Json -Compress
        [IO.File]::WriteAllText((Join-Path $Extracted $MarkerName), $Marker)
        $OwnedFiles = @($Allowed) + @($MarkerName)
        $Root = $env:LOCALAPPDATA
        if (-not $Root -or -not [IO.Path]::IsPathRooted($Root)) { throw 'LOCALAPPDATA must identify an absolute user-owned directory' }
        $Root = [IO.Path]::GetFullPath($Root)
        $Parent = Join-Path $Root "Umbod/plugins/$Marketplace/$Harness"
        Assert-NoLinks $Parent
        $Ancestor = $Parent
        while ($Ancestor -and $Ancestor.Length -ge $Root.Length) {
            if (Test-Path -LiteralPath $Ancestor) {
                $AncestorOwner = (Get-Acl -LiteralPath $Ancestor).GetOwner([Security.Principal.SecurityIdentifier])
                if (-not $AncestorOwner.Equals([Security.Principal.WindowsIdentity]::GetCurrent().User)) { throw 'Installation directory ancestors must be owned by the current user' }
            }
            $Ancestor = [IO.Path]::GetDirectoryName($Ancestor)
        }
        $null = [IO.Directory]::CreateDirectory($Parent)
        $Owner = (Get-Acl -LiteralPath $Parent).GetOwner([Security.Principal.SecurityIdentifier])
        if ($Owner -ne [Security.Principal.WindowsIdentity]::GetCurrent().User) { throw 'Installation directory must be owned by the current user' }
        $LockPath = Join-Path $Parent '.install.lock'
        try { $LockStream = [IO.File]::Open($LockPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None) } catch { throw "Another installation is running or a stale lock exists: $LockPath. Retry after it finishes; review stale locks manually." }
        $Destination = Join-Path $Parent $Digest
        Assert-NoLinks $Destination
        if (Test-Path -LiteralPath $Destination) {
            $Files = @(Get-ChildItem -Force -Recurse -LiteralPath $Destination | Where-Object { -not $_.PSIsContainer -or ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) })
            if ($Files.Count -ne $OwnedFiles.Count) { throw 'Existing content-addressed installation was modified; review it manually' }
            foreach ($Name in $OwnedFiles) {
                $Installed = Join-Path $Destination $Name
                Assert-NoLinks $Installed
                if (-not (Test-Path -LiteralPath $Installed -PathType Leaf) -or (Get-FileHash -LiteralPath $Installed).Hash -ne (Get-FileHash -LiteralPath (Join-Path $Extracted $Name)).Hash) { throw 'Existing content-addressed installation was modified; review it manually' }
            }
        } else {
            $Staging = Join-Path $Parent ('.staging-' + [Guid]::NewGuid().ToString('N'))
            $null = [IO.Directory]::CreateDirectory($Staging)
            foreach ($Name in $OwnedFiles) {
                $Target = Join-Path $Staging $Name
                $null = [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Target))
                [IO.File]::Copy((Join-Path $Extracted $Name), $Target)
            }
            [IO.Directory]::Move($Staging, $Destination)
            $Staging = $null
        }
        $ExistingPlugins = @($InitialPlugins | Where-Object { $(if ($Cli -eq 'codex') { $_.pluginId } else { $_.id }) -ceq "umbod@$Marketplace" })
        if ($ExistingPlugins.Count -gt 1) { throw 'Multiple Umbod plugin registrations exist; review your harness plugin settings manually' }
        if ($ExistingPlugins.Count -eq 1) {
            $ExistingSource = if ($Cli -eq 'codex') { $ExistingPlugins[0].source.path } else { $ExistingPlugins[0].readFromFolder }
            if (-not $ExistingSource -or [IO.Path]::GetFullPath($ExistingSource) -ne [IO.Path]::GetFullPath((Join-Path $Destination 'plugins/umbod')) -or ($Cli -eq 'claude' -and $ExistingPlugins[0].scope -cne 'user')) { throw 'The existing Umbod plugin uses another source or scope. Review your harness plugin settings manually; nothing was replaced.' }
        }
        $Matches = @($Marketplaces | Where-Object { $_.name -ceq $Marketplace })
        if ($Matches.Count -gt 0) {
            $Registered = if ($Cli -eq 'codex') { $Matches[0].root } else { $Matches[0].path }
            if ($Matches.Count -ne 1 -or [IO.Path]::GetFullPath($Registered) -ne [IO.Path]::GetFullPath($Destination)) { throw 'Marketplace already exists at another path. Review it manually; nothing was replaced.' }
        } else {
            Write-Host (Invoke-Harness -Arguments @('plugin', 'marketplace', 'add', $Destination))
        }
        $InstallArguments = @('plugin', $Action, "umbod@$Marketplace")
        if ($Cli -eq 'claude') { $InstallArguments += @('--scope', 'user') }
        if ($ExistingPlugins.Count -eq 1) { Write-Host 'Umbod plugin already installed; verifying registration...' } else { Write-Host (Invoke-Harness -Arguments $InstallArguments) }
        Write-Host "Verifying $Harness plugin registration..."
        $VerificationArguments = @('plugin', 'list', '--json')
        if ($Cli -eq 'codex') { $VerificationArguments += @('--marketplace', $Marketplace) }
        $Installed = @(ConvertFrom-Json (Invoke-Harness -Arguments $VerificationArguments))
        if ($Cli -eq 'codex') {
            $Verified = @($Installed[0].installed | Where-Object { $_.pluginId -ceq "umbod@$Marketplace" -and $_.enabled -eq $true })
        } else {
            $Verified = @($Installed | Where-Object { $_.id -ceq "umbod@$Marketplace" -and $_.enabled -eq $true -and $_.scope -ceq 'user' })
        }
        if ($Verified.Count -ne 1) { throw 'The intended Umbod plugin is not enabled; review your harness plugin settings' }
        $PluginSource = if ($Cli -eq 'codex') { $Verified[0].source.path } else { $Verified[0].readFromFolder }
        if (-not $PluginSource -or [IO.Path]::GetFullPath($PluginSource) -ne [IO.Path]::GetFullPath((Join-Path $Destination 'plugins/umbod'))) { throw 'The installed Umbod plugin source could not be verified; review your harness plugin settings' }
        $HarnessName = if ($Harness -eq 'codex') { 'Codex' } else { 'Claude Code' }
        Write-Host ''
        Write-Host '      |'
        Write-Host '      |'
        Write-Host '     /|\'
        Write-Host '    / | \'
        Write-Host '   |  |  |'
        Write-Host '   |     |'
        Write-Host ''
        Write-Host '   Umbod'
        Write-Host ''
        Write-Host "Umbod plugin installed for ${HarnessName}. Plugin registration verified."
        Write-Host ''
        Write-Host "1. Restart ${HarnessName}."
        Write-Host '2. Open /mcp and sign in if prompted.'
        Write-Host '3. Ask your agent to discover available Umbod connected apps.'
        Write-Host ''
        Write-Host 'Connection has not been verified. Installation does not verify access to connected apps.'
        Write-Host ''
    } catch {
        Write-Error "Umbod installation stopped: $_"
        exit 1
    } finally {
        if ($LockStream) { $LockStream.Dispose(); [IO.File]::Delete($LockPath) }
        if ($Staging -and [IO.Directory]::Exists($Staging)) { [IO.Directory]::Delete($Staging, $true) }
        if ($Temporary -and [IO.Directory]::Exists($Temporary)) { [IO.Directory]::Delete($Temporary, $true) }
    }
}
