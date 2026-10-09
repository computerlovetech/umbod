using System.Text.Json;
using System.Text.Json.Nodes;
namespace Umbod.Core;
public static class Json
{
    public static readonly JsonSerializerOptions Pretty = new() { WriteIndented = true };
    public static string Text(this JsonNode? node, string fallback = "") => node is JsonValue value && value.TryGetValue<string>(out var text) ? text : fallback;
    public static long Count(this JsonNode? node) => node is JsonValue value && value.TryGetValue<long>(out var count) ? count : 0;
}
public sealed class ConnectorDraft
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
    public string Transport { get; set; } = "stdio";
    public string Command { get; set; } = "";
    public string Arguments { get; set; } = "";
    public string Url { get; set; } = "";
    public bool OAuth
    {
        get; set;
    }
    public string HeaderReferences { get; set; } = "{}";
    public string EnvironmentReferences { get; set; } = "{}";
    public static ConnectorDraft From(JsonObject item) => new() { Id = item["id"].Text(), Name = item["name"].Text(), Transport = item["transport"].Text("stdio"), Command = item["command"].Text(), Arguments = string.Join("\n", (item["args"] as JsonArray ?? []).Select(x => x.Text())), Url = item["url"].Text(), OAuth = item["oauth"]?.GetValue<bool>() ?? false, HeaderReferences = item["headers"]?.ToJsonString() ?? "{}", EnvironmentReferences = item["env"]?.ToJsonString() ?? "{}" };
    public JsonObject Payload()
    {
        static JsonObject References(string input)
        {
            try
            {
                var values = JsonNode.Parse(input) as JsonObject ?? throw new ArgumentException();
                if (values.Any(x => x.Value is not JsonValue value || !value.TryGetValue<string>(out var reference) || !reference.StartsWith("upstream:") || reference.StartsWith("upstream:oauth:")))
                    throw new ArgumentException();
                return values;
            }
            catch (Exception e) when (e is JsonException or ArgumentException) { throw new ArgumentException("Credential references must map names to upstream: references, never secret values."); }
        }
        return new()
        {
            ["id"] = Id,
            ["name"] = Name,
            ["transport"] = Transport,
            ["command"] = Command,
            ["args"] = new JsonArray(Arguments.Replace("\r", "").Split('\n', StringSplitOptions.RemoveEmptyEntries).Select(x => (JsonNode?)JsonValue.Create(x)).ToArray()),
            ["url"] = Url,
            ["oauth"] = OAuth,
            ["headers"] = References(HeaderReferences),
            ["env"] = References(EnvironmentReferences)
        };
    }
}
public sealed record ToolRow(string Name, string Description, bool Allowed, string Schema)
{
    public override string ToString() => $"{(Allowed ? "✓" : "○")} {Name}";
}
public sealed record ConnectorRow(JsonObject Value, string Status, int Enabled, int Total)
{
    public string Id => Value["id"].Text(); public string Name => Value["name"].Text(); public override string ToString() => $"{Name} — {Status} · {Enabled}/{Total} enabled";
}
public sealed record UsageRow(string Tool, long Succeeded, long Failed)
{
    public long Total => Succeeded + Failed;
}
public sealed class GatewayState
{
    public List<ConnectorRow> Connectors { get; } = [];
    public List<ToolRow> Tools { get; } = [];
    public List<UsageRow> Usage { get; } = [];
    public SortedDictionary<long, long> DailyCalls { get; } = [];
    public long TotalCalls => Usage.Sum(x => x.Total);
    public bool DiagnosticsEnabled
    {
        get; private set;
    }
    public static GatewayState Parse(JsonObject state)
    {
        var result = new GatewayState();
        var allowed = (state["allowed_tools"] as JsonArray ?? []).Select(x => x.Text()).ToHashSet(StringComparer.Ordinal);
        foreach (var item in state["tools"] as JsonArray ?? [])
            if (item is JsonObject t)
                result.Tools.Add(new(t["name"].Text(), t["description"].Text("No description provided."), allowed.Contains(t["name"].Text()), t["inputSchema"]?.ToJsonString(Json.Pretty) ?? "{}"));
        foreach (var item in state["servers"] as JsonArray ?? [])
            if (item is JsonObject s)
            {
                var tools = result.Tools.Where(t => t.Name.StartsWith(s["id"].Text() + ".", StringComparison.Ordinal)).ToList();
                result.Connectors.Add(new((JsonObject)s.DeepClone(), state["statuses"]?[s["id"].Text()].Text("Disconnected") ?? "Disconnected", tools.Count(t => t.Allowed), tools.Count));
            }
        foreach (var pair in state["tool_usage"] as JsonObject ?? [])
            result.Usage.Add(new(pair.Key, pair.Value?["succeeded"].Count() ?? 0, pair.Value?["failed"].Count() ?? 0));
        foreach (var pair in state["daily_calls"] as JsonObject ?? [])
            if (long.TryParse(pair.Key, out var day))
                result.DailyCalls[day] = pair.Value.Count();
        result.DiagnosticsEnabled = state["diagnostics"]?["enabled"]?.GetValue<bool>() ?? false;
        return result;
    }
}
public sealed record AppProfile
{
    public string Name
    {
        get;
    }
    public string DataDirectory
    {
        get;
    }
    public string DisplayName => Name == "release" ? "Umbod" : "Umbod Dev";
    public string Executable => Path.Combine(DataDirectory, "bin", "umbod-gateway.exe");
    public AppProfile(string name, string? dataDirectory = null)
    {
        if (name is not ("release" or "dev"))
            throw new ArgumentException("Profile must be release or dev.");
        Name = name;
        DataDirectory = dataDirectory ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), DisplayName);
    }
    public string BridgeConfiguration() => new JsonObject { ["mcpServers"] = new JsonObject { [Name == "release" ? "umbod" : "umbod-dev"] = new JsonObject { ["command"] = Executable, ["args"] = new JsonArray("bridge", "--profile", Name) } } }.ToJsonString(Json.Pretty);
}
