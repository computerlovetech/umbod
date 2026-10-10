using System.Windows;
using Umbod.Core;
namespace Umbod.Windows;
public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        try
        {
            var marker = Path.Combine(AppContext.BaseDirectory, "umbod-profile");
            var profile = File.Exists(marker) ? File.ReadAllText(marker).Trim() : "dev";
            var smoke = e.Args.Contains("--smoke-test");
            var window = new MainWindow(new AppProfile(profile), smoke);
            MainWindow = window;
            window.Show();
            if (smoke)
            {
                window.Dispatcher.InvokeAsync(() =>
                {
                    if (window.Tabs.Items.Count != 3)
                    {
                        Shutdown(1);
                        return;
                    }
                    Console.WriteLine("PASS WPF window construction and dispatcher smoke (no gateway or vault access)");
                    window.Close();
                });
            }
        }
        catch (Exception error)
        {
            if (!e.Args.Contains("--smoke-test"))
                MessageBox.Show("Umbod could not initialize: " + error.Message, "Umbod", MessageBoxButton.OK, MessageBoxImage.Error);
            Shutdown(1);
        }
    }
}
