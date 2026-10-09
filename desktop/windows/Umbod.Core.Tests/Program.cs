using System.Text.Json.Nodes;
using Umbod.Core;
static void Check(bool value, string message) { if (!value) throw new Exception(message); Console.WriteLine("PASS " + message); }
var startupError = false;
try { GatewayStartup.Parse("{\"error\":\"fixture bind denied\"}"); } catch (IOException e) { startupError = e.Message == "fixture bind denied"; }
Check(startupError, "startup errors surface actual backend failure before parsing addresses");
var markerDirectory = Path.Combine(Path.GetTempPath(), "umbod-marker-" + Guid.NewGuid().ToString("N"));
try
{
    Directory.CreateDirectory(Path.Combine(markerDirectory, "bin"));
    await GatewayInstallation.WriteProfileAsync(new AppProfile("release", markerDirectory));
    var marker = Path.Combine(markerDirectory, "bin", "umbod-profile");
    Check(File.Exists(marker) && File.ReadAllText(marker).Trim() == "release", "stable installed gateway retains explicit release profile marker");
}
finally { Directory.Delete(markerDirectory, true); }
// Identical installed bytes must not be replaced, even before process launch.
var installDirectory = Path.Combine(Path.GetTempPath(), "umbod-install-" + Guid.NewGuid().ToString("N"));
try
{
    var installProfile = new AppProfile("dev", installDirectory);
    Directory.CreateDirectory(Path.GetDirectoryName(installProfile.Executable)!);
    var bundle = Path.Combine(installDirectory, "bundle.exe");
    File.WriteAllText(bundle, "not an executable: installation-only fixture");
    File.Copy(bundle, installProfile.Executable);
    File.SetLastWriteTimeUtc(installProfile.Executable, new DateTime(2001, 1, 1, 0, 0, 0, DateTimeKind.Utc));
    var originalWrite = File.GetLastWriteTimeUtc(installProfile.Executable);
    using var gateway = new Gateway(installProfile, bundle, path => Directory.CreateDirectory(path));
    try { await gateway.StartAsync(); } catch (System.ComponentModel.Win32Exception) { }
    Check(File.GetLastWriteTimeUtc(installProfile.Executable) == originalWrite, "identical installed executable is never replaced");
}
finally { Directory.Delete(installDirectory, true); }
var draft = new ConnectorDraft { Id = "test", Name = "Test", Command = @"C:\tools\server.exe", Arguments = "first argument\nsecond", EnvironmentReferences = "{\"KEY\":\"upstream:test\"}" };
var payload = draft.Payload();
Check(payload["args"]!.AsArray().Count == 2 && payload["args"]![0]!.GetValue<string>() == "first argument", "arguments preserve spaces without shell quoting");
Check(payload["env"]!["KEY"]!.GetValue<string>() == "upstream:test" && payload["transport"]!.GetValue<string>() == "stdio", "connector payload exact Rust fields");
var invalid = false;
try { new ConnectorDraft { EnvironmentReferences = "{\"KEY\":42}" }.Payload(); } catch (ArgumentException) { invalid = true; }
Check(invalid, "reject non-string credential references");
var state = GatewayState.Parse(JsonNode.Parse("""{"servers":[{"id":"test","name":"Test","transport":"stdio"}],"tools":[{"name":"test.echo","description":"Echo text","inputSchema":{"type":"object"}}],"allowed_tools":["test.echo"],"statuses":{"test":"Connected"},"tool_usage":{"test.echo":{"succeeded":3,"failed":2}},"daily_calls":{"20000":4}}""")!.AsObject());
Check(state.TotalCalls == 5 && state.Tools.Single().Allowed && state.Tools.Single().Schema.Contains("object"), "status shared permissions schema and successful plus failed counts");
var config = JsonNode.Parse(new AppProfile("dev", "/tmp/isolated").BridgeConfiguration())!;
Check(config["mcpServers"]!["umbod-dev"]!["args"]![2]!.GetValue<string>() == "dev", "bridge explicitly selects isolated dev profile");
Check(config["mcpServers"]!["umbod-dev"]!["command"]!.GetValue<string>().EndsWith(Path.Combine("bin", "umbod-gateway.exe"), StringComparison.Ordinal), "bridge uses stable Windows executable");
Console.WriteLine("Core behavioral harness passed.");
var fake = new RecordingManagement();
var workspace = new Workspace(fake);
await workspace.SaveAsync(draft, "KEY", "fixture-secret");
Check(fake.Bodies[0]["action"].Text() == "secret_set" && fake.Bodies[1]["action"].Text() == "server_save" && fake.Bodies[1]["server"]!["env"]!["KEY"].Text() == "upstream:test:KEY", "credential stored before reference save through management API");
Check(!fake.Bodies[1].ToJsonString().Contains("fixture-secret"), "connector payload never contains secret value");
var oauth = await workspace.BeginOAuthAsync("test", "public-id");
Check(oauth.Scheme == "https" && fake.Bodies[^1]["action"].Text() == "oauth_begin" && fake.Bodies[^1]["client_id"].Text() == "public-id", "OAuth uses exact public client management fields");
foreach (var address in new[] { "example.org:12", "127.0.0.1.evil:12", "127.0.0.1:12@evil", "127.0.0.1", "127.0.0.1:12/other", "127.0.0.1:12?query" }) { var rejected = false; try { ManagementClient.Loopback(address); } catch (InvalidDataException) { rejected = true; } Check(rejected, "reject unsafe management address " + address); }
Check(ManagementClient.Loopback("127.0.0.1:23456").AbsolutePath == "/manage", "management endpoint fixed to loopback /manage");
using (var http = new HttpClient(new RecordingHttp()))
{
    var client = new ManagementClient(http, "127.0.0.1:1234", "test-capability");
    var result = await client.RequestAsync(new()
    {
        ["action"] = "status"
    });
    Check(result["ok"]?.GetValue<bool>() == true, "management sends bearer JSON POST and parses response");
}
var gatewayArg = Array.IndexOf(args, "--gateway");
if (gatewayArg >= 0)
{
    if (gatewayArg + 1 >= args.Length)
        throw new ArgumentException("--gateway requires an executable path");
    var directory = Path.Combine(Path.GetTempPath(), "umbod-windows-core-" + Guid.NewGuid().ToString("N"));
    Directory.CreateDirectory(directory);
    try
    {
        var start = new System.Diagnostics.ProcessStartInfo(Path.GetFullPath(args[gatewayArg + 1])) { UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true };
        foreach (var argument in new[] { "serve", "--profile", "dev", "--data-dir", directory })
            start.ArgumentList.Add(argument);
        using var process = System.Diagnostics.Process.Start(start) ?? throw new Exception("Fixture gateway failed to start");
        process.ErrorDataReceived += (_, _) => { };
        process.BeginErrorReadLine();
        try
        {
            await process.StandardInput.WriteLineAsync("{\"admin_token\":\"isolated-harness-capability\"}");
            await process.StandardInput.FlushAsync();
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(30));
            var ready = GatewayStartup.Parse(await process.StandardOutput.ReadLineAsync(timeout.Token) ?? throw new Exception("Gateway exited"));
            using var http = new HttpClient(new HttpClientHandler { UseProxy = false, AllowAutoRedirect = false });
            var api = new ManagementClient(http, ready["management"].Text(), "isolated-harness-capability");
            var fixture = new Workspace(api);
            await fixture.RefreshAsync(timeout.Token);
            Check(fixture.State.Connectors.Count == 0, "real Rust empty isolated workspace");
            await fixture.SaveAsync(new ConnectorDraft { Id = "fixture", Name = "Fixture", Transport = "http", Url = "http://127.0.0.1:1/mcp" }, "", "", timeout.Token);
            Check(fixture.State.Connectors.Single().Id == "fixture", "real Rust CRUD exact connector contract");
            await fixture.ActAsync(new()
            {
                ["action"] = "server_remove",
                ["id"] = "fixture"
            }, timeout.Token);
            Check(fixture.State.Connectors.Count == 0, "real Rust connector removal");
            process.StandardInput.Close();
            await process.WaitForExitAsync(timeout.Token);
            Check(process.ExitCode == 0, "owned isolated gateway stops on EOF");
        }
        finally { if (!process.HasExited) { process.Kill(true); await process.WaitForExitAsync(); } }
    }
    finally { Directory.Delete(directory, true); }
}

