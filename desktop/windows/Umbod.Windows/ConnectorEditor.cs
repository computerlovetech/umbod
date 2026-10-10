using System.Windows;
using System.Windows.Controls;
using Umbod.Core;
namespace Umbod.Windows;
public sealed class ConnectorEditor : Window
{
    public ConnectorDraft Draft
    {
        get;
    }
    private readonly TextBox name = new(), command = new(), arguments = new() { AcceptsReturn = true, Height = 75 }, url = new(), headers = new(), environment = new(), credentialName = new();
    private readonly ComboBox transport = new() { ItemsSource = new[] { "stdio", "http" }, Margin = new Thickness(0, 0, 0, 12) };
    private readonly PasswordBox credential = new() { Padding = new Thickness(8), Margin = new Thickness(0, 0, 0, 12) };
    private readonly TextBlock error = new() { Foreground = System.Windows.Media.Brushes.DarkRed };
    public string CredentialName => credentialName.Text;
    public string Credential => credential.Password;
    public void ClearSecret() => credential.Clear();
    public ConnectorEditor(ConnectorDraft draft)
    {
        Draft = draft;
        Title = draft.Id.Length == 0 ? "Add connector" : "Edit connector";
        Width = 640;
        Height = 820;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        var panel = new StackPanel { Margin = new Thickness(24) };
        Content = new ScrollViewer { Content = panel, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
        void Field(string label, Control field)
        {
            panel.Children.Add(new TextBlock { Text = label, TextWrapping = TextWrapping.Wrap });
            panel.Children.Add(field);
        }
        name.Text = draft.Name;
        transport.SelectedItem = draft.Transport;
        command.Text = draft.Command;
        arguments.Text = draft.Arguments;
        url.Text = draft.Url;
        headers.Text = draft.HeaderReferences;
        environment.Text = draft.EnvironmentReferences;
        credentialName.Text = draft.Transport == "stdio" ? "API_KEY" : "Authorization";
        Field("Name", name);
        Field("Transport", transport);
        Field("Executable: absolute path to the real .exe (no .cmd/.bat wrappers)", command);
        Field("Arguments: one per line, no shell quoting", arguments);
        Field("Remote Streamable HTTP URL", url);
        Field("Header reference map (JSON; never put secret values here)", headers);
        Field("Environment reference map (JSON; never put secret values here)", environment);
        Field("Optional credential header / environment variable name", credentialName);
        Field("Secret value: stored only in Windows Credential Manager; blank means unchanged", credential);
        panel.Children.Add(new TextBlock { Text = "Saving edits disconnects the connector, clears OAuth authorization and resets its shared tool permissions. Reconnect and review the tools afterward.", TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 10, 0, 15) });
        panel.Children.Add(error);
        var buttons = new WrapPanel();
        var cancel = new Button { Content = "Cancel", IsCancel = true };
        var save = new Button { Content = "Save connector", IsDefault = true };
        buttons.Children.Add(cancel);
        buttons.Children.Add(save);
        panel.Children.Add(buttons);
        save.Click += (_, _) => { try { Draft.Name = name.Text; Draft.Transport = (string?)transport.SelectedItem ?? "stdio"; Draft.Command = command.Text; Draft.Arguments = arguments.Text; Draft.Url = url.Text; Draft.HeaderReferences = headers.Text; Draft.EnvironmentReferences = environment.Text; if (string.IsNullOrWhiteSpace(Draft.Name)) throw new ArgumentException("Give the connector a name."); if (Draft.Transport == "stdio" && (!Path.IsPathFullyQualified(Draft.Command) || !Draft.Command.EndsWith(".exe", StringComparison.OrdinalIgnoreCase))) throw new ArgumentException("Select an absolute .exe path. For Node-based servers use node.exe and the server JavaScript file as an argument; batch wrappers are not supported."); Draft.Payload(); DialogResult = true; } catch (Exception e) { error.Text = e.Message; } };
    }
}
