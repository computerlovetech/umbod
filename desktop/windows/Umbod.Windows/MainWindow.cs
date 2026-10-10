using System.Diagnostics;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;
using Umbod.Core;
namespace Umbod.Windows;
public sealed class MainWindow : Window
{
    public TabControl Tabs { get; } = new();
    private readonly AppProfile profile;
    private readonly Gateway gateway;
    private readonly Workspace workspace;
    private readonly TextBlock message = new() { Margin = new Thickness(20, 8, 20, 8), Foreground = Brushes.DarkRed };
    private readonly TextBlock lifecycle = new();
    private readonly TextBlock diagnosticsState = new();
    private readonly StackPanel overview = new();
    private readonly ListBox connectors = new() { MinHeight = 120, MaxHeight = 180 };
    private readonly ListBox tools = new() { MinHeight = 180, MaxHeight = 330 };
    private readonly TextBox query = new();
    private readonly TextBox details = new() { IsReadOnly = true, AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, MinHeight = 220, MaxHeight = 360 };
    private readonly CheckBox allowed = new() { Content = "Available to every connected app", Margin = new Thickness(0, 12, 0, 12) };
    private readonly TextBox clientId = new();
    private readonly TextBox reference = new() { Text = "upstream:" };
    private readonly PasswordBox secret = new() { Padding = new Thickness(8), Margin = new Thickness(0, 4, 0, 12) };
    private readonly DispatcherTimer timer = new() { Interval = TimeSpan.FromSeconds(5) };
    private readonly CancellationTokenSource lifetime = new();
    private bool busy, rendering;
    public MainWindow(AppProfile profile, bool smoke = false)
    {
        this.profile = profile;
        gateway = new(profile, Path.Combine(AppContext.BaseDirectory, "umbod-gateway.exe"), PrivateDirectory.Ensure);
        workspace = new(gateway);
        Title = profile.DisplayName;
        Width = 1120;
        Height = 850;
        MinWidth = 850;
        MinHeight = 650;
        FontFamily = new FontFamily("Segoe UI");
        FontSize = 14;
        Background = Brushes.White;
        var root = new DockPanel();
        var heading = new TextBlock { Text = profile.DisplayName + "  ·  Your tools, shared permissions", FontSize = 25, Margin = new Thickness(20) };
        DockPanel.SetDock(heading, Dock.Top);
        root.Children.Add(heading);
        var refresh = Button("Refresh status", () => workspace.RefreshAsync(lifetime.Token));
        DockPanel.SetDock(refresh, Dock.Top);
        root.Children.Add(refresh);
        DockPanel.SetDock(message, Dock.Bottom);
        root.Children.Add(message);
        root.Children.Add(Tabs);
        Content = root;
        AddTab("Overview", overview);
        BuildConnectors();
        BuildSettings();
        connectors.SelectionChanged += (_, _) => RenderTools();
        query.TextChanged += (_, _) => RenderTools();
        tools.SelectionChanged += (_, _) => RenderTool();
        allowed.Click += async (_, _) => { if (!rendering && tools.SelectedItem is ToolRow tool) await Run(() => workspace.ActAsync(new() { ["action"] = "grant", ["tool"] = tool.Name, ["allow"] = allowed.IsChecked == true }, lifetime.Token)); };
        timer.Tick += async (_, _) => { if (!busy && gateway.Online) await Run(() => workspace.RefreshAsync(lifetime.Token)); };
        Loaded += async (_, _) => { if (!smoke) { await Run(async () => { await gateway.StartAsync(lifetime.Token); await workspace.RefreshAsync(lifetime.Token); }); timer.Start(); } };
        Closed += (_, _) => { timer.Stop(); lifetime.Cancel(); gateway.Dispose(); lifetime.Dispose(); };
    }
    private void AddTab(string title, StackPanel panel) => Tabs.Items.Add(new TabItem { Header = title, Content = new ScrollViewer { Content = panel, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, Padding = new Thickness(24) } });
    private static TextBlock Text(string value, int size = 14) => new() { Text = value, FontSize = size, Margin = new Thickness(0, 4, 0, 12) };
    private Button Button(string label, Func<Task> action)
    {
        var button = new Button { Content = label };
        button.Click += async (_, _) => await Run(action);
        return button;
    }
    private async Task Run(Func<Task> action)
    {
        if (busy)
            return;
        busy = true;
        Tabs.IsEnabled = false;
        message.Foreground = Brushes.DarkSlateGray;
        message.Text = "Working…";
        try
        {
            await action();
            message.Text = "";
            Render();
        }
        catch (OperationCanceledException) { if (!lifetime.IsCancellationRequested) { message.Foreground = Brushes.DarkRed; message.Text = "Action timed out. Check the gateway and retry."; } }
        catch (Exception e) { message.Foreground = Brushes.DarkRed; message.Text = e.Message; }
        finally { RenderTool(); busy = false; Tabs.IsEnabled = true; lifecycle.Text = $"{(gateway.Online ? "Running" : "Offline")} · {gateway.Address}" + (gateway.UpdateAvailable ? " · Backend update ready: close MCP clients, Stop, then Start / attach." : ""); }
    }
    private void BuildConnectors()
    {
        var panel = new StackPanel();
        AddTab("Connectors", panel);
        panel.Children.Add(Text("Choose a connector to manage discovery and shared permissions.", 20));
        var actions = new WrapPanel();
        actions.Children.Add(Button("Add connector", () => Edit(null)));
        actions.Children.Add(Button("Edit", () => Edit(Selected())));
        actions.Children.Add(Button("Connect / rediscover", () => ActSelected("connect")));
        actions.Children.Add(Button("Remove", async () => { var selected = Selected(); if (MessageBox.Show(this, "Remove this connector and its tool permissions? Reusable vault references remain.", "Remove connector", MessageBoxButton.YesNo, MessageBoxImage.Warning) == MessageBoxResult.Yes) await workspace.ActAsync(new() { ["action"] = "server_remove", ["id"] = selected.Id }, lifetime.Token); }));
        panel.Children.Add(actions);
        panel.Children.Add(connectors);
        panel.Children.Add(Text("Browser sign-in (remote HTTP connectors)", 18));
        panel.Children.Add(Text("Optional public native client ID. Finish sign-in in your browser, then connect. Loopback callback expires after three minutes."));
        panel.Children.Add(clientId);
        var oauth = new WrapPanel();
        oauth.Children.Add(Button("Sign in with browser", async () => { var selected = Selected(); if (selected.Value["transport"].Text() != "http") throw new ArgumentException("Browser sign-in requires a remote HTTP connector."); var url = await workspace.BeginOAuthAsync(selected.Id, clientId.Text, lifetime.Token); Process.Start(new ProcessStartInfo(url.AbsoluteUri) { UseShellExecute = true }); MessageBox.Show(this, "Finish sign-in in your browser, then Connect / rediscover. The callback expires after three minutes.", "Browser sign-in"); }));
        oauth.Children.Add(Button("Refresh token", () => ActSelected("oauth_refresh")));
        oauth.Children.Add(Button("Sign out", () => ActSelected("oauth_logout")));
        panel.Children.Add(oauth);
        panel.Children.Add(Text("Tools & permissions", 20));
        panel.Children.Add(Text("Search name or description. New tools are off by default; permissions apply to all connected apps."));
        panel.Children.Add(query);
        var grid = new Grid();
        grid.ColumnDefinitions.Add(new()
        {
            Width = new GridLength(1, GridUnitType.Star)
        });
        grid.ColumnDefinitions.Add(new()
        {
            Width = new GridLength(1, GridUnitType.Star)
        });
        grid.Children.Add(tools);
        var inspector = new StackPanel { Margin = new Thickness(20, 0, 0, 0) };
        inspector.Children.Add(allowed);
        inspector.Children.Add(details);
        Grid.SetColumn(inspector, 1);
        grid.Children.Add(inspector);
        panel.Children.Add(grid);
    }
    private ConnectorRow Selected() => connectors.SelectedItem as ConnectorRow ?? throw new ArgumentException("Select a connector first.");
    private Task ActSelected(string action) => workspace.ActAsync(new() { ["action"] = action, ["id"] = Selected().Id }, lifetime.Token);
    private async Task Edit(ConnectorRow? connector)
    {
        var dialog = new ConnectorEditor(connector is null ? new() : ConnectorDraft.From(connector.Value)) { Owner = this };
        try
        {
            if (dialog.ShowDialog() == true)
                await workspace.SaveAsync(dialog.Draft, dialog.CredentialName, dialog.Credential, lifetime.Token);
        }
        finally { dialog.ClearSecret(); }
    }
    private void BuildSettings()
    {
        var panel = new StackPanel();
        AddTab("Settings", panel);
        panel.Children.Add(Text("Gateway", 22));
        panel.Children.Add(lifecycle);
        var buttons = new WrapPanel();
        buttons.Children.Add(Button("Start / attach", async () => { await gateway.StartAsync(lifetime.Token); await workspace.RefreshAsync(lifetime.Token); }));
        buttons.Children.Add(Button("Stop", () => gateway.StopAsync(lifetime.Token)));
        buttons.Children.Add(Button("Restart", async () => { await gateway.RestartAsync(lifetime.Token); await workspace.RefreshAsync(lifetime.Token); }));
        panel.Children.Add(buttons);
        panel.Children.Add(Text("Closing this window detaches; the gateway and connectors keep running. Stop and restart are authenticated actions. Restart may interrupt active calls."));
        panel.Children.Add(Text("MCP configuration", 22));
        panel.Children.Add(Text(profile.Name == "dev" ? "Development is isolated. Use umbod-dev only in a dedicated test session." : "Merge the Umbod entry into your client's mcpServers configuration."));
        panel.Children.Add(new TextBox { Text = profile.BridgeConfiguration(), IsReadOnly = true, AcceptsReturn = true, FontFamily = new FontFamily("Consolas"), TextWrapping = TextWrapping.Wrap });
        panel.Children.Add(Button("Copy configuration", async () => { await gateway.RequestAsync(new() { ["action"] = "connection_setup" }, lifetime.Token); Clipboard.SetText(profile.BridgeConfiguration()); }));
        panel.Children.Add(Button("Copy direct HTTP connection token", async () => { await gateway.RequestAsync(new() { ["action"] = "connection_setup" }, lifetime.Token); var result = await gateway.RequestAsync(new() { ["action"] = "connection_token" }, lifetime.Token); Clipboard.SetText(result["token"].Text()); MessageBox.Show(this, "Connection token copied. Treat your clipboard as sensitive.", "Umbod"); }));
        panel.Children.Add(Text("Client files are never edited by these buttons. Claude Desktop: %APPDATA%\\Claude\\claude_desktop_config.json. Direct HTTP endpoint: http://<gateway address>/mcp."));
        panel.Children.Add(Text("Credential Manager", 22));
        panel.Children.Add(Text("Secret values are stored by the Rust gateway in Windows Credential Manager only. Reference names are public identifiers; values never go in connector JSON."));
        panel.Children.Add(reference);
        panel.Children.Add(secret);
        var vault = new WrapPanel();
        vault.Children.Add(Button("Store credential", async () => { var value = secret.Password; secret.Clear(); await gateway.RequestAsync(new() { ["action"] = "secret_set", ["reference"] = reference.Text, ["value"] = value }, lifetime.Token); }));
        vault.Children.Add(Button("Delete credential", async () => { await gateway.RequestAsync(new() { ["action"] = "secret_delete", ["reference"] = reference.Text }, lifetime.Token); }));
        panel.Children.Add(vault);
        panel.Children.Add(diagnosticsState);
        panel.Children.Add(Button("Toggle local diagnostics", () => workspace.ActAsync(new() { ["action"] = "diagnostics_set", ["enabled"] = !workspace.State.DiagnosticsEnabled }, lifetime.Token)));
        panel.Children.Add(Text("Diagnostics are off by default and stay on this machine. Turning them off erases recorded counts and timing. No prompts, tool arguments, results or credentials are included."));
        panel.Children.Add(Text($"Umbod {typeof(MainWindow).Assembly.GetName().Version?.ToString(3)} · Native WPF interface · Shared Rust gateway. OAuth provider compatibility is not certified. Batch wrappers are unsupported: select the real .exe and put arguments on separate lines."));
    }
    private void Render()
    {
        diagnosticsState.Text = "Local diagnostics: " + (workspace.State.DiagnosticsEnabled ? "enabled" : "disabled");
        var selected = (connectors.SelectedItem as ConnectorRow)?.Id;
        connectors.ItemsSource = workspace.State.Connectors;
        connectors.SelectedItem = workspace.State.Connectors.FirstOrDefault(x => x.Id == selected) ?? workspace.State.Connectors.FirstOrDefault();
        RenderTools();
        overview.Children.Clear();
        overview.Children.Add(Text("Your tool activity", 26));
        overview.Children.Add(Text($"{workspace.State.TotalCalls:N0} total calls", 36));
        overview.Children.Add(Text($"{workspace.State.Connectors.Count} connectors · {workspace.State.Tools.Count(x => x.Allowed)} enabled tools · {workspace.State.Tools.Count} discovered tools"));
        overview.Children.Add(Text("Most-used connectors", 20));
        var connectorUsage = workspace.State.Usage.GroupBy(x => x.Tool.Split('.')[0]).Select(group => new { Connector = workspace.State.Connectors.FirstOrDefault(x => x.Id == group.Key)?.Name ?? "Removed connector (" + group.Key + ")", Calls = group.Sum(x => x.Total) }).OrderByDescending(x => x.Calls).ToList();
        overview.Children.Add(new DataGrid { ItemsSource = connectorUsage, IsReadOnly = true, AutoGenerateColumns = true, CanUserAddRows = false, MinHeight = 80 });
        overview.Children.Add(Text("Most-used tools", 20));
        var usage = new DataGrid { ItemsSource = workspace.State.Usage.OrderByDescending(x => x.Total).ToList(), IsReadOnly = true, AutoGenerateColumns = true, CanUserAddRows = false, MinHeight = 100 };
        overview.Children.Add(usage);
        overview.Children.Add(Text("Daily calls · UTC", 20));
        foreach (var pair in workspace.State.DailyCalls)
            overview.Children.Add(Text($"{DateTimeOffset.FromUnixTimeSeconds(pair.Key * 86400):yyyy-MM-dd}   {pair.Value:N0}"));
        overview.Children.Add(Text("Counts include successful and failed dispatched calls. Earlier totals may predate daily tracking. No arguments or results are stored. Refreshes every five seconds."));
    }
    private void RenderTools()
    {
        var selected = (tools.SelectedItem as ToolRow)?.Name;
        var id = (connectors.SelectedItem as ConnectorRow)?.Id;
        var rows = workspace.State.Tools.Where(x => id is not null && x.Name.StartsWith(id + ".", StringComparison.Ordinal) && (x.Name.Contains(query.Text, StringComparison.OrdinalIgnoreCase) || x.Description.Contains(query.Text, StringComparison.OrdinalIgnoreCase))).OrderBy(x => x.Name).ToList();
        tools.ItemsSource = rows;
        tools.SelectedItem = rows.FirstOrDefault(x => x.Name == selected) ?? rows.FirstOrDefault();
        RenderTool();
    }
    private void RenderTool()
    {
        rendering = true;
        var tool = tools.SelectedItem as ToolRow;
        allowed.IsEnabled = tool is not null;
        allowed.IsChecked = tool?.Allowed ?? false;
        details.Text = tool is null ? "No tools discovered. Connect / rediscover to load tools." : tool.Name + "\n\n" + tool.Description + "\n\nInput schema\n" + tool.Schema;
        rendering = false;
    }
}
