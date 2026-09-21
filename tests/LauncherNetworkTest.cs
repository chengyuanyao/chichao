using System;
using System.Drawing;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Windows.Forms;
using SteelFrontLauncher;

internal static class LauncherNetworkTest
{
    static void Check(bool value, string message) { if (!value) throw new Exception(message); }
    static object Field(object form, string name) { return form.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic).GetValue(form); }
    [STAThread]
    static void Main(string[] args)
    {
        Check(NetworkSupport.ValidateHotspot("Chichao-LAN", "123456") != null, "short password rejected");
        Check(NetworkSupport.ValidateHotspot("Chichao-LAN", "12345678") == null, "default password accepted");
        Check(NetworkSupport.ValidateHotspot("赤潮", "abcd1234") == null, "Unicode SSID accepted");
        Check(NetworkSupport.ValidateHotspot(new string('界', 11), "abcd1234") != null, "SSID bounded by UTF8 bytes");
        Check(NetworkSupport.ValidateHotspot("", "abcd1234") != null, "empty SSID rejected");
        Check(NetworkSupport.ValidateHotspot("LAN", "abcd中文1234") != null, "ASCII password required");
        Check(NetworkSupport.ValidateHotspot("LAN", " abc12345") != null, "leading space rejected");
        Check(NetworkSupport.ValidateHotspot("LAN", new string('a', 64)) != null, "long password rejected");
        Check(NetworkSupport.AccessHost("0.0.0.0") == "127.0.0.1", "wildcard uses loopback");
        Check(NetworkSupport.AccessHost("192.168.137.1") == "192.168.137.1", "explicit NIC health URL");
        var choices = NetworkSupport.Choices();
        Check(choices[0].Address == "0.0.0.0", "compatibility option");
        Check(choices[choices.Count-1].Address == "127.0.0.1", "local-only option");
        var listener = new TcpListener(IPAddress.Parse("127.0.0.2"), 0);
        listener.Start();
        int port = ((IPEndPoint)listener.LocalEndpoint).Port;
        var probe = typeof(LauncherForm).GetMethod("TcpPortOpen", BindingFlags.Static | BindingFlags.NonPublic);
        try { Check((bool)probe.Invoke(null, new object[] {port}), "stop check detects non-default-interface listener"); }
        finally { listener.Stop(); }
        Check(!(bool)probe.Invoke(null, new object[] {port}), "released listener detected");
        Application.EnableVisualStyles();
        using (var form = new LauncherForm(new LauncherOptions { OpenBrowser = false }))
        {
            var network = (ComboBox)Field(form, "_networkInput");
            network.SelectedIndex = network.Items.Count - 1;
            Check(((Label)Field(form,"_localAddressLabel")).Text.Contains("127.0.0.1"), "local address follows selection");
            Check(!((Label)Field(form,"_lanAddressLabel")).Text.StartsWith("http"), "local-only not advertised to peers");
            Check(((TextBox)Field(form,"_hotspotPassword")).UseSystemPasswordChar, "password masked");
            Check(((TextBox)Field(form,"_hotspotPassword")).Text == "12345678", "default visible in configuration");
            foreach (Control control in form.Controls)
                Check(control.Right <= form.ClientSize.Width && control.Bottom <= form.ClientSize.Height, "control fits: " + control.Text);
            if (args.Length > 0)
                using (var bitmap = new Bitmap(form.Width, form.Height))
                { form.DrawToBitmap(bitmap, new Rectangle(Point.Empty, bitmap.Size)); bitmap.Save(args[0]); }
        }
        Console.WriteLine("Launcher network tests passed: validation, NIC URLs, port release, local-only UI, password masking and layout bounds. No hotspot was started.");
    }
}
