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


    function Initialize-TelemetrySupport {
        Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;

public static class UmbodTelemetrySettings {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool MoveFileEx(string source, string destination, int flags);

    public static void Publish(string source, string destination, bool replace) {
        const int writeThrough = 8;
        const int replaceExisting = 1;
        if (!MoveFileEx(source, destination, writeThrough | (replace ? replaceExisting : 0)))
            throw new InvalidOperationException("Could not publish settings");
    }

    public sealed class Value {
        public Dictionary<string, Value> Fields;
        public string Text;
        public int Opening;
        public int End;
    }

    private static readonly Regex Token = new Regex(
        @"\G[ \t\r\n]*(?:""(?<text>(?:[^""\\\x00-\x1f]|\\(?:[""\\/bfnrt]|u[0-9a-fA-F]{4}))*)""|[{}\[\]:,]|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|true|false|null)",
        RegexOptions.CultureInvariant, TimeSpan.FromSeconds(2));

    private static readonly Regex Escape = new Regex(@"\\(u[0-9a-fA-F]{4}|[""\\/bfnrt])");
    private static readonly UTF8Encoding Utf8 = new UTF8Encoding(false, true);

    private static Exception Invalid() { return new FormatException("Invalid or ambiguous JSON"); }

    private static string Decode(Match token) {
        string decoded = Escape.Replace(token.Groups["text"].Value, match => {
            string code = match.Groups[1].Value;
            if (code.Length == 5) return ((char)Int32.Parse(code.Substring(1), NumberStyles.HexNumber)).ToString();
            int escaped = "bfnrt".IndexOf(code[0]);
            return escaped < 0 ? code : "\b\f\n\r\t"[escaped].ToString();
        });
        Utf8.GetByteCount(decoded);
        return decoded;
    }

    private sealed class Reader {
        private readonly string source;
        private int cursor;
        private Match token;

        internal Reader(string source) { this.source = source; Next(); }

        private void Next() {
            while (cursor < source.Length && " \t\r\n".IndexOf(source[cursor]) >= 0) cursor++;
            token = Token.Match(source, cursor);
            if (cursor < source.Length && !token.Success) throw Invalid();
        }

        private bool Is(string raw) { return token.Success && token.Value == raw; }

        private void Skip() { cursor += token.Length; Next(); }

        private void Require(string raw) {
            if (!Is(raw)) throw Invalid();
            Skip();
        }

        internal Value Read(int depth) {
            if (depth > 64 || !token.Success) throw Invalid();
            Value value = new Value();
            if (Is("{")) {
                value.Opening = cursor;
                value.Fields = new Dictionary<string, Value>(StringComparer.Ordinal);
                var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                Skip();
                if (!Is("}")) {
                    do {
                        if (!token.Success || !token.Groups["text"].Success) throw Invalid();
                        string key = Decode(token);
                        if (!seen.Add(key)) throw Invalid();
                        Skip();
                        Require(":");
                        value.Fields.Add(key, Read(depth + 1));
                        if (!Is(",")) break;
                        Skip();
                    } while (true);
                }
                Require("}");
            } else if (Is("[")) {
                Skip();
                if (!Is("]")) {
                    do {
                        Read(depth + 1);
                        if (!Is(",")) break;
                        Skip();
                    } while (true);
                }
                Require("]");
            } else {
                if (Is("}") || Is("]") || Is(":") || Is(",")) throw Invalid();
                if (token.Groups["text"].Success) {
                    value.Text = Decode(token);
                    value.Opening = cursor;
                    value.End = cursor + token.Length;
                }
                Skip();
            }
            if (depth == 0 && cursor != source.Length) throw Invalid();
            return value;
        }
    }

    public static Dictionary<string, Value> Object(string source) {
        Value root = new Reader(source).Read(0);
        if (root.Fields == null) throw Invalid();
        return root.Fields;
    }

    public static string Merge(string source, IDictionary<string, string> desired) {
        Value root = new Reader(source).Read(0);
        if (root.Fields == null) throw Invalid();
        Value env;
        foreach (string key in root.Fields.Keys)
            if (key.Equals("otelHeadersHelper", StringComparison.OrdinalIgnoreCase)
                || (key != "env" && key.Equals("env", StringComparison.OrdinalIgnoreCase))) throw Invalid();
        bool hasEnv = root.Fields.TryGetValue("env", out env);
        Value section = hasEnv ? env : root;
        if (section.Fields == null) throw Invalid();

        const string header = "OTEL_EXPORTER_OTLP_LOGS_HEADERS";
        Value previous = null;
        bool rotate = hasEnv && env.Fields.TryGetValue(header, out previous) && previous.Text != null
            && previous.Text != desired[header]
            && Regex.IsMatch(previous.Text, @"\AAuthorization=Bearer umbod_pat_v1_[0-9a-f]{32}_[A-Za-z0-9_-]{43}\z");
        if (rotate) {
            foreach (var pair in desired) {
                Value actual;
                if (pair.Key != header && (!env.Fields.TryGetValue(pair.Key, out actual) || actual.Text != pair.Value)) {
                    rotate = false;
                    break;
                }
            }
        }
        if (hasEnv) {
            foreach (var pair in env.Fields) {
                string key = pair.Key;
                bool telemetry = key.StartsWith("OTEL_", StringComparison.OrdinalIgnoreCase)
                    || key.StartsWith("CLAUDE_CODE_OTEL_", StringComparison.OrdinalIgnoreCase)
                    || key.Equals("CLAUDE_CODE_ENABLE_TELEMETRY", StringComparison.OrdinalIgnoreCase);
                string expected;
                if (telemetry && (!desired.TryGetValue(key, out expected) || pair.Value.Text != expected) && !(rotate && key == header))
                    throw new InvalidOperationException("Conflicting telemetry");
            }
        }
        if (rotate) return source.Substring(0, previous.Opening) + "\"" + desired[header] + "\"" + source.Substring(previous.End);
        var fields = new List<string>();
        foreach (var pair in desired)
            if (!hasEnv || !env.Fields.ContainsKey(pair.Key))
                fields.Add("\"" + pair.Key + "\": \"" + pair.Value + "\"");
        if (fields.Count == 0) return source;
        string added = String.Join(", ", fields);
        if (!hasEnv) added = "\"env\": {" + added + "}";
        return source.Insert(section.Opening + 1, "\n  " + added + (section.Fields.Count > 0 ? "," : "\n"));
    }
}
'@
    }

    function Read-TelemetryPayload([string]$Encoded) {
        try {
            if ($Encoded.Length -gt 8192 -or $Encoded -cnotmatch '\A[A-Za-z0-9+/]+={0,2}\z') { throw 'Invalid encoding' }
            $Bytes = [Convert]::FromBase64String($Encoded)
            if ([Convert]::ToBase64String($Bytes) -cne $Encoded) { throw 'Noncanonical encoding' }
            Initialize-TelemetrySupport
            $Payload = [UmbodTelemetrySettings]::Object([Text.UTF8Encoding]::new($false, $true).GetString($Bytes))
            if ($Payload.Count -ne 2 -or -not $Payload.ContainsKey('endpoint') -or -not $Payload.ContainsKey('token')) { throw 'Unexpected keys' }
            $Endpoint = $Payload['endpoint'].Text
            $Token = $Payload['token'].Text
            if (-not $Endpoint -or $Endpoint.Length -gt 2048 -or $Endpoint -cnotmatch '\A[A-Za-z0-9:/._~!&''()*+,;=@%\[\]-]+\z' -or
                $Endpoint -match '%(?:[01][0-9a-f]|7f)|%(?![0-9a-f]{2})' -or
                $Endpoint -notmatch '\Ahttps?://(?:\[[a-f0-9:.]+\]|[a-z0-9.-]+)(?::[0-9]+)?/') { throw 'Invalid endpoint' }
            $null = Assert-SafeUrl $Endpoint
            if (-not $Endpoint.EndsWith('/v1/logs', [StringComparison]::Ordinal) -or -not ([Uri]$Endpoint).AbsolutePath.EndsWith('/v1/logs', [StringComparison]::Ordinal)) { throw 'Invalid logs path' }
            if ($Token -cnotmatch '\Aumbod_pat_v1_[0-9a-f]{32}_[A-Za-z0-9_-]{43}\z') { throw 'Invalid token' }
            $Values = [Collections.Generic.Dictionary[string,string]]::new([StringComparer]::Ordinal)
            $Values['CLAUDE_CODE_ENABLE_TELEMETRY'] = '1'
            $Values['OTEL_LOGS_EXPORTER'] = 'otlp'
            $Values['OTEL_EXPORTER_OTLP_LOGS_PROTOCOL'] = 'http/json'
            $Values['OTEL_EXPORTER_OTLP_LOGS_ENDPOINT'] = $Endpoint
            $Values['OTEL_EXPORTER_OTLP_LOGS_HEADERS'] = 'Authorization=Bearer ' + $Token
            $Values['OTEL_METRICS_EXPORTER'] = 'none'
            $Values['OTEL_TRACES_EXPORTER'] = 'none'
            $Values['OTEL_LOG_USER_PROMPTS'] = '0'
            $Values['OTEL_LOG_ASSISTANT_RESPONSES'] = '0'
            $Values['OTEL_LOG_TOOL_DETAILS'] = '0'
            $Values['OTEL_LOG_TOOL_CONTENT'] = '0'
            $Values['OTEL_LOG_RAW_API_BODIES'] = '0'
            return ,$Values
        } catch { throw 'Invalid Claude Code telemetry payload' }
    }

    function Get-TelemetryFileAttributes([string]$Path) {
        try { return [IO.File]::GetAttributes($Path) } catch [IO.FileNotFoundException], [IO.DirectoryNotFoundException] { return $null }
    }

    function Assert-TelemetryPath([string]$Path, [Security.Principal.SecurityIdentifier]$Owner, [bool]$Directory) {
        $Attributes = Get-TelemetryFileAttributes $Path
        if ($null -eq $Attributes) { return $false }
        if (($Attributes -band [IO.FileAttributes]::ReparsePoint) -or [bool]($Attributes -band [IO.FileAttributes]::Directory) -ne $Directory) { throw 'Unsafe settings path' }
        $Security = Get-Acl -LiteralPath $Path
        if (-not $Owner.Equals($Security.GetOwner([Security.Principal.SecurityIdentifier]))) { throw 'Settings must be user-owned' }
        foreach ($Rule in $Security.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
            $InheritableOwner = $Rule.IdentityReference.Value -eq 'S-1-3-0' -and ($Rule.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly)
            if ($Rule.AccessControlType -eq 'Allow' -and ($Rule.FileSystemRights -band 0xD0156) -and -not $InheritableOwner -and
                $Rule.IdentityReference.Value -notin @($Owner.Value, 'S-1-5-18', 'S-1-5-32-544')) { throw 'Settings cannot be writable by others' }
        }
        return $true
    }

    function Read-ClaudeSettings([string]$Path, [Security.Principal.SecurityIdentifier]$Owner) {
        if (-not (Assert-TelemetryPath $Path $Owner $false)) { return $null }
        $Stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
        try {
            if ($Stream.Length -gt 1048576) { throw 'Oversized Claude Code settings' }
            $Reader = [IO.BinaryReader]::new($Stream)
            try { return [Text.UTF8Encoding]::new($false, $true).GetString($Reader.ReadBytes([int]$Stream.Length)) }
            finally { $Reader.Dispose() }
        } finally { $Stream.Dispose() }
    }

    function Save-ClaudeSettings([string]$Path, [string]$Updated, $Original, [Security.Principal.SecurityIdentifier]$Owner) {
        $TemporarySettings = Join-Path ([IO.Path]::GetDirectoryName($Path)) ('.umbod-settings-' + [Guid]::NewGuid().ToString('N'))
        $Stream = [IO.File]::Open($TemporarySettings, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try {
            $Stream.Dispose()
            $Security = [Security.AccessControl.FileSecurity]::new()
            $Security.SetOwner($Owner)
            $Security.SetAccessRuleProtection($true, $false)
            $Security.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($Owner, 'FullControl', 'Allow'))
            Set-Acl -LiteralPath $TemporarySettings -AclObject $Security
            $Applied = Get-Acl -LiteralPath $TemporarySettings
            $Rules = @($Applied.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
            if (-not $Applied.AreAccessRulesProtected -or -not $Owner.Equals($Applied.GetOwner([Security.Principal.SecurityIdentifier])) -or
                $Rules.Count -ne 1 -or -not $Owner.Equals($Rules[0].IdentityReference) -or $Rules[0].AccessControlType -ne 'Allow') { throw 'Could not restrict settings access' }
            $Stream = [IO.File]::Open($TemporarySettings, [IO.FileMode]::Open, [IO.FileAccess]::Write, [IO.FileShare]::None)
            $Bytes = [Text.UTF8Encoding]::new($false, $true).GetBytes($Updated)
            $Stream.Write($Bytes, 0, $Bytes.Length)
            $Stream.Flush($true)
            $Stream.Dispose()
            if ((Read-ClaudeSettings $Path $Owner) -cne $Original) { throw 'Settings changed during installation' }
            [UmbodTelemetrySettings]::Publish($TemporarySettings, $Path, ($null -ne $Original))
        } finally {
            $Stream.Dispose()
            [IO.File]::Delete($TemporarySettings)
        }
    }

    function Update-ClaudeTelemetry($Desired, [bool]$Write) {
        if (Test-Path Env:CLAUDE_CONFIG_DIR) { throw 'Claude Code telemetry requires manual setup when CLAUDE_CONFIG_DIR is set' }
        $TelemetryLock = $null
        try {
            $ProfilePath = [Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)
            if ($ProfilePath -notmatch '\A[A-Za-z]:\\' -or ($env:USERPROFILE -and $env:USERPROFILE -ne $ProfilePath)) { throw 'Expected the default local profile' }
            $Directory = Join-Path $ProfilePath '.claude'
            $Owner = [Security.Principal.WindowsIdentity]::GetCurrent().User
            $Ancestor = $Directory
            while ($Ancestor) {
                if ((Get-TelemetryFileAttributes $Ancestor) -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing linked settings directories' }
                $Ancestor = [IO.Path]::GetDirectoryName($Ancestor)
            }
            if (-not (Assert-TelemetryPath $ProfilePath $Owner $true)) { throw 'Missing user profile' }
            if (-not (Assert-TelemetryPath $Directory $Owner $true)) {
                if (-not $Write) { return }
                $null = [IO.Directory]::CreateDirectory($Directory)
                if (-not (Assert-TelemetryPath $Directory $Owner $true)) { throw 'Unsafe configuration directory' }
            }
            if ($Write) {
                $TelemetryLock = [IO.FileStream]::new((Join-Path $Directory '.umbod-telemetry.lock'), [IO.FileMode]::CreateNew,
                    [IO.FileAccess]::Write, [IO.FileShare]::None, 4096, [IO.FileOptions]::DeleteOnClose)
            }
            $Path = Join-Path $Directory 'settings.json'
            $Original = Read-ClaudeSettings $Path $Owner
            $Source = if ($null -eq $Original) { '{}' } else { $Original }
            $Updated = [UmbodTelemetrySettings]::Merge($Source, $Desired)
            if ($Write) { Save-ClaudeSettings $Path $Updated $Original $Owner }
        } catch {
            if ($Write) { throw 'Plugin registration verified, but Claude Code telemetry was not applied. Review your settings manually before retrying.' }
            throw 'Claude Code telemetry settings could not be safely updated. Review your settings manually before retrying.'
        } finally {
            if ($null -ne $TelemetryLock) { $TelemetryLock.Dispose() }
        }
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

    function Get-FileDigest([string]$Path) {
        $Hasher = [Security.Cryptography.SHA256]::Create()
        $Stream = $null
        try {
            $Stream = [IO.File]::OpenRead($Path)
            return ([BitConverter]::ToString($Hasher.ComputeHash($Stream))).Replace('-', '').ToLowerInvariant()
        } finally {
            if ($Stream) { $Stream.Dispose() }
            $Hasher.Dispose()
        }
    }

    function Get-DirectoryOwner([string]$Path) {
        $Security = [Security.AccessControl.DirectorySecurity]::new($Path, [Security.AccessControl.AccessControlSections]::Owner)
        return $Security.GetOwner([Security.Principal.SecurityIdentifier])
    }

    function Save-Artifact([string]$Address, [string]$Path) {
        $Handler = [Net.Http.HttpClientHandler]::new()
        $Handler.AllowAutoRedirect = $false
        $Client = [Net.Http.HttpClient]::new($Handler)
        $Cancellation = [Threading.CancellationTokenSource]::new(120000)
        $Timer = [Diagnostics.Stopwatch]::StartNew()
        $PreviousTls = [Net.ServicePointManager]::SecurityProtocol
        try {
            if ($PSVersionTable.PSVersion.Major -lt 6) { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 }
            $Current = [Uri]$Address
            for ($Redirects = 0; $Redirects -le 3; $Redirects++) {
                $Response = $null
                $InputStream = $null
                $OutputStream = $null
                try {
                    $Request = $Client.GetAsync($Current, [Net.Http.HttpCompletionOption]::ResponseHeadersRead, $Cancellation.Token)
                    $Remaining = 120000 - [int]$Timer.ElapsedMilliseconds
                    if ($Remaining -le 0 -or -not $Request.Wait([Math]::Min(10000, $Remaining))) { throw 'Artifact download timed out' }
                    $Response = $Request.GetAwaiter().GetResult()
                    $Status = [int]$Response.StatusCode
                    if ($Status -in @(301, 302, 303, 307, 308)) {
                        if ($Redirects -eq 3 -or $null -eq $Response.Headers.Location) { throw 'Artifact download exceeded the redirect limit or omitted its destination' }
                        $Current = [Uri]::new($Current, $Response.Headers.Location)
                        if ($Current.Scheme -ne 'https' -or $Current.UserInfo) { throw 'Artifact redirects must use HTTPS without credentials' }
                        continue
                    }
                    if (-not $Response.IsSuccessStatusCode) { throw "Artifact download failed with HTTP status $Status" }
                    if ($Response.Content.Headers.ContentLength -gt 10485760) { throw 'Artifact download exceeds the size limit' }
                    $InputStream = $Response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
                    $OutputStream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
                    $Buffer = [byte[]]::new(81920)
                    $Total = 0
                    while ($true) {
                        $Remaining = 120000 - [int]$Timer.ElapsedMilliseconds
                        if ($Remaining -le 0) { throw 'Artifact download timed out' }
                        $Read = $InputStream.ReadAsync($Buffer, 0, $Buffer.Length, $Cancellation.Token)
                        if (-not $Read.Wait($Remaining)) { throw 'Artifact download timed out' }
                        $Count = $Read.GetAwaiter().GetResult()
                        if ($Count -eq 0) { return }
                        $Total += $Count
                        if ($Total -gt 10485760) { throw 'Artifact download exceeds the size limit' }
                        $OutputStream.Write($Buffer, 0, $Count)
                    }
                } finally {
                    if ($OutputStream) { $OutputStream.Dispose() }
                    if ($InputStream) { $InputStream.Dispose() }
                    if ($Response) { $Response.Dispose() }
                }
            }
        } finally {
            $Cancellation.Cancel()
            $Client.Dispose()
            $Cancellation.Dispose()
            [Net.ServicePointManager]::SecurityProtocol = $PreviousTls
        }
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
        $Telemetry = $null
        if (Get-Variable UmbodTelemetryPayload -Scope Script -ErrorAction SilentlyContinue) {
            if ($Harness -ne 'claude-code') { throw 'The telemetry installer hook is supported only for Claude Code' }
            $Telemetry = Read-TelemetryPayload $UmbodTelemetryPayload
            Update-ClaudeTelemetry $Telemetry $false
        }
        $Expected = Assert-SafeUrl $ExpectedEndpoint
        if (-not $Expected.EndsWith('/mcp')) { throw 'Expected endpoint must be a normalized MCP URL' }
        $Base = Assert-SafeUrl $BaseUrl.TrimEnd('/')
        if (-not ([Uri]$Base).AbsolutePath.EndsWith('/install/v1')) { throw 'Base URL must end with /install/v1' }
        $Cli = if ($Harness -eq 'codex') { 'codex' } else { 'claude' }
        Write-Host "Checking $Harness installer prerequisites..."
        if (-not (Get-Command $Cli -ErrorAction SilentlyContinue)) { throw "Required command is missing: $Cli" }
        $Action = if ($Cli -eq 'codex') { 'add' } else { 'install' }
        $null = Invoke-Harness -Arguments @('plugin', 'marketplace', 'add', '--help')
        $null = Invoke-Harness -Arguments @('plugin', $Action, '--help')
        $null = Invoke-Harness -Arguments @('plugin', 'marketplace', 'list', '--help')
        $ExpectedMarketplace = 'umbod-' + (Get-EndpointIdentity $Expected).Substring(0, 12)
        $Marketplaces = @(ConvertFrom-Json (Invoke-Harness -Arguments @('plugin', 'marketplace', 'list', '--json')) | ForEach-Object { $_ })
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
            $InitialPlugins = @(ConvertFrom-Json (Invoke-Harness -Arguments @('plugin', 'list', '--json')) | ForEach-Object { $_ })
        }
        foreach ($Plugin in $InitialPlugins) {
            $PluginIdentity = if ($Cli -eq 'codex') { $Plugin.pluginId } else { $Plugin.id }
            if ($PluginIdentity.StartsWith('umbod@') -and $PluginIdentity -cne "umbod@$ExpectedMarketplace" -and $Plugin.enabled -eq $true) { throw 'An active Umbod plugin for another instance exists. Review your harness plugin list and resolve it manually; nothing was replaced.' }
            if ($PluginIdentity -ceq "umbod@$ExpectedMarketplace" -and $Plugin.enabled -ne $true) { throw 'The Umbod plugin is already installed but disabled. Review your harness plugin settings manually.' }
        }
        if ($Cli -eq 'codex') {
            $Servers = @(ConvertFrom-Json (Invoke-Harness -Arguments @('mcp', 'list', '--json', '--disable', 'plugins')) | ForEach-Object { $_ })
            $Conflict = @($Servers | Where-Object { $_.name -ieq 'umbod' }).Count -gt 0
        } else {
            $ErrorActionPreference = 'Continue'
            Write-Host "Inspecting standalone MCP connections for $Cli..."
            try { $Inspection = & $Cli mcp get umbod 2>&1; $Conflict = $LASTEXITCODE -eq 0 } finally { $ErrorActionPreference = 'Stop' }
            if (-not $Conflict -and ($Inspection -join "`n") -notlike '*No MCP server named "umbod"*') { throw 'Could not safely inspect standalone MCP connections; run claude mcp get umbod' }
        }
        if ($Conflict) { throw "A standalone umbod MCP connection already exists. Review it with $Cli mcp get umbod and resolve it manually before retrying; nothing was removed." }
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        Add-Type -AssemblyName System.Net.Http
        $Temporary = Join-Path ([IO.Path]::GetTempPath()) ('umbod-install-' + [Guid]::NewGuid().ToString('N'))
        $null = [IO.Directory]::CreateDirectory($Temporary)
        Write-Host 'Downloading and verifying Umbod plugin...'
        foreach ($Name in @('package.zip', 'package.sha256', 'marketplace.txt', 'endpoint.txt')) {
            Save-Artifact "$Base/$Harness/$Name" (Join-Path $Temporary $Name)
        }
        $Digest = Get-Metadata (Join-Path $Temporary 'package.sha256') '[0-9a-f]{64}'
        $Marketplace = Get-Metadata (Join-Path $Temporary 'marketplace.txt') 'umbod-[0-9a-f]{12}'
        $Endpoint = Assert-SafeUrl (Get-Metadata (Join-Path $Temporary 'endpoint.txt') '[^\r\n]+')
        if ($Endpoint -cne $Expected) { throw 'Downloaded endpoint does not match -ExpectedEndpoint; no configuration was changed' }
        $Identity = Get-EndpointIdentity $Endpoint
        if ($Marketplace -cne ('umbod-' + $Identity.Substring(0, 12))) { throw 'Marketplace does not match endpoint identity' }
        if ((Get-FileDigest (Join-Path $Temporary 'package.zip')) -cne $Digest) { throw 'Package SHA256 mismatch; no configuration was changed' }
        $Catalog = if ($Cli -eq 'codex') { '.agents/plugins/marketplace.json' } else { '.claude-plugin/marketplace.json' }
        $Manifest = if ($Cli -eq 'codex') { 'plugins/umbod/.codex-plugin/plugin.json' } else { 'plugins/umbod/.claude-plugin/plugin.json' }
        $Allowed = @($Catalog, $Manifest, 'plugins/umbod/.mcp.json', 'plugins/umbod/skills/umbod-connected-apps/SKILL.md', 'plugins/umbod/skills/umbod-agent-behaviour/SKILL.md', 'plugins/umbod/skills/run-diagnostics/SKILL.md', 'plugins/umbod/LICENSE')
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
                $AncestorOwner = Get-DirectoryOwner $Ancestor
                if (-not $AncestorOwner.Equals([Security.Principal.WindowsIdentity]::GetCurrent().User)) { throw 'Installation directory ancestors must be owned by the current user' }
            }
            $Ancestor = [IO.Path]::GetDirectoryName($Ancestor)
        }
        $null = [IO.Directory]::CreateDirectory($Parent)
        $Owner = Get-DirectoryOwner $Parent
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
                if (-not (Test-Path -LiteralPath $Installed -PathType Leaf) -or (Get-FileDigest $Installed) -cne (Get-FileDigest (Join-Path $Extracted $Name))) { throw 'Existing content-addressed installation was modified; review it manually' }
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
        $Installed = @(ConvertFrom-Json (Invoke-Harness -Arguments $VerificationArguments) | ForEach-Object { $_ })
        if ($Cli -eq 'codex') {
            $Verified = @($Installed[0].installed | Where-Object { $_.pluginId -ceq "umbod@$Marketplace" -and $_.enabled -eq $true })
        } else {
            $Verified = @($Installed | Where-Object { $_.id -ceq "umbod@$Marketplace" -and $_.enabled -eq $true -and $_.scope -ceq 'user' })
        }
        if ($Verified.Count -ne 1) { throw 'The intended Umbod plugin is not enabled; review your harness plugin settings' }
        $PluginSource = if ($Cli -eq 'codex') { $Verified[0].source.path } else { $Verified[0].readFromFolder }
        if (-not $PluginSource -or [IO.Path]::GetFullPath($PluginSource) -ne [IO.Path]::GetFullPath((Join-Path $Destination 'plugins/umbod'))) { throw 'The installed Umbod plugin source could not be verified; review your harness plugin settings' }
        if ($null -ne $Telemetry) {
            Update-ClaudeTelemetry $Telemetry $true
            Write-Host 'Claude Code logs-only telemetry settings applied. Delivery has not been verified.'
        }
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