if (gatewayArg >= 0)
{
    var directory = Path.Combine(Path.GetTempPath(), "umbod-lifecycle-" + Guid.NewGuid().ToString("N"));
    var fixtureProfile = new AppProfile("dev", directory);
    var executable = Path.GetFullPath(args[gatewayArg + 1]);
    using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(90));
    // On Unix preinstall with executable permissions; production installation targets Windows.
    if (!OperatingSystem.IsWindows())
    {
        Directory.CreateDirectory(Path.GetDirectoryName(fixtureProfile.Executable)!);
        File.Copy(executable, fixtureProfile.Executable);
        File.SetUnixFileMode(fixtureProfile.Executable, File.GetUnixFileMode(executable));
    }
    using var first = new Gateway(fixtureProfile, executable, path => Directory.CreateDirectory(path));
    System.Diagnostics.Process? bridge = null;
    string? connectionId = null;
    try
    {
        await first.StartAsync(timeout.Token);
        var before = await first.RequestAsync(new()
        {
            ["action"] = "health"
        }, timeout.Token);
        using var second = new Gateway(fixtureProfile, executable, path => Directory.CreateDirectory(path));
        await second.StartAsync(timeout.Token);
        var attached = await second.RequestAsync(new()
        {
            ["action"] = "health"
        }, timeout.Token);
        Check(before["pid"].Count() == attached["pid"].Count(), "Lifecycle attaches without duplicate gateway");
        first.Dispose();
        await second.RequestAsync(new()
        {
            ["action"] = "health"
        }, timeout.Token);
        Check(second.Online, "Persistent gateway survives UI detach");
        var connection = await second.RequestAsync(new() { ["action"] = "connection_setup" }, timeout.Token);
        connectionId = connection["id"].Text();
        var bridgeStart = new System.Diagnostics.ProcessStartInfo(fixtureProfile.Executable)
        { UseShellExecute = false, RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true };
        foreach (var argument in new[] { "bridge", "--profile", "dev", "--data-dir", directory })
            bridgeStart.ArgumentList.Add(argument);
        bridge = System.Diagnostics.Process.Start(bridgeStart) ?? throw new Exception("Bridge failed to start");
        bridge.ErrorDataReceived += (_, _) => { };
        bridge.BeginErrorReadLine();
        await bridge.StandardInput.WriteLineAsync("""{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"lifecycle-fixture","version":"1"}}}""");
        await bridge.StandardInput.FlushAsync();
        var initialized = JsonNode.Parse(await bridge.StandardOutput.ReadLineAsync(timeout.Token) ?? throw new Exception("Bridge exited before initialize"));
        Check(initialized?["result"] is not null, "real stdio bridge initializes before restart");
        await bridge.StandardInput.WriteLineAsync("""{"jsonrpc":"2.0","method":"notifications/initialized"}""");
        await bridge.StandardInput.FlushAsync();
        var installedWrite = File.GetLastWriteTimeUtc(fixtureProfile.Executable);
        await second.RestartAsync(timeout.Token);
        Check(!bridge.HasExited && File.GetLastWriteTimeUtc(fixtureProfile.Executable) == installedWrite,
            "same-build restart leaves active bridge and installed image untouched");
        var restarted = await second.RequestAsync(new()
        {
            ["action"] = "health"
        }, timeout.Token);
        Check(restarted["pid"].Count() != before["pid"].Count(), "Restart replaces process using stable executable");
        var updateBundle = Path.Combine(directory, "updated.exe");
        File.Copy(executable, updateBundle);
        await using (var append = new FileStream(updateBundle, FileMode.Append))
            await append.WriteAsync(new byte[] { 0 }); // Valid unsigned PE with changed hash.
        using var updater = new Gateway(fixtureProfile, updateBundle, path => Directory.CreateDirectory(path));
        await updater.StartAsync(timeout.Token);
        Check(updater.UpdateAvailable, "changed bundle detected while attaching");
        var refused = false;
        try { await updater.RestartAsync(timeout.Token); }
        catch (IOException e) { refused = e.Message.Contains("MCP clients", StringComparison.Ordinal); }
        catch (System.ComponentModel.Win32Exception) { } // Regression: old code stopped then attempted replacement/launch.
        Check(refused, "changed-build restart refuses with actionable MCP client guidance");
        var afterRefusal = await updater.RequestAsync(new() { ["action"] = "health" }, timeout.Token);
        Check(afterRefusal["pid"].Count() == restarted["pid"].Count() && !bridge.HasExited,
            "update refusal preserves healthy gateway PID and live bridge");
        await updater.RequestAsync(new() { ["action"] = "client_remove", ["id"] = connectionId }, timeout.Token);
        connectionId = null;
        await updater.StopAsync(timeout.Token);
        if (OperatingSystem.IsWindows())
        {
            var locked = false;
            try { await updater.StartAsync(timeout.Token); }
            catch (IOException e) { locked = e.Message.Contains("MCP clients", StringComparison.Ordinal); }
            Check(locked && !bridge.HasExited, "Windows changed image stays locked until MCP bridge exits");
        }
        bridge.StandardInput.Close();
        await bridge.WaitForExitAsync(timeout.Token);
        if (OperatingSystem.IsWindows())
        {
            await updater.StartAsync(timeout.Token);
            Check(!updater.UpdateAvailable, "Windows changed update starts after gateway and bridges stop");
            Check(File.ReadAllBytes(fixtureProfile.Executable).SequenceEqual(File.ReadAllBytes(updateBundle)), "Windows installs exact updated bytes");
            await updater.StopAsync(timeout.Token);
        }
        Check(!File.Exists(Path.Combine(directory, "runtime.json")), "Authenticated stop removes runtime");
    }
    finally
    {
        if (bridge is not null)
        {
            if (!bridge.HasExited) { bridge.Kill(true); await bridge.WaitForExitAsync(); }
            bridge.Dispose();
        }
        // Clean only this UUID-scoped test gateway, even after a failed assertion.
        using var cleanup = new Gateway(fixtureProfile, executable, path => Directory.CreateDirectory(path));
        using var cleanupTimeout = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        if (connectionId is not null && !File.Exists(Path.Combine(directory, "runtime.json")))
        {
            // A failing restart may already have stopped/replaced the gateway. Restore
            // the fixture executable so its temporary vault entry can still be removed.
            File.Copy(executable, fixtureProfile.Executable, true);
            if (!OperatingSystem.IsWindows())
                File.SetUnixFileMode(fixtureProfile.Executable, File.GetUnixFileMode(executable));
        }
        if (connectionId is not null || File.Exists(Path.Combine(directory, "runtime.json")))
        {
            await cleanup.StartAsync(cleanupTimeout.Token);
            if (connectionId is not null)
                await cleanup.RequestAsync(new() { ["action"] = "client_remove", ["id"] = connectionId }, cleanupTimeout.Token);
            await cleanup.StopAsync(cleanupTimeout.Token);
        }
        // Windows image teardown or a transient scanner can delay deletion after
        // process exit. Keep cleanup mandatory, with a bounded retry. Do not
        // change permissions, terminate unrelated processes, or swallow failure.
        for (var attempt = 0; Directory.Exists(directory); attempt++)
        {
            try { Directory.Delete(directory, true); }
            catch (Exception e) when (OperatingSystem.IsWindows() && attempt < 50 &&
                e is IOException or UnauthorizedAccessException)
            {
                if (attempt == 0)
                    Console.WriteLine($"Waiting for Windows fixture cleanup: {e.Message}");
                await Task.Delay(100, cleanupTimeout.Token);
            }
        }
        Check(!Directory.Exists(directory), "lifecycle fixture directory and executable removed");
    }
}
Console.WriteLine("All Core behavioral and requested integration checks passed.");
sealed class RecordingManagement : IManagement
{
    public List<JsonObject> Bodies { get; } = [];
    public Task<JsonObject> RequestAsync(JsonObject body, CancellationToken cancellation = default)
    {
        Bodies.Add((JsonObject)body.DeepClone());
        return Task.FromResult(body["action"].Text() == "oauth_begin" ? new JsonObject { ["url"] = "https://provider.example/authorize" } : new JsonObject());
    }
}
sealed class RecordingHttp : HttpMessageHandler
{
    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellation)
    {
        if (request.Method != HttpMethod.Post || request.RequestUri?.AbsoluteUri != "http://127.0.0.1:1234/manage" || request.Headers.Authorization?.ToString() != "Bearer test-capability" || !((await request.Content!.ReadAsStringAsync(cancellation)).Contains("status")))
            throw new Exception("Management wire contract mismatch");
        return new(System.Net.HttpStatusCode.OK)
        {
            Content = new StringContent("{\"ok\":true}")
        };
    }
}
