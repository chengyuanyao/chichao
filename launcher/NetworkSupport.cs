using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;

namespace SteelFrontLauncher
{
    internal sealed class NetworkChoice
    {
        public string Id, Address, Name;
        public override string ToString() { return Name + "  ·  " + Address; }
    }

    internal static class NetworkSupport
    {
        public static List<NetworkChoice> Choices()
        {
            var result = new List<NetworkChoice>();
            foreach (var adapter in NetworkInterface.GetAllNetworkInterfaces())
            {
                if (adapter.OperationalStatus != OperationalStatus.Up ||
                    adapter.NetworkInterfaceType == NetworkInterfaceType.Loopback) continue;
                foreach (var ip in adapter.GetIPProperties().UnicastAddresses)
                {
                    if (ip.Address.AddressFamily != AddressFamily.InterNetwork ||
                        ip.Address.ToString().StartsWith("169.254.")) continue;
                    result.Add(new NetworkChoice { Id = adapter.Id, Address = ip.Address.ToString(),
                        Name = adapter.Name + (adapter.NetworkInterfaceType == NetworkInterfaceType.Wireless80211 ? " [Wi-Fi]" : "") });
                }
            }
            result.Sort(delegate(NetworkChoice a, NetworkChoice b) { return String.Compare(a.Name, b.Name, StringComparison.Ordinal); });
            result.Insert(0, new NetworkChoice { Id = "", Address = "0.0.0.0", Name = "全部网卡（兼容模式）" });
            result.Add(new NetworkChoice { Id = "", Address = "127.0.0.1", Name = "仅本机（他人无法加入）" });
            return result;
        }

        public static string AccessHost(string bindAddress)
        { return bindAddress == "0.0.0.0" ? "127.0.0.1" : bindAddress; }

        public static string ValidateHotspot(string ssid, string password)
        {
            if (String.IsNullOrWhiteSpace(ssid) || Encoding.UTF8.GetByteCount(ssid) > 32 || ssid.IndexOf('\0') >= 0)
                return "热点名称不能为空，UTF-8 长度不能超过 32 字节。";
            if (password == null || password.Length < 8 || password.Length > 63 || password.Trim() != password)
                return "热点密码须为 8–63 位可打印英文字符，首尾不能有空格。123456 不符合 Windows 要求。";
            foreach (char c in password) if (c < 32 || c > 126) return "热点密码只能使用英文、数字和可打印英文符号。";
            return null;
        }

        // Never put the password in command-line arguments, logs or disk files.
        public static Dictionary<string, object> Hotspot(string root, string action, string adapterId, string ssid, string password)
        {
            var info = new ProcessStartInfo();
            info.FileName = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell\\v1.0\\powershell.exe");
            info.Arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File \"" + Path.Combine(root, "launcher", "hotspot.ps1") + "\"";
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.WindowStyle = ProcessWindowStyle.Hidden;
            info.RedirectStandardInput = info.RedirectStandardOutput = info.RedirectStandardError = true;
            info.StandardOutputEncoding = info.StandardErrorEncoding = Encoding.UTF8;
            var json = new JavaScriptSerializer();
            using (var process = Process.Start(info))
            {
                var output = process.StandardOutput.ReadToEndAsync();
                var errors = process.StandardError.ReadToEndAsync();
                // ASCII JSON escapes avoid Windows PowerShell stdin code-page ambiguity.
                string input = json.Serialize(new { action = action, adapterId = adapterId, ssid = ssid, password = password });
                var ascii = new StringBuilder();
                foreach (char c in input) ascii.Append(c > 127 ? "\\u" + ((int)c).ToString("x4") : c.ToString());
                process.StandardInput.WriteLine(ascii.ToString());
                process.StandardInput.Close();
                if (!process.WaitForExit(45000))
                {
                    try { process.Kill(); } catch { }
                    throw new InvalidOperationException("热点操作超时，状态不确定。请打开系统热点设置核实，必要时手动关闭。" );
                }
                string text = output.Result.Trim();
                if (text.Length == 0) throw new InvalidOperationException("系统热点接口不可用，请使用 Windows 热点设置。" );
                var result = json.Deserialize<Dictionary<string, object>>(text);
                if (!Convert.ToBoolean(result["ok"])) throw new InvalidOperationException(Convert.ToString(result["error"]));
                return result;
            }
        }
    }
}
