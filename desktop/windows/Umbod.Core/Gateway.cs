using System.Diagnostics;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
namespace Umbod.Core;
public interface IManagement
{
    Task<JsonObject> RequestAsync(JsonObject body, CancellationToken cancellation = default);
}
public sealed class ManagementClient(HttpClient http, string address, string token) : IManagement
{
    public static Uri Loopback(string address)
    {
        if (!Uri.TryCreate("http://" + address, UriKind.Absolute, out var uri) || !address.StartsWith("127.0.0.1:", StringComparison.Ordinal) || uri.Host != "127.0.0.1" || uri.Port <= 0 || uri.AbsolutePath != "/" || uri.UserInfo.Length != 0 || uri.Query.Length != 0 || uri.Fragment.Length != 0)
            throw new InvalidDataException("Gateway address must be an IPv4 loopback host and port.");
        return new Uri(uri, "manage");
    }
    public async Task<JsonObject> RequestAsync(JsonObject body, CancellationToken cancellation = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, Loopback(address));
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        request.Content = new StringContent(body.ToJsonString(), Encoding.UTF8, "application/json");
        using var response = await http.SendAsync(request, cancellation);
        var text = await response.Content.ReadAsStringAsync(cancellation);
        JsonObject? value;
        try
        {
            value = JsonNode.Parse(text) as JsonObject;
        }
        catch (System.Text.Json.JsonException) { throw new IOException("Gateway returned an invalid response. Retry or restart in Settings."); }
        if (!response.IsSuccessStatusCode)
            throw new IOException(value?["error"].Text("Gateway request failed.") ?? "Gateway authentication failed. Restart the app to reconnect.");
        return value ?? throw new IOException("Gateway returned an empty response.");
    }
}
public sealed class Gateway(AppProfile profile, string bundledExecutable, Action<string> ensurePrivateDirectory) : IManagement, IDisposable
{
    private readonly HttpClient http = new(new HttpClientHandler { UseProxy = false, AllowAutoRedirect = false }) { Timeout = TimeSpan.FromSeconds(45) };
    private ManagementClient? client;
    private Process? owned;
    public bool Online => client != null;
    public bool UpdateAvailable
    {
        get; private set;
    }
    public string Address { get; private set; } = "";
    private string RuntimeFile => Path.Combine(profile.DataDirectory, "runtime.json");
    public Task<JsonObject> RequestAsync(JsonObject body, CancellationToken cancellation = default) => (client ?? throw new IOException("Gateway is offline. Start it in Settings.")).RequestAsync(body, cancellation);
    private async Task<bool> AttachAsync(CancellationToken cancellation)
    {
        if (!File.Exists(RuntimeFile))
            return false;
        try
        {
            if ((File.GetAttributes(RuntimeFile) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("Runtime record cannot be a symbolic link.");
            var record = JsonNode.Parse(await File.ReadAllTextAsync(RuntimeFile, cancellation)) as JsonObject ?? throw new IOException("Invalid gateway runtime record.");
            if (record["profile"].Text() != profile.Name)
                throw new IOException("Gateway profile mismatch.");
            ManagementClient.Loopback(record["gateway"].Text());
            var candidate = new ManagementClient(http, record["management"].Text(), record["admin_token"].Text());
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
            timeout.CancelAfter(TimeSpan.FromSeconds(2));
            var health = await candidate.RequestAsync(new()
            {
                ["action"] = "health"
            }, timeout.Token);
            if (health["profile"].Text() != profile.Name || health["pid"].Count() != record["pid"].Count())
                throw new IOException("Gateway identity mismatch.");
            client = candidate;
            Address = record["gateway"].Text();
            UpdateAvailable = File.Exists(profile.Executable) && !SHA256.HashData(await File.ReadAllBytesAsync(profile.Executable, cancellation)).SequenceEqual(SHA256.HashData(await File.ReadAllBytesAsync(bundledExecutable, cancellation)));
            return true;
        }
        catch (Exception e) when (e is IOException or System.Text.Json.JsonException or HttpRequestException or OperationCanceledException or InvalidOperationException) { cancellation.ThrowIfCancellationRequested(); client = null; Address = ""; return false; }
    }
    public async Task StartAsync(CancellationToken cancellation = default)
    {
        if (Online)
        {
            try
            {
                await RequestAsync(new()
                {
                    ["action"] = "health"
                }, cancellation);
                return;
            }
            catch (Exception e) when (e is HttpRequestException or IOException or OperationCanceledException) { cancellation.ThrowIfCancellationRequested(); Detach(); }
        }
        if (!File.Exists(bundledExecutable))
            throw new IOException("Bundled umbod-gateway.exe is missing. Extract the complete Umbod ZIP and try again.");
        ensurePrivateDirectory(profile.DataDirectory);
        if (await AttachAsync(cancellation))
            return;
        var bin = Path.GetDirectoryName(profile.Executable)!;
        ensurePrivateDirectory(bin);
        if (!await InstalledMatchesAsync(cancellation))
            await InstallAsync(bin, cancellation);
        await GatewayInstallation.WriteProfileAsync(profile, cancellation);
        await LaunchAsync(bin, cancellation);
    }
    private async Task<bool> InstalledMatchesAsync(CancellationToken cancellation) =>
        File.Exists(profile.Executable) && SHA256.HashData(await File.ReadAllBytesAsync(profile.Executable, cancellation)).SequenceEqual(SHA256.HashData(await File.ReadAllBytesAsync(bundledExecutable, cancellation)));
    private async Task InstallAsync(string bin, CancellationToken cancellation)
    {
        var staging = Path.Combine(bin, "gateway-" + Guid.NewGuid().ToString("N") + ".exe");
        try
        {
            await using (var source = File.OpenRead(bundledExecutable))
            await using (var target = new FileStream(staging, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                await source.CopyToAsync(target, cancellation);
            for (var attempt = 0; ; attempt++)
            {
                try
                {
                    File.Move(staging, profile.Executable, true);
                    break;
                }
                catch (IOException) when (attempt < 50) { await Task.Delay(100, cancellation); }
            }
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { throw new IOException("Cannot update the stable gateway executable. Close MCP clients (their stdio bridges can keep it locked), stop any gateway for this profile, then choose Start in Settings. If it still fails, check folder permissions.", e); }
        finally { if (File.Exists(staging)) File.Delete(staging); }
    }
    private async Task LaunchAsync(string bin, CancellationToken cancellation)
    {
        var start = new ProcessStartInfo(profile.Executable) { UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true, WorkingDirectory = bin };
        foreach (var arg in new[] { "serve", "--profile", profile.Name, "--data-dir", profile.DataDirectory, "--persistent" })
            start.ArgumentList.Add(arg);
        var token = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        var child = Process.Start(start) ?? throw new IOException("Gateway process could not start.");
        owned = child;
        // Drain and discard diagnostics: upstream errors may contain credential values.
        child.ErrorDataReceived += (_, _) => { };
        child.BeginErrorReadLine();
        try
        {
            await child.StandardInput.WriteLineAsync(new JsonObject { ["admin_token"] = token }.ToJsonString());
            await child.StandardInput.FlushAsync(cancellation);
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
            timeout.CancelAfter(TimeSpan.FromSeconds(20));
            var line = await child.StandardOutput.ReadLineAsync(timeout.Token) ?? throw new IOException("Gateway exited before startup. Check Credential Manager access and configuration.");
            var ready = GatewayStartup.Parse(line);
            ManagementClient.Loopback(ready["gateway"].Text());
            client = new(http, ready["management"].Text(), token);
            Address = ready["gateway"].Text();
            UpdateAvailable = false;
        }
        catch { if (!child.HasExited) child.Kill(true); child.Dispose(); owned = null; client = null; throw; }
    }
    public async Task StopAsync(CancellationToken cancellation = default)
    {
        if (client == null)
            return;
        await RequestAsync(new()
        {
            ["action"] = "shutdown"
        }, cancellation);
        for (var i = 0; i < 150; i++)
        {
            if (!File.Exists(RuntimeFile))
            {
                if (owned is not null)
                {
                    using var exitTimeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
                    exitTimeout.CancelAfter(TimeSpan.FromSeconds(10));
                    await owned.WaitForExitAsync(exitTimeout.Token);
                }
                Detach();
                return;
            }
            await Task.Delay(100, cancellation);
        }
        throw new IOException("Gateway is still shutting down. Wait before restarting.");
    }
    public async Task RestartAsync(CancellationToken cancellation = default)
    {
        // A running gateway itself locks the stable Windows image; bridges can keep it
        // locked after shutdown. Never turn a working gateway off to discover that.
        // Updates require an explicit Stop, closing MCP clients, then Start instead.
        if (!await InstalledMatchesAsync(cancellation))
            throw new IOException("Gateway update requires a manual stop. The existing gateway has not been stopped. Close MCP clients, choose Stop in Settings, then Start to install the update.");
        try
        {
            await StopAsync(cancellation);
        }
        catch (HttpRequestException) { Detach(); }
        await StartAsync(cancellation);
    }
    private void Detach()
    {
        client = null;
        Address = "";
        owned?.StandardInput.Dispose();
        owned?.Dispose();
        owned = null;
    }
    public void Dispose()
    {
        Detach();
        http.Dispose();
    }
}
public sealed class Workspace(IManagement management)
{
    public GatewayState State { get; private set; } = new();
    public async Task RefreshAsync(CancellationToken cancellation = default) => State = GatewayState.Parse(await management.RequestAsync(new() { ["action"] = "status" }, cancellation));
    public async Task ActAsync(JsonObject body, CancellationToken cancellation = default)
    {
        await management.RequestAsync(body, cancellation);
        await RefreshAsync(cancellation);
    }
    public async Task SaveAsync(ConnectorDraft draft, string credentialName, string credential, CancellationToken cancellation = default)
    {
        if (string.IsNullOrWhiteSpace(draft.Name))
            throw new ArgumentException("Give the connector a name.");
        if (draft.Id.Length == 0)
            draft.Id = Guid.NewGuid().ToString("N");
        var server = draft.Payload();
        if (credential.Length > 0)
        {
            if (string.IsNullOrWhiteSpace(credentialName))
                throw new ArgumentException("Enter a header or environment variable name.");
            var reference = $"upstream:{draft.Id}:{credentialName}";
            await management.RequestAsync(new()
            {
                ["action"] = "secret_set",
                ["reference"] = reference,
                ["value"] = credential
            }, cancellation);
            server[draft.Transport == "stdio" ? "env" : "headers"]!.AsObject()[credentialName] = reference;
        }
        await ActAsync(new()
        {
            ["action"] = "server_save",
            ["server"] = server
        }, cancellation);
    }
    public async Task<Uri> BeginOAuthAsync(string id, string clientId, CancellationToken cancellation = default)
    {
        var response = await management.RequestAsync(new()
        {
            ["action"] = "oauth_begin",
            ["id"] = id,
            ["client_id"] = clientId
        }, cancellation);
        if (!Uri.TryCreate(response["url"].Text(), UriKind.Absolute, out var url) || (url.Scheme != "https" && !(url.Scheme == "http" && url.IsLoopback)) || url.UserInfo.Length != 0)
            throw new IOException("Provider returned an unsafe browser URL.");
        return url;
    }
}
public static class GatewayStartup
{
    public static JsonObject Parse(string line)
    {
        JsonObject value;
        try
        {
            value = JsonNode.Parse(line) as JsonObject ?? throw new IOException("Invalid gateway startup response.");
        }
        catch (System.Text.Json.JsonException) { throw new IOException("Invalid gateway startup response."); }
        if (value["error"] is not null)
            throw new IOException(value["error"].Text("Gateway startup failed."));
        ManagementClient.Loopback(value["management"].Text());
        ManagementClient.Loopback(value["gateway"].Text());
        return value;
    }
}

public static class GatewayInstallation
{
    // Caller secures the containing directory before this nonsecret marker is created.
    public static async Task WriteProfileAsync(AppProfile profile, CancellationToken cancellation = default)
    {
        var marker = Path.Combine(Path.GetDirectoryName(profile.Executable)!, "umbod-profile");
        var staging = marker + "." + Guid.NewGuid().ToString("N");
        try
        {
            await using (var output = new FileStream(staging, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                await output.WriteAsync(Encoding.UTF8.GetBytes(profile.Name + "\n"), cancellation);
            File.Move(staging, marker, true);
        }
        finally { if (File.Exists(staging)) File.Delete(staging); }
    }
}
