[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BaseUrl,
    [Parameter(Mandatory = $true)][string]$ExpectedEndpoint,
    [Parameter(Mandatory = $true)][ValidateSet('codex', 'claude-code')][string]$Harness,
    [ValidateSet('windows')][string]$Platform = 'windows',
    [string]$LogsEndpoint = ''
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
        if ('UmbodTelemetrySettings' -as [type]) { return }
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

    [StructLayout(LayoutKind.Sequential)]
    private struct SecurityAttributes {
        public int Length;
        public IntPtr Descriptor;
        public int Inherit;
    }

    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool ConvertStringSecurityDescriptorToSecurityDescriptor(string sddl, uint revision, out IntPtr descriptor, IntPtr size);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool CreateDirectory(string path, ref SecurityAttributes security);

    [DllImport("kernel32.dll")]
    private static extern IntPtr LocalFree(IntPtr memory);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GetFileInformationByHandle(Microsoft.Win32.SafeHandles.SafeFileHandle handle, [Out] uint[] information);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern Microsoft.Win32.SafeHandles.SafeFileHandle CreateFile(string path, uint access, uint share, IntPtr security, uint disposition, uint flags, IntPtr template);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool SetFileInformationByHandle(Microsoft.Win32.SafeHandles.SafeFileHandle handle, int type, IntPtr information, uint size);

    public static void ReplaceLocked(string source, string destination) {
        const int fileRenameInfoEx = 22;
        const int replaceAndPreserveOpenHandles = 3;
        byte[] name = Encoding.Unicode.GetBytes(destination);
        int rootOffset = IntPtr.Size;
        int lengthOffset = rootOffset + IntPtr.Size;
        int nameOffset = lengthOffset + sizeof(int);
        int size = nameOffset + name.Length + sizeof(char);
        IntPtr information = Marshal.AllocHGlobal(size);
        try {
            Marshal.WriteInt32(information, 0, replaceAndPreserveOpenHandles);
            Marshal.WriteIntPtr(information, rootOffset, IntPtr.Zero);
            Marshal.WriteInt32(information, lengthOffset, name.Length);
            Marshal.Copy(name, 0, IntPtr.Add(information, nameOffset), name.Length);
            Marshal.WriteInt16(information, nameOffset + name.Length, 0);
            using (var handle = CreateFile(source, 0x10000, 7, IntPtr.Zero, 3, 0x200000, IntPtr.Zero)) {
                if (handle.IsInvalid || !SetFileInformationByHandle(handle, fileRenameInfoEx, information, (uint)size))
                    throw new InvalidOperationException("Could not atomically replace Codex configuration while locked");
            }
        } finally { Marshal.FreeHGlobal(information); }
    }

    public static void CreatePrivateDirectory(string path, string owner) {
        IntPtr descriptor;
        if (!ConvertStringSecurityDescriptorToSecurityDescriptor("O:" + owner + "D:P(A;OICI;FA;;;" + owner + ")", 1, out descriptor, IntPtr.Zero))
            throw new InvalidOperationException("Could not protect Codex staging directory");
        try {
            var attributes = new SecurityAttributes { Length = Marshal.SizeOf(typeof(SecurityAttributes)), Descriptor = descriptor };
            if (!CreateDirectory(path, ref attributes)) throw new InvalidOperationException("Could not create Codex staging directory");
        } finally { LocalFree(descriptor); }
    }

    public static string FileStamp(System.IO.FileStream stream) {
        var information = new uint[13];
        if (!GetFileInformationByHandle(stream.SafeFileHandle, information) || information[10] != 1 || (information[0] & 0x445400) != 0)
            throw new InvalidOperationException("Unsupported Codex configuration file");
        information[3] = information[4] = 0;
        return String.Join(":", information);
    }

    public sealed class Value {
        public Dictionary<string, Value> Fields;
        public List<Value> Elements;
        public string Text;
        public string Literal;
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
                value.Elements = new List<Value>();
                Skip();
                if (!Is("]")) {
                    do {
                        value.Elements.Add(Read(depth + 1));
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
                } else {
                    value.Literal = token.Value;
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

    private static bool Equivalent(Value left, Value right) {
        if (left.Text != right.Text || left.Literal != right.Literal) return false;
        if (left.Fields != null || right.Fields != null)
            return left.Fields != null && right.Fields != null && EqualFields(left.Fields, right.Fields);
        if (left.Elements == null || right.Elements == null) return left.Elements == right.Elements;
        if (left.Elements.Count != right.Elements.Count) return false;
        for (int i = 0; i < left.Elements.Count; i++) if (!Equivalent(left.Elements[i], right.Elements[i])) return false;
        return true;
    }

    public static bool EqualFields(Dictionary<string, Value> left, Dictionary<string, Value> right, params string[] ignore) {
        var excluded = new HashSet<string>(ignore, StringComparer.Ordinal);
        foreach (var pair in left) {
            Value value;
            if (!excluded.Contains(pair.Key) && (!right.TryGetValue(pair.Key, out value) || !Equivalent(pair.Value, value))) return false;
        }
        foreach (string key in right.Keys) if (!excluded.Contains(key) && !left.ContainsKey(key)) return false;
        return true;
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
        bool rotate = desired.ContainsKey(header) && hasEnv && env.Fields.TryGetValue(header, out previous) && previous.Text != null
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
            return ,(New-TelemetrySettings $Payload['endpoint'].Text $Payload['token'].Text)
        } catch { throw 'Invalid Claude Code telemetry payload' }
    }

    function New-TelemetrySettings([string]$Endpoint, [string]$Token) {
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

    function Update-ClaudeTelemetry([Collections.Generic.Dictionary[string,string]]$Desired, [bool]$Write, [scriptblock]$ResolveClaim) {
        if (Test-Path Env:CLAUDE_CONFIG_DIR) { throw 'Claude Code telemetry requires manual setup when CLAUDE_CONFIG_DIR is set' }
        $TelemetryLock = $null
        $Redeeming = $false
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
            $TelemetryLockPath = Join-Path $Directory '.umbod-telemetry.lock'
            if ($Write) {
                $TelemetryLock = [IO.FileStream]::new($TelemetryLockPath, [IO.FileMode]::CreateNew,
                    [IO.FileAccess]::Write, [IO.FileShare]::None, 4096, [IO.FileOptions]::DeleteOnClose)
            }
            $Path = Join-Path $Directory 'settings.json'
            if ($ResolveClaim -and ((Get-TelemetryFileAttributes $Path) -band [IO.FileAttributes]::ReadOnly)) { throw 'Settings are read-only' }
            $Original = Read-ClaudeSettings $Path $Owner
            $Source = if ($null -eq $Original) { '{}' } else { $Original }
            $Updated = [UmbodTelemetrySettings]::Merge($Source, $Desired)
            if ($ResolveClaim) {
                if ((Read-ClaudeSettings $Path $Owner) -cne $Original) { throw 'Settings changed during installation' }
                $Redeeming = $true
                $Credentials = & $ResolveClaim
                $Redeeming = $false
                $Updated = [UmbodTelemetrySettings]::Merge($Source, $Credentials)
            }
            if ($Write) { Save-ClaudeSettings $Path $Updated $Original $Owner }
        } catch {
            if ($Redeeming) { throw 'Plugin registration verified, but the telemetry claim could not be redeemed. Copy a fresh command from Umbod.' }
            if ($Write) { throw 'Plugin registration verified, but Claude Code telemetry was not applied. Review your settings manually before retrying.' }
            throw 'Claude Code telemetry settings could not be safely updated. Review your settings manually before retrying.'
        } finally {
            if ($null -ne $TelemetryLock) { $TelemetryLock.Dispose() }
        }
    }

    function Redeem-InstallClaim([string]$Address, [string]$Claim, [string]$ExpectedLogsEndpoint) {
        $Handler = [Net.Http.HttpClientHandler]::new()
        $Handler.AllowAutoRedirect = $false
        $Handler.UseCookies = $false
        $Client = [Net.Http.HttpClient]::new($Handler)
        $Response = $null
        $PreviousTls = [Net.ServicePointManager]::SecurityProtocol
        try {
            if ($PSVersionTable.PSVersion.Major -lt 6) { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 }
            $Client.Timeout = [TimeSpan]::FromSeconds(15)
            $Client.MaxResponseContentBufferSize = 8192
            $Client.DefaultRequestHeaders.Authorization = [Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer', $Claim)
            $Request = $Client.PostAsync([Uri]$Address, $null)
            if (-not $Request.Wait(15000)) { throw 'Request timed out' }
            $Response = $Request.GetAwaiter().GetResult()
            if (-not $Response.IsSuccessStatusCode -or $Response.Content.Headers.ContentType.MediaType -ne 'application/json') { throw 'Unexpected response' }
            $Bytes = $Response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
            $Payload = [UmbodTelemetrySettings]::Object([Text.UTF8Encoding]::new($false, $true).GetString($Bytes))
            if ($Payload.Count -ne 2 -or -not $Payload.ContainsKey('token') -or -not $Payload.ContainsKey('logs_endpoint')) { throw 'Unexpected response keys' }
            if ($Payload['logs_endpoint'].Text -cne $ExpectedLogsEndpoint) { throw 'Unexpected telemetry destination' }
            return ,(New-TelemetrySettings $Payload['logs_endpoint'].Text $Payload['token'].Text)
        } catch { throw 'Plugin registration verified, but the telemetry claim could not be redeemed. Request a new claim before retrying.' }
        finally {
            if ($null -ne $Response) { $Response.Dispose() }
            $Client.Dispose()
            [Net.ServicePointManager]::SecurityProtocol = $PreviousTls
        }
    }

    function Resolve-CodexExecutable {
        $Command = Get-Command codex -ErrorAction Stop
        if ($Command.CommandType -eq 'Application' -and [IO.Path]::GetExtension($Command.Source) -ieq '.exe') { return $Command.Source }
        if ($Command.CommandType -notin @('Application', 'ExternalScript') -or [IO.Path]::GetExtension($Command.Source) -notin @('.cmd', '.ps1')) { throw 'Unsupported Codex command' }
        $Root = Join-Path ([IO.Path]::GetDirectoryName($Command.Source)) 'node_modules/@openai'
        $Target = switch ($env:PROCESSOR_ARCHITECTURE) {
            'AMD64' { 'x86_64-pc-windows-msvc' }
            'ARM64' { 'aarch64-pc-windows-msvc' }
            default { throw 'Unsupported Codex architecture' }
        }
        $Architecture = if ($Target.StartsWith('x86_64')) { 'x64' } else { 'arm64' }
        $Package = "codex-win32-$Architecture"
        foreach ($Path in @("codex/node_modules/@openai/$Package", $Package, 'codex')) {
            $Executable = Join-Path $Root "$Path/vendor/$Target/bin/codex.exe"
            if (Test-Path -LiteralPath $Executable -PathType Leaf) { return $Executable }
            $Executable = Join-Path $Root "$Path/vendor/$Target/codex/codex.exe"
            if (Test-Path -LiteralPath $Executable -PathType Leaf) { return $Executable }
        }
        throw 'Codex executable could not be located'
    }

    function Send-CodexRequest([IO.StreamWriter]$Writer, [hashtable]$Message) {
        $Writer.WriteLine(($Message | ConvertTo-Json -Compress -Depth 8))
        $Writer.Flush()
    }

    function Read-CodexResponse([IO.StreamReader]$Reader, [Diagnostics.Stopwatch]$Timer, [int]$Id) {
        while ($true) {
            $Remaining = 15000 - [int]$Timer.ElapsedMilliseconds
            if ($Remaining -le 0) { throw 'Codex inspection timed out' }
            $Read = $Reader.ReadLineAsync()
            if (-not $Read.Wait($Remaining)) { throw 'Codex inspection timed out' }
            $Line = $Read.GetAwaiter().GetResult()
            if (-not $Line -or $Line.Length -gt 1048576) { throw 'Invalid Codex response' }
            $Message = [UmbodTelemetrySettings]::Object($Line)
            if (-not $Message.ContainsKey('id') -or $Message['id'].Literal -cne [string]$Id) { continue }
            if ($Message.ContainsKey('error') -or -not $Message.ContainsKey('result') -or $null -eq $Message['result'].Fields) { throw 'Codex inspection failed' }
            return ,$Message['result'].Fields
        }
    }

    function Get-CodexSetting([object]$Config, [string]$Key) {
        if ($null -ne $Config -and $Config.ContainsKey($Key) -and $Config[$Key].Literal -cne 'null') { return $Config[$Key] }
    }

    function Assert-CodexSettingShape([object]$Value, [object]$Shape) {
        if ($null -eq $Value) { return }
        if ($Shape -is [Collections.IDictionary]) {
            if ($null -eq $Value.Fields) { throw 'Invalid Codex telemetry table' }
            foreach ($Key in $Value.Fields.Keys) {
                $Field = Get-CodexSetting $Value.Fields $Key
                if ($null -eq $Field) { continue }
                if ($Key -cnotin @($Shape.Keys)) { throw 'Unknown Codex telemetry setting' }
                Assert-CodexSettingShape $Field $Shape[$Key]
            }
            return
        }
        $Valid = switch ($Shape) {
            'boolean' { $Value.Literal -cin @('true', 'false') }
            'integer' { $Value.Literal -cmatch '\A(?:0|[1-9][0-9]*)\z' }
            'string' { $null -ne $Value.Text }
            'string map' {
                $null -ne $Value.Fields -and @($Value.Fields.Values | Where-Object { $null -eq $_.Text }).Count -eq 0
            }
            'exporter' {
                if ($Value.Text -cin @('none', 'statsig', 'stdout')) { $true }
                elseif ($null -ne $Value.Fields -and $Value.Fields.Count -eq 1) {
                    $Transport = @($Value.Fields.Keys)[0]
                    $TransportConfig = $Value.Fields[$Transport]
                    if ($null -eq $TransportConfig.Fields -or $null -eq (Get-CodexSetting $TransportConfig.Fields 'endpoint')) { $false }
                    elseif ($Transport -ceq 'otlp-http') {
                        $Tls = @{ ca_certificate = 'string'; client_certificate = 'string'; client_private_key = 'string' }
                        Assert-CodexSettingShape $TransportConfig @{ endpoint = 'string'; headers = 'string map'; protocol = 'string'; tls = $Tls }
                        $Protocol = Get-CodexSetting $TransportConfig.Fields 'protocol'
                        $null -eq $Protocol -or $Protocol.Text -cin @('json', 'binary')
                    } elseif ($Transport -ceq 'otlp-grpc') {
                        $Tls = @{ ca_certificate = 'string'; client_certificate = 'string'; client_private_key = 'string' }
                        Assert-CodexSettingShape $TransportConfig @{ endpoint = 'string'; headers = 'string map'; tls = $Tls }
                        $true
                    } else { $false }
                } else { $false }
            }
        }
        if (-not $Valid) { throw 'Unrecognized Codex telemetry setting' }
    }

    function Test-CodexHeadersHelper([object]$Config) {
        foreach ($Key in $Config.Keys) {
            if ($Key -match 'headers[_-]?helper' -and $null -ne (Get-CodexSetting $Config $Key)) { return $true }
        }
        return $false
    }

    function Get-CodexOtel([object]$Config) {
        foreach ($Key in $Config.Keys) {
            if ($Key -ieq 'otel' -and $Key -cne 'otel') { throw 'Unsupported Codex telemetry setting' }
        }
        $Otel = Get-CodexSetting $Config 'otel'
        Assert-CodexSettingShape $Otel @{
            exporter = 'exporter'; trace_exporter = 'exporter'; metrics_exporter = 'exporter'
            log_user_prompt = 'boolean'; log_agent_responses = 'boolean'; log_guardian_assessments = 'boolean'; log_sse_deltas = 'boolean'
            tool_result = @{ max_bytes = 'integer' }; environment = 'string'; span_attributes = 'string map'; tracestate = 'string'
        }
        return $Otel
    }

    function Assert-CodexAcl([string]$Path, [Security.Principal.SecurityIdentifier]$Owner, [bool]$Private) {
        $Acl = Get-Acl -LiteralPath $Path
        if ($Acl.GetOwner([Security.Principal.SecurityIdentifier]) -ne $Owner -or ($Private -and -not $Acl.AreAccessRulesProtected)) { throw 'Unsafe Codex ownership' }
        $OwnerAccess = $false
        foreach ($Rule in $Acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
            if ($Rule.IdentityReference -eq $Owner -and $Rule.AccessControlType -eq 'Allow' -and $Rule.FileSystemRights -eq 'FullControl') { $OwnerAccess = $true }
            elseif ($Private -or $Rule.IdentityReference.Value -notin @('S-1-5-18', 'S-1-5-32-544')) { throw 'Unsafe Codex permissions' }
        }
        if (-not $OwnerAccess) { throw 'Missing owner permissions' }
    }

    function Protect-CodexFile([string]$Path, [Security.Principal.SecurityIdentifier]$Owner) {
        $Acl = [Security.AccessControl.FileSecurity]::new()
        $Acl.SetOwner($Owner)
        $Acl.SetAccessRuleProtection($true, $false)
        $Acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($Owner, 'FullControl', 'Allow'))
        Set-Acl -LiteralPath $Path -AclObject $Acl
        Assert-CodexAcl $Path $Owner $true
    }

    function Assert-CodexAncestors([string]$HomePath, [Security.Principal.SecurityIdentifier]$Owner) {
        $Trusted = @($Owner.Value, 'S-1-5-18', 'S-1-5-32-544', 'S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464')
        $DangerousRights = [Security.AccessControl.FileSystemRights]'Delete, DeleteSubdirectoriesAndFiles, ChangePermissions, TakeOwnership, WriteAttributes, WriteData'
        $Ancestor = [IO.Path]::GetDirectoryName($HomePath)
        while ($Ancestor) {
            $Acl = Get-Acl -LiteralPath $Ancestor
            if ($Acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin $Trusted) { throw 'Unsafe Codex ancestor ownership' }
            foreach ($Rule in $Acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
                if ($Rule.IdentityReference.Value -notin $Trusted -and $Rule.AccessControlType -eq 'Allow' -and
                    -not ($Rule.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly) -and
                    ($Rule.FileSystemRights -band $DangerousRights)) { throw 'Unsafe Codex ancestor permissions' }
            }
            $Ancestor = [IO.Path]::GetDirectoryName($Ancestor)
        }
    }

    function Get-CodexTarget {
        foreach ($Name in [Environment]::GetEnvironmentVariables().Keys) {
            if ($Name -match '\A(?:OTEL_|CODEX_(?!HOME\z)|OPENAI_MANAGED_)') { throw 'Ambient Codex settings' }
        }
        $Location = Get-Location
        if ($Location.Provider.Name -ne 'FileSystem') { throw 'Expected a filesystem working directory' }
        $Cwd = $Location.ProviderPath
        Assert-NoLinks $Cwd
        $ProfileHome = [Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)
        if (-not $ProfileHome -or ($env:USERPROFILE -and -not (Test-SameCodexPath $env:USERPROFILE $ProfileHome)) -or
            ($env:HOME -and -not (Test-SameCodexPath $env:HOME $ProfileHome))) { throw 'Ambiguous Windows user profile' }
        $HomePath = if ($env:CODEX_HOME) { Get-CodexLocalPath $env:CODEX_HOME } else { Get-CodexLocalPath (Join-Path $ProfileHome '.codex') }
        if ($HomePath -cnotmatch '\A[A-Za-z]:\\[^:]+\z' -or $HomePath -match '[\x7f\p{Cf}]') { throw 'Unsupported Codex home' }
        $Drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($HomePath))
        if ($Drive.DriveType -ne 'Fixed' -or $Drive.DriveFormat -ne 'NTFS') { throw 'Codex home requires local NTFS' }
        Assert-NoLinks $HomePath
        $Owner = [Security.Principal.WindowsIdentity]::GetCurrent().User
        Assert-CodexAncestors $HomePath $Owner
        Assert-CodexAcl $HomePath $Owner $false
        $Path = Join-Path $HomePath 'config.toml'
        $Ancestor = $Cwd
        while ($Ancestor) {
            $ProjectPath = Join-Path $Ancestor '.codex\config.toml'
            if (-not (Test-SameCodexPath $ProjectPath $Path) -and (Test-Path -LiteralPath $ProjectPath)) { throw 'Project Codex configuration' }
            $Ancestor = [IO.Path]::GetDirectoryName($Ancestor)
        }
        return [pscustomobject]@{ HomePath = $HomePath; Path = $Path; Cwd = $Cwd; Owner = $Owner; Executable = (Resolve-CodexExecutable) }
    }

    function Get-CodexFileSnapshot([IO.FileStream]$Stream) {
        $Stamp = [UmbodTelemetrySettings]::FileStamp($Stream)
        if ($Stream.Length -gt 524288) { throw 'Codex configuration too large' }
        $Stream.Position = 0
        $Copy = [IO.MemoryStream]::new()
        try {
            $Stream.CopyTo($Copy)
            if ($Stamp -cne [UmbodTelemetrySettings]::FileStamp($Stream)) { throw 'Codex configuration changed' }
            return [pscustomobject]@{ Stamp = $Stamp; Bytes = $Copy.ToArray() }
        } finally { $Copy.Dispose() }
    }

    function Open-CodexConfiguration([pscustomobject]$Target, [IO.FileShare]$Share) {
        Assert-NoLinks $Target.Path
        if (-not (Test-Path -LiteralPath $Target.Path)) { return }
        Assert-CodexAcl $Target.Path $Target.Owner $false
        if (@(Get-Item -LiteralPath $Target.Path -Stream '*').Count -ne 1) { throw 'Unsupported Codex configuration streams' }
        return [IO.File]::Open($Target.Path, 'Open', 'Read', $Share)
    }

    function Read-CodexSnapshot([pscustomobject]$Target) {
        $Stream = Open-CodexConfiguration $Target 'Read'
        if ($null -eq $Stream) { return }
        try { return Get-CodexFileSnapshot $Stream } finally { $Stream.Dispose() }
    }

    function Assert-CodexSnapshot([object]$Expected, [object]$Current) {
        if ($null -eq $Expected -and $null -eq $Current) { return }
        if ($null -eq $Expected -or $null -eq $Current -or $Expected.Stamp -cne $Current.Stamp -or
            [Convert]::ToBase64String($Expected.Bytes) -cne [Convert]::ToBase64String($Current.Bytes)) { throw 'Codex configuration changed' }
    }

    function Get-CodexInspection([object]$Result, [string]$Path, [string]$LiveHome) {
        $Config = Get-CodexSetting $Result 'config'
        $Layers = Get-CodexSetting $Result 'layers'
        $Origins = Get-CodexSetting $Result 'origins'
        if ($null -eq $Config -or $null -eq $Config.Fields -or $null -eq $Layers -or $null -eq $Layers.Elements -or
            $null -eq $Origins -or $null -eq $Origins.Fields) { throw 'Missing Codex configuration' }
        $User = $null
        foreach ($Layer in $Layers.Elements) {
            $Name = $Layer.Fields['name'].Fields
            $LayerType = $Name['type'].Text
            $LayerConfig = $Layer.Fields['config'].Fields
            if ($null -eq $LayerConfig -or (Test-CodexHeadersHelper $LayerConfig)) { throw 'Unsafe Codex configuration layer' }
            if ($LayerType -ceq 'user') {
                if ($null -ne $User -or $null -ne (Get-CodexSetting $Name 'profile') -or
                    -not (Test-SameCodexPath (Get-CodexLocalPath $Name['file'].Text) $Path)) { throw 'Unexpected user configuration layer' }
                $User = $LayerConfig
            } elseif ($LayerType -ceq 'project' -and $Layer.Fields.ContainsKey('disabledReason') -and $Layer.Fields['disabledReason'].Text -and
                (Test-SameCodexPath (Get-CodexLocalPath $Name['dotCodexFolder'].Text) $LiveHome)) {
                continue
            } elseif ($LayerType -cne 'system' -or $LayerConfig.Count -ne 0) { throw 'Project or managed Codex configuration' }
        }
        if ($null -eq $User -or (Test-CodexHeadersHelper $Config.Fields) -or (Test-CodexHeadersHelper $Origins.Fields)) { throw 'Unsafe Codex settings' }
        foreach ($Key in $Origins.Fields.Keys) {
            if ($Key -imatch '\A(?:otel|analytics)(?:\.|\z)' -and $Origins.Fields[$Key].Fields['name'].Fields['type'].Text -cne 'user') { throw 'Overridden telemetry' }
        }
        foreach ($Key in $User.Keys) {
            if ($Key -imatch '\A(?:otel|analytics|profile|profiles)(?:\z|[_-])' -and $Key -cnotin @('otel', 'analytics')) { throw 'Unrecognized or profiled telemetry' }
        }
        $Otel = Get-CodexOtel $Config.Fields
        $UserOtel = Get-CodexOtel $User
        $Analytics = Get-CodexSetting $Config.Fields 'analytics'
        $UserAnalytics = Get-CodexSetting $User 'analytics'
        Assert-CodexSettingShape $Analytics @{ enabled = 'boolean' }
        Assert-CodexSettingShape $UserAnalytics @{ enabled = 'boolean' }
        if (($null -ne $Otel -and $null -eq $UserOtel) -or ($null -ne $Analytics -and $null -eq $UserAnalytics)) { throw 'Unknown telemetry origin' }
        return [pscustomobject]@{ User = $User; Effective = $Config.Fields; Otel = $Otel; Analytics = $Analytics }
    }

    function Write-StagedCodexTelemetry([object]$Connection, [hashtable]$ReadParams, [object]$Before, [string]$Path, [string]$LiveHome, [int]$Id, [string]$Endpoint, [string]$Authorization) {
        $Desired = @{
            exporter = @{ 'otlp-http' = @{ endpoint = $Endpoint; protocol = 'json'; headers = @{ Authorization = $Authorization } } }
            trace_exporter = 'none'; metrics_exporter = 'none'; log_user_prompt = $false; log_agent_responses = $false
            log_guardian_assessments = $false; log_sse_deltas = $false; tool_result = @{ max_bytes = 0 }
        }
        Send-CodexRequest $Connection.Writer @{ id = $Id; method = 'config/batchWrite'; params = @{ edits = @(
            @{ keyPath = 'otel'; mergeStrategy = 'replace'; value = $Desired }
            @{ keyPath = 'analytics.enabled'; mergeStrategy = 'replace'; value = $false }
        ) } }
        $Write = Read-CodexResponse $Connection.Reader $Connection.Timer $Id
        if ($Write['status'].Text -cne 'ok' -or -not (Test-SameCodexPath (Get-CodexLocalPath $Write['filePath'].Text) $Path)) { throw 'Unexpected staged write' }
        Send-CodexRequest $Connection.Writer @{ id = ($Id + 1); method = 'config/read'; params = $ReadParams }
        $After = Get-CodexInspection (Read-CodexResponse $Connection.Reader $Connection.Timer ($Id + 1)) $Path $LiveHome
        if (-not [UmbodTelemetrySettings]::EqualFields($Before.User, $After.User, 'otel', 'analytics') -or
            -not [UmbodTelemetrySettings]::EqualFields($Before.Effective, $After.Effective, 'otel', 'analytics')) { throw 'Unrelated Codex settings changed' }
        $Desired.exporter['otlp-http'].headers.Authorization = '[redacted]'
        $Expected = [UmbodTelemetrySettings]::Object(($Desired | ConvertTo-Json -Depth 8 -Compress))
        foreach ($Optional in @('environment', 'span_attributes', 'tracestate')) {
            if ($After.Otel.Fields.ContainsKey($Optional) -and $After.Otel.Fields[$Optional].Literal -ceq 'null') { $null = $After.Otel.Fields.Remove($Optional) }
        }
        $Http = $After.Otel.Fields['exporter'].Fields['otlp-http'].Fields
        if ($Http.ContainsKey('tls') -and $Http['tls'].Literal -ceq 'null') { $null = $Http.Remove('tls') }
        if (-not [UmbodTelemetrySettings]::EqualFields($Expected, $After.Otel.Fields) -or $After.Analytics.Fields['enabled'].Literal -cne 'false') { throw 'Unexpected staged telemetry settings' }
        $Text = [Text.UTF8Encoding]::new($false, $true).GetString([IO.File]::ReadAllBytes($Path))
        if ([regex]::Matches($Text, ('(?m)^Authorization[ \t]*=[ \t]*"' + [regex]::Escape($Authorization) + '"[ \t]*\r?$')).Count -ne 1) { throw 'Staged credential could not be verified' }
    }

    function Format-CodexDestination([string]$Endpoint) {
        $Address = $null
        if (-not [Uri]::TryCreate($Endpoint, [UriKind]::Absolute, [ref]$Address) -or $Address.Scheme -cnotin @('https', 'http')) { return 'Configured (hidden)' }
        $Origin = $Address.GetComponents([UriComponents]::SchemeAndServer, [UriFormat]::UriEscaped)
        if ($Origin.Length -gt 88 -or $Origin -cnotmatch '\Ahttps?://(?:[A-Za-z0-9.-]+|\[[A-Fa-f0-9:.]+\])(?::[0-9]+)?\z') { return 'Configured (hidden)' }
        return $Origin
    }

    function Format-CodexExporter([object]$Exporter) {
        if ($null -eq $Exporter) { return 'Default' }
        if ($Exporter.Text -ceq 'none') { return 'Disabled' }
        if ($Exporter.Text -ceq 'stdout') { return 'Standard output' }
        if ($Exporter.Text -ceq 'statsig') { return 'Statsig' }
        return 'Configured'
    }

    function Format-CodexToggle([object]$Value) {
        if ($null -eq $Value) { return 'Default' }
        if ($Value.Literal -ceq 'true') { return 'Enabled' }
        return 'Disabled'
    }

    function Show-CodexTelemetryComparison([pscustomobject]$Inspection, [string]$UmbodEndpoint) {
        $Otel = if ($null -ne $Inspection.Otel) { $Inspection.Otel.Fields }
        $Analytics = if ($null -ne $Inspection.Analytics) { $Inspection.Analytics.Fields }
        $Exporter = Get-CodexSetting $Otel 'exporter'
        $Destination = Format-CodexExporter $Exporter
        $Authentication = if ($null -eq $Exporter -or $Exporter.Text -ceq 'statsig') { 'Default' } else { 'None' }
        if ($null -ne $Exporter -and $null -ne $Exporter.Fields) {
            $Transport = @($Exporter.Fields.Values)[0].Fields
            $Destination = Format-CodexDestination $Transport['endpoint'].Text
            $Headers = Get-CodexSetting $Transport 'headers'
            if ($null -ne $Headers -and $Headers.Fields.Count -gt 0) { $Authentication = 'Configured (hidden)' }
        }
        $ToolResult = Get-CodexSetting $Otel 'tool_result'
        $MaxBytes = if ($null -ne $ToolResult) { Get-CodexSetting $ToolResult.Fields 'max_bytes' }
        $ToolLogging = if ($null -eq $MaxBytes) { 'Default' } elseif ($MaxBytes.Literal -ceq '0') { 'Disabled' } else { 'Enabled' }
        $Rows = [ordered]@{
            'Logs destination' = @($Destination, (Format-CodexDestination $UmbodEndpoint))
            'Authentication' = @($Authentication, 'Umbod bearer token (hidden)')
            'Traces' = @((Format-CodexExporter (Get-CodexSetting $Otel 'trace_exporter')), 'Disabled')
            'Metrics' = @((Format-CodexExporter (Get-CodexSetting $Otel 'metrics_exporter')), 'Disabled')
            'Prompt logging' = @((Format-CodexToggle (Get-CodexSetting $Otel 'log_user_prompt')), 'Disabled')
            'Response logging' = @((Format-CodexToggle (Get-CodexSetting $Otel 'log_agent_responses')), 'Disabled')
            'Guardian logging' = @((Format-CodexToggle (Get-CodexSetting $Otel 'log_guardian_assessments')), 'Disabled')
            'SSE delta logging' = @((Format-CodexToggle (Get-CodexSetting $Otel 'log_sse_deltas')), 'Disabled')
            'Tool-result logging' = @($ToolLogging, 'Disabled')
            'Codex analytics' = @((Format-CodexToggle (Get-CodexSetting $Analytics 'enabled')), 'Disabled')
        }
        $CurrentWidth = 32
        foreach ($Row in $Rows.Values) { $CurrentWidth = [Math]::Max($CurrentWidth, $Row[0].Length) }
        Write-Host ('  {0,-22} {1}  {2}' -f '', 'Current'.PadRight($CurrentWidth), 'With Umbod')
        foreach ($Label in $Rows.Keys) {
            Write-Host ('  {0,-22} {1}  {2}' -f $Label, $Rows[$Label][0].PadRight($CurrentWidth), $Rows[$Label][1])
        }
    }

    function Confirm-CodexTelemetry([pscustomobject]$Inspection, [string]$Path, [string]$Endpoint) {
        Write-Host "Codex user configuration: $Path"
        Write-Host "Umbod logs target: $Endpoint"
        Show-CodexTelemetryComparison $Inspection $Endpoint
        Write-Host 'Current destinations are shown without paths or credentials.'
        Write-Host 'Saving replaces the entire user telemetry section, including any custom headers, TLS settings, environment label, span attributes, and tracestate.'
        Write-Host 'The Umbod token expires after 30 days and is stored in plaintext in an owner-only TOML file.'
        Write-Host 'Keep this file and its protected backup out of cloud sync and shared backups.'
        Write-Host '  1) Save Umbod telemetry as my Codex default'
        Write-Host '  2) Finish without configuring Umbod telemetry or starting Codex'
        try { return (([string](Read-Host 'Choose [1-2] (default: 2)')).Trim() -ceq '1') } catch { return $false }
    }

    function Invoke-CodexStagedEdit([object]$Target, [object]$Snapshot, [string]$Stage, [string]$Endpoint, [scriptblock]$Redeem) {
        $Path = Join-Path $Stage 'config.toml'
        $Start = [Diagnostics.ProcessStartInfo]::new($Target.Executable, 'app-server --listen stdio://')
        $Start.WorkingDirectory = $Stage
        $Start.UseShellExecute = $false
        $Start.EnvironmentVariables['CODEX_HOME'] = $Stage
        $Start.RedirectStandardInput = $true
        $Start.RedirectStandardOutput = $true
        $Start.RedirectStandardError = $true
        $Start.StandardOutputEncoding = [Text.UTF8Encoding]::new($false, $true)
        $Process = [Diagnostics.Process]::new()
        $Process.StartInfo = $Start
        $Started = $false
        try {
            $Started = $Process.Start()
            if (-not $Started) { throw 'Could not start Codex configuration helper' }
            $null = $Process.StandardError.BaseStream.CopyToAsync([IO.Stream]::Null)
            $Connection = [pscustomobject]@{
                Writer = [IO.StreamWriter]::new($Process.StandardInput.BaseStream, [Text.UTF8Encoding]::new($false))
                Reader = $Process.StandardOutput
                Timer = [Diagnostics.Stopwatch]::StartNew()
            }
            Send-CodexRequest $Connection.Writer @{ id = 1; method = 'initialize'; params = @{ clientInfo = @{ name = 'umbod-installer'; version = '1' } } }
            $Initialized = Read-CodexResponse $Connection.Reader $Connection.Timer 1
            if ($Initialized['userAgent'].Text -cnotmatch '^umbod-installer/0\.169\.' -or
                -not (Test-SameCodexPath (Get-CodexLocalPath $Initialized['codexHome'].Text) $Stage)) { throw 'Unexpected Codex helper version or home' }
            Send-CodexRequest $Connection.Writer @{ method = 'initialized' }
            Send-CodexRequest $Connection.Writer @{ id = 2; method = 'configRequirements/read' }
            $Requirements = Read-CodexResponse $Connection.Reader $Connection.Timer 2
            if (-not $Requirements.ContainsKey('requirements') -or $Requirements['requirements'].Literal -cne 'null') { throw 'Managed Codex requirements' }
            if ($null -ne $Snapshot) {
                if (Test-Path -LiteralPath $Path) { throw 'Unexpected staged file' }
                [IO.File]::WriteAllBytes($Path, $Snapshot.Bytes)
            }
            $ReadParams = @{ includeLayers = $true; cwd = $Target.Cwd }
            Send-CodexRequest $Connection.Writer @{ id = 3; method = 'config/read'; params = $ReadParams }
            $Before = Get-CodexInspection (Read-CodexResponse $Connection.Reader $Connection.Timer 3) $Path $Target.HomePath
            Write-StagedCodexTelemetry $Connection $ReadParams $Before $Path $Target.HomePath 4 $Endpoint 'Bearer umbod-installer-placeholder'
            if ($null -ne $Redeem) {
                Assert-CodexTargetUnchanged $Target
                Assert-CodexSnapshot $Snapshot (Read-CodexSnapshot $Target)
                $Settings = & $Redeem
                $Connection.Timer.Restart()
                $Authorization = $Settings['OTEL_EXPORTER_OTLP_LOGS_HEADERS'].Substring('Authorization='.Length)
                Write-StagedCodexTelemetry $Connection $ReadParams $Before $Path $Target.HomePath 6 $Endpoint $Authorization
            }
            return $Before
        } finally {
            try {
                if ($Started -and -not $Process.HasExited) {
                    $Process.Kill()
                    if (-not $Process.WaitForExit(5000)) { throw 'Codex configuration helper did not stop' }
                }
            } finally { $Process.Dispose() }
        }
    }

    function Assert-CodexTargetUnchanged([pscustomobject]$Target) {
        $Current = Get-CodexTarget
        if (-not (Test-SameCodexPath $Target.Path $Current.Path) -or -not (Test-SameCodexPath $Target.Cwd $Current.Cwd) -or
            $Target.Owner -ne $Current.Owner -or -not (Test-SameCodexPath $Target.Executable $Current.Executable)) { throw 'Active Codex configuration changed' }
    }

    function Publish-CodexTelemetry([object]$Target, [object]$Snapshot, [string]$Stage) {
        $Path = Join-Path $Stage 'config.toml'
        Assert-NoLinks $Path
        Protect-CodexFile $Path $Target.Owner
        $StagedFile = [IO.File]::Open($Path, 'Open', 'ReadWrite', 'None')
        try {
            $null = [UmbodTelemetrySettings]::FileStamp($StagedFile)
            $StagedFile.Flush($true)
        } finally { $StagedFile.Dispose() }
        $Backup = $null
        $Lock = $null
        $Published = $false
        try {
            if ($null -ne $Snapshot) {
                $BackupStage = Join-Path $Stage 'original.toml'
                [IO.File]::WriteAllBytes($BackupStage, $Snapshot.Bytes)
                Protect-CodexFile $BackupStage $Target.Owner
                $BackupPath = Join-Path $Target.HomePath ('config.toml.umbod-before-' + [Guid]::NewGuid().ToString('N'))
                [UmbodTelemetrySettings]::Publish($BackupStage, $BackupPath, $false)
                $Backup = $BackupPath
                Assert-CodexAcl $Backup $Target.Owner $true
            }
            Assert-CodexTargetUnchanged $Target
            $Lock = Open-CodexConfiguration $Target ([IO.FileShare]::Read -bor [IO.FileShare]::Delete)
            $Actual = if ($null -ne $Lock) { Get-CodexFileSnapshot $Lock }
            Assert-CodexSnapshot $Snapshot $Actual
            if ($null -ne $Lock) {
                $Named = Open-CodexConfiguration $Target ([IO.FileShare]::Read -bor [IO.FileShare]::Delete)
                if ($null -eq $Named) { throw 'Codex configuration moved' }
                try {
                    if ([UmbodTelemetrySettings]::FileStamp($Lock) -cne [UmbodTelemetrySettings]::FileStamp($Named)) { throw 'Codex configuration replaced' }
                    [UmbodTelemetrySettings]::ReplaceLocked($Path, $Target.Path)
                } finally { $Named.Dispose() }
            } else {
                [UmbodTelemetrySettings]::Publish($Path, $Target.Path, $false)
            }
            $Published = $true
            if ($Backup) { Write-Host "Protected original: $Backup" }
            Assert-CodexAcl $Target.Path $Target.Owner $true
            if ($Backup) {
                Write-Host 'To undo: close Codex and move this protected original over config.toml if no later settings need keeping.'
            } else {
                Write-Host 'To undo: close Codex and remove the newly created config.toml if no later settings need keeping.'
            }
            Write-Host 'If you made later changes, keep them and restore only the previous otel and analytics.enabled settings.'
            Write-Host 'Revoke the Umbod token when you remove this configuration.'
        } finally {
            if ($null -ne $Lock) { $Lock.Dispose() }
            if (-not $Published -and $Backup) { [IO.File]::Delete($Backup) }
        }
    }

    function Set-CodexTelemetry([string]$Endpoint, [scriptblock]$Redeem) {
        if ([Console]::IsInputRedirected -or [Console]::IsOutputRedirected -or [Console]::IsErrorRedirected -or -not [Environment]::UserInteractive) {
            Write-Host 'Skipped Codex telemetry in a noninteractive session. No Umbod telemetry token was created.'
            return
        }
        $Stage = $null
        try {
            try {
                $Target = Get-CodexTarget
                $Snapshot = Read-CodexSnapshot $Target
                $Candidate = Join-Path $Target.HomePath ('.umbod-telemetry-' + [Guid]::NewGuid().ToString('N'))
                [UmbodTelemetrySettings]::CreatePrivateDirectory($Candidate, $Target.Owner.Value)
                $Stage = $Candidate
                Assert-CodexAcl $Stage $Target.Owner $true
                $DryRun = Join-Path $Stage 'preflight'
                [UmbodTelemetrySettings]::CreatePrivateDirectory($DryRun, $Target.Owner.Value)
                Assert-CodexAcl $DryRun $Target.Owner $true
                $Inspection = Invoke-CodexStagedEdit $Target $Snapshot $DryRun $Endpoint $null
                [IO.Directory]::Delete($DryRun, $true)
                if (-not (Confirm-CodexTelemetry $Inspection $Target.Path $Endpoint)) {
                    Write-Host 'Codex telemetry was not changed. No Umbod telemetry token was created.'
                    return
                }
                Assert-CodexTargetUnchanged $Target
                Assert-CodexSnapshot $Snapshot (Read-CodexSnapshot $Target)
            } catch {
                Write-Host 'Codex settings could not be verified safely. No Umbod telemetry token was created.'
                return
            }
            try {
                $null = Invoke-CodexStagedEdit $Target $Snapshot $Stage $Endpoint $Redeem
                Publish-CodexTelemetry $Target $Snapshot $Stage
                Write-Host 'Umbod logs-only telemetry saved as the Codex default. Delivery has not been verified.'
            } catch {
                throw 'Plugin registration verified, but saving Codex telemetry could not be verified. Check your configuration and revoke any unused Umbod token before retrying.'
            }
        } finally {
            if ($Stage -and [IO.Directory]::Exists($Stage)) { [IO.Directory]::Delete($Stage, $true) }
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

    function Get-CodexLocalPath([object]$Value) {
        if ($Value -isnot [string]) { throw 'Expected an absolute local Codex path' }
        $Path = $Value.Replace('/', '\').TrimEnd('\')
        if ($Path -cmatch '\A\\\\\?\\[A-Za-z]:\\') { $Path = $Path.Substring(4) }
        if ($Path -imatch '\A\\\\\?\\UNC\\') { $Path = '\\' + $Path.Substring(8) }
        if ($Path -cnotmatch '\A(?:[A-Za-z]:\\|\\\\[^\\?.][^\\]*\\[^\\]+\\)' -or $Path -match '[\x00-\x1f]|(?:\A|\\)\.{1,2}(?:\\|\z)') { throw 'Expected an absolute local Codex path' }
        $FullPath = [IO.Path]::GetFullPath($Path)
        if (-not [string]::Equals($Path, $FullPath, [StringComparison]::OrdinalIgnoreCase)) { throw 'Expected a canonical local Codex path' }
        return $FullPath
    }

    function Test-SameCodexPath([string]$Left, [string]$Right) {
        return [string]::Equals($Left, $Right, [StringComparison]::OrdinalIgnoreCase)
    }

    function Assert-CodexMarketplaceSource([pscustomobject]$Registration, [string]$RootPath) {
        $Property = $Registration.PSObject.Properties['marketplaceSource']
        if ($null -eq $Property) { return }
        $Source = $Property.Value
        if ($null -eq $Source -or -not [string]::Equals($Source.sourceType, 'local', [StringComparison]::Ordinal) -or
            -not (Test-SameCodexPath (Get-CodexLocalPath $Source.source) $RootPath)) { throw 'The Codex marketplace source is not the expected local directory' }
    }

    function Assert-CodexPluginSource([pscustomobject]$Plugin, [string]$RootPath) {
        if ($Plugin.enabled -isnot [bool] -or -not $Plugin.enabled -or -not [string]::Equals($Plugin.source.source, 'local', [StringComparison]::Ordinal) -or
            -not (Test-SameCodexPath (Get-CodexLocalPath $Plugin.source.path) (Get-CodexLocalPath (Join-Path $RootPath 'plugins/umbod')))) { throw 'The enabled Codex plugin source is not the expected local directory' }
        Assert-CodexMarketplaceSource $Plugin $RootPath
    }

    function Read-PreviousCodexFile([string]$Path, [int]$MaximumLength, [Security.Principal.SecurityIdentifier]$UserOwner) {
        Assert-NoLinks $Path
        $File = Get-Item -Force -LiteralPath $Path
        if ($File -isnot [IO.FileInfo] -or $File.LinkType -or ($File.Attributes -band [IO.FileAttributes]::Device) -or
            -not $UserOwner.Equals((Get-Acl -LiteralPath $Path).GetOwner([Security.Principal.SecurityIdentifier]))) { throw 'A previous Codex package metadata file is unsafe' }
        $Stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
        try {
            if ($Stream.Length -gt $MaximumLength) { throw 'A previous Codex package metadata file is oversized' }
            $Reader = [IO.BinaryReader]::new($Stream)
            try { return [Text.UTF8Encoding]::new($false, $true).GetString($Reader.ReadBytes([int]$Stream.Length)) } finally { $Reader.Dispose() }
        } finally { $Stream.Dispose() }
    }

    function Assert-PreviousCodexPackage([string]$RootPath, [string]$ParentPath, [string]$InstanceEndpoint, [string]$MarketplaceName, [Security.Principal.SecurityIdentifier]$UserOwner) {
        $PreviousDigest = [IO.Path]::GetFileName($RootPath)
        if ($PreviousDigest -cnotmatch '\A[0-9a-f]{64}\z' -or -not (Test-SameCodexPath ([IO.Path]::GetDirectoryName($RootPath)) $ParentPath)) { throw 'The previous Codex package is not under the Umbod installation directory' }
        Assert-NoLinks $RootPath
        if (-not [IO.Directory]::Exists($RootPath) -or -not $UserOwner.Equals((Get-DirectoryOwner $RootPath))) { throw 'The previous Codex package is not user-owned' }
        Initialize-TelemetrySupport
        $MarkerText = Read-PreviousCodexFile (Join-Path $RootPath '.umbod-install.json') 2048 $UserOwner
        $Fields = [UmbodTelemetrySettings]::Object($MarkerText)
        if ($Fields.Count -ne 5 -or -not $Fields.ContainsKey('schema') -or $Fields['schema'].Literal -cne '1') { throw 'The previous Codex installation marker has an unsupported schema' }
        $ExpectedFields = @{ endpoint = $InstanceEndpoint; harness = 'codex'; marketplace = $MarketplaceName; sha256 = $PreviousDigest }
        foreach ($Key in $ExpectedFields.Keys) {
            if (-not $Fields.ContainsKey($Key) -or -not [string]::Equals($Fields[$Key].Text, $ExpectedFields[$Key], [StringComparison]::Ordinal)) { throw 'The previous Codex installation marker does not match this Umbod instance' }
        }
        $CatalogText = Read-PreviousCodexFile (Join-Path $RootPath '.agents/plugins/marketplace.json') 65536 $UserOwner
        $null = [UmbodTelemetrySettings]::Object($CatalogText)
        $PreviousCatalog = ConvertFrom-Json $CatalogText
        if (-not [string]::Equals($PreviousCatalog.name, $MarketplaceName, [StringComparison]::Ordinal) -or
            $PreviousCatalog.plugins -isnot [array] -or $PreviousCatalog.plugins.Count -ne 1) { throw 'The previous Codex marketplace is not an Umbod-only catalog' }
        $PreviousPlugin = $PreviousCatalog.plugins[0]
        if (-not [string]::Equals($PreviousPlugin.name, 'umbod', [StringComparison]::Ordinal) -or
            @($PreviousPlugin.source.PSObject.Properties).Count -ne 2 -or
            -not [string]::Equals($PreviousPlugin.source.source, 'local', [StringComparison]::Ordinal) -or
            -not [string]::Equals($PreviousPlugin.source.path, './plugins/umbod', [StringComparison]::Ordinal)) { throw 'The previous Codex marketplace plugin source is unsafe' }
        Assert-NoLinks (Join-Path $RootPath 'plugins/umbod')
    }

    function Get-CodexMarketplace([string]$MarketplaceName) {
        $Response = ConvertFrom-Json (Invoke-Harness -Arguments @('plugin', 'marketplace', 'list', '--json'))
        if ($Response.marketplaces -isnot [array]) { throw 'Unsupported Codex marketplace list response' }
        $Registered = @($Response.marketplaces | Where-Object { $_.name -ieq $MarketplaceName })
        if ($Registered.Count -gt 1 -or ($Registered.Count -eq 1 -and $Registered[0].name -cne $MarketplaceName)) { throw 'Ambiguous Codex marketplace registration' }
        if ($Registered.Count -eq 1) { return $Registered[0] }
    }

    function Get-InstalledCodexPlugin([string]$MarketplaceName) {
        $Response = ConvertFrom-Json (Invoke-Harness -Arguments @('plugin', 'list', '--json', '--marketplace', $MarketplaceName))
        if ($Response.installed -isnot [array]) { throw 'Unsupported Codex plugin list response' }
        $Installed = @($Response.installed | Where-Object { $_.pluginId -ceq "umbod@$MarketplaceName" })
        if ($Installed.Count -gt 1) { throw 'Multiple Umbod plugin registrations exist; review your harness plugin settings manually' }
        if ($Installed.Count -eq 1) { return $Installed[0] }
    }

    function Get-VerifiedCodexPlugin([string]$MarketplaceName, [string]$RootPath) {
        $Registration = Get-CodexMarketplace $MarketplaceName
        if ($null -eq $Registration -or -not (Test-SameCodexPath (Get-CodexLocalPath $Registration.root) $RootPath)) { throw 'The Codex marketplace root could not be verified' }
        Assert-CodexMarketplaceSource $Registration $RootPath
        $Installed = Get-InstalledCodexPlugin $MarketplaceName
        if ($null -eq $Installed) { throw 'The intended Codex plugin registration could not be verified' }
        Assert-CodexPluginSource $Installed $RootPath
        return $Installed
    }

    function Restore-CodexRegistration([string]$MarketplaceName, [string]$PreviousRoot, [string]$NewRoot, [string]$PreviousVersion) {
        $Registration = Get-CodexMarketplace $MarketplaceName
        if ($null -ne $Registration) {
            $RegisteredRoot = Get-CodexLocalPath $Registration.root
            Assert-CodexMarketplaceSource $Registration $RegisteredRoot
            if (-not (Test-SameCodexPath $RegisteredRoot $NewRoot) -and -not (Test-SameCodexPath $RegisteredRoot $PreviousRoot)) { throw 'Refusing to change an unexpected Codex marketplace during recovery' }
            $Installed = Get-InstalledCodexPlugin $MarketplaceName
            if ($null -ne $Installed) {
                $PluginPath = Get-CodexLocalPath $Installed.source.path
                $PreviousPluginPath = Get-CodexLocalPath (Join-Path $PreviousRoot 'plugins/umbod')
                $NewPluginPath = Get-CodexLocalPath (Join-Path $NewRoot 'plugins/umbod')
                if ($Installed.source.source -cne 'local' -or (-not (Test-SameCodexPath $PluginPath $PreviousPluginPath) -and -not (Test-SameCodexPath $PluginPath $NewPluginPath))) { throw 'Refusing to change an unexpected Codex plugin during recovery' }
            }
            if (Test-SameCodexPath $RegisteredRoot $NewRoot) {
                $null = Invoke-Harness -Arguments @('plugin', 'marketplace', 'remove', $MarketplaceName)
                $Registration = $null
            }
        }
        if ($null -eq $Registration) { $null = Invoke-Harness -Arguments @('plugin', 'marketplace', 'add', $PreviousRoot) }
        $null = Invoke-Harness -Arguments @('plugin', 'add', "umbod@$MarketplaceName")
        if ((Get-VerifiedCodexPlugin $MarketplaceName $PreviousRoot).version -cne $PreviousVersion) { throw 'The previous Codex plugin version could not be verified' }
    }

    $Temporary = $null
    $Staging = $null
    $LockStream = $null
    $LockPath = $null
    $InstallClaim = $null
    try {
        if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Unsupported platform. Use install.sh on macOS or Linux.' }
        $Telemetry = $null
        $ClaimVariable = Get-Variable UmbodInstallClaim -ErrorAction SilentlyContinue
        $LegacyPayload = Get-Variable UmbodTelemetryPayload -Scope Script -ErrorAction SilentlyContinue
        if ($null -ne $ClaimVariable) {
            if ($null -ne $LegacyPayload) { throw 'The telemetry claim cannot be combined with the private installer hook' }
            $InstallClaim = $ClaimVariable.Value
            $ClaimVariable = $null
            if ($InstallClaim -isnot [string] -or $InstallClaim -cnotmatch '\A[A-Za-z0-9_-]{43}\z') { throw 'Invalid telemetry install claim' }
            if (-not $LogsEndpoint) { throw 'Telemetry setup is unavailable. Copy a fresh install command from Umbod.' }
        }
        if ($null -ne $LegacyPayload) {
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
        $PreviousRoot = $null
        $CodexMarketplace = $null
        if ($Cli -eq 'codex') {
            $Destination = Get-CodexLocalPath $Destination
            $Parent = Get-CodexLocalPath $Parent
            $CodexMarketplace = Get-CodexMarketplace $Marketplace
            $ExistingCodexPlugin = Get-InstalledCodexPlugin $Marketplace
            if ($null -eq $CodexMarketplace) {
                if ($null -ne $ExistingCodexPlugin) { throw 'The existing Codex plugin has no registered Umbod marketplace. Review it manually; nothing was replaced.' }
            } else {
                $RegisteredRoot = Get-CodexLocalPath $CodexMarketplace.root
                Assert-CodexMarketplaceSource $CodexMarketplace $RegisteredRoot
                if ($null -ne $ExistingCodexPlugin) { Assert-CodexPluginSource $ExistingCodexPlugin $RegisteredRoot }
                if (-not (Test-SameCodexPath $RegisteredRoot $Destination)) {
                    if ($null -eq $ExistingCodexPlugin) { throw 'The Codex marketplace exists at another path without an enabled Umbod plugin. Review it manually; nothing was replaced.' }
                    Assert-PreviousCodexPackage $RegisteredRoot $Parent $Endpoint $Marketplace $Owner
                    $null = Invoke-Harness -Arguments @('plugin', 'marketplace', 'remove', '--help')
                    $PreviousRoot = $RegisteredRoot
                }
            }
        }
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
        if ($Cli -eq 'codex') {
            if ($null -ne $PreviousRoot) {
                $PreviousVersion = (Get-VerifiedCodexPlugin $Marketplace $PreviousRoot).version
                if ($PreviousVersion -isnot [string] -or -not $PreviousVersion) { throw 'The previous Codex plugin version could not be verified' }
                Assert-PreviousCodexPackage $PreviousRoot $Parent $Endpoint $Marketplace $Owner
                try {
                    Write-Host (Invoke-Harness -Arguments @('plugin', 'marketplace', 'remove', $Marketplace))
                    Write-Host (Invoke-Harness -Arguments @('plugin', 'marketplace', 'add', $Destination))
                    Write-Host (Invoke-Harness -Arguments @('plugin', 'add', "umbod@$Marketplace"))
                    if ((Get-VerifiedCodexPlugin $Marketplace $Destination).version -cne $ManifestData.version) { throw 'The upgraded Codex plugin version could not be verified' }
                } catch {
                    try {
                        Assert-PreviousCodexPackage $PreviousRoot $Parent $Endpoint $Marketplace $Owner
                        Restore-CodexRegistration $Marketplace $PreviousRoot $Destination $PreviousVersion
                    } catch {
                        throw "Codex upgrade failed and the previous registration could not be restored. The previous package remains at $PreviousRoot. Review marketplace $Marketplace in Codex before manually re-registering that directory and adding its Umbod plugin. No telemetry claim was redeemed."
                    }
                    throw 'Codex upgrade failed. The previous marketplace and Umbod plugin registration are active and verified. No telemetry claim was redeemed.'
                }
            } else {
                if ($null -eq $CodexMarketplace) { Write-Host (Invoke-Harness -Arguments @('plugin', 'marketplace', 'add', $Destination)) }
                if ($null -ne $ExistingCodexPlugin) { Write-Host 'Umbod plugin already installed; verifying registration...' } else { Write-Host (Invoke-Harness -Arguments @('plugin', 'add', "umbod@$Marketplace")) }
                if ((Get-VerifiedCodexPlugin $Marketplace $Destination).version -cne $ManifestData.version) { throw 'The Codex plugin version does not match the verified Umbod package. Review your Codex plugin settings before retrying.' }
            }
        } else {
            $ExistingPlugins = @($InitialPlugins | Where-Object { $_.id -ceq "umbod@$Marketplace" })
            if ($ExistingPlugins.Count -gt 1) { throw 'Multiple Umbod plugin registrations exist; review your harness plugin settings manually' }
            if ($ExistingPlugins.Count -eq 1) {
                $ExistingSource = $ExistingPlugins[0].readFromFolder
                if (-not $ExistingSource -or [IO.Path]::GetFullPath($ExistingSource) -ne [IO.Path]::GetFullPath((Join-Path $Destination 'plugins/umbod')) -or $ExistingPlugins[0].scope -cne 'user') { throw 'The existing Umbod plugin uses another source or scope. Review your harness plugin settings manually; nothing was replaced.' }
            }
            $Matches = @($Marketplaces | Where-Object { $_.name -ceq $Marketplace })
            if ($Matches.Count -gt 0) {
                if ($Matches.Count -ne 1 -or [IO.Path]::GetFullPath($Matches[0].path) -ne [IO.Path]::GetFullPath($Destination)) { throw 'Marketplace already exists at another path. Review it manually; nothing was replaced.' }
            } else {
                Write-Host (Invoke-Harness -Arguments @('plugin', 'marketplace', 'add', $Destination))
            }
            if ($ExistingPlugins.Count -eq 1) { Write-Host 'Umbod plugin already installed; verifying registration...' } else { Write-Host (Invoke-Harness -Arguments @('plugin', 'install', "umbod@$Marketplace", '--scope', 'user')) }
            Write-Host "Verifying $Harness plugin registration..."
            $Installed = @(ConvertFrom-Json (Invoke-Harness -Arguments @('plugin', 'list', '--json')) | ForEach-Object { $_ })
            $Verified = @($Installed | Where-Object { $_.id -ceq "umbod@$Marketplace" -and $_.enabled -eq $true -and $_.scope -ceq 'user' })
            if ($Verified.Count -ne 1) { throw 'The intended Umbod plugin is not enabled; review your harness plugin settings' }
            $PluginSource = $Verified[0].readFromFolder
            if (-not $PluginSource -or [IO.Path]::GetFullPath($PluginSource) -ne [IO.Path]::GetFullPath((Join-Path $Destination 'plugins/umbod'))) { throw 'The installed Umbod plugin source could not be verified; review your harness plugin settings' }
        }
        if ($null -ne $InstallClaim) {
            Initialize-TelemetrySupport
            if ($Harness -eq 'codex') {
                $null = New-TelemetrySettings $LogsEndpoint ('umbod_pat_v1_' + ('0' * 32) + '_' + ('A' * 43))
                Set-CodexTelemetry $LogsEndpoint { Redeem-InstallClaim "$Base/$Harness/telemetry/redeem" $InstallClaim $LogsEndpoint }
            } else {
                $PreflightSettings = New-TelemetrySettings $LogsEndpoint ('umbod_pat_v1_' + ('0' * 32) + '_' + ('A' * 43))
                Update-ClaudeTelemetry $PreflightSettings $true { Redeem-InstallClaim "$Base/$Harness/telemetry/redeem" $InstallClaim $LogsEndpoint }
                Write-Host 'Claude Code logs-only telemetry settings applied. Delivery has not been verified.'
            }
            $InstallClaim = $null
        }
        if ($null -ne $Telemetry -and $Harness -eq 'claude-code') {
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
        if ($Harness -eq 'codex') {
            Write-Host '1. Open or restart Codex when you are ready.'
        } else {
            Write-Host '1. Restart Claude Code.'
        }
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
