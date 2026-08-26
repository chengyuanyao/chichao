using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace SteelFrontLauncher
{
    internal static class NativeMethods
    {
        internal const uint JobObjectExtendedLimitInformationClass = 9;
        internal const uint JobObjectLimitKillOnJobClose = 0x00002000;

        [StructLayout(LayoutKind.Sequential)]
        internal struct JobObjectBasicLimitInformation
        {
            internal long PerProcessUserTimeLimit;
            internal long PerJobUserTimeLimit;
            internal uint LimitFlags;
            internal UIntPtr MinimumWorkingSetSize;
            internal UIntPtr MaximumWorkingSetSize;
            internal uint ActiveProcessLimit;
            internal UIntPtr Affinity;
            internal uint PriorityClass;
            internal uint SchedulingClass;
        }

        [StructLayout(LayoutKind.Sequential)]
        internal struct IoCounters
        {
            internal ulong ReadOperationCount;
            internal ulong WriteOperationCount;
            internal ulong OtherOperationCount;
            internal ulong ReadTransferCount;
            internal ulong WriteTransferCount;
            internal ulong OtherTransferCount;
        }

        [StructLayout(LayoutKind.Sequential)]
        internal struct JobObjectExtendedLimitInformation
        {
            internal JobObjectBasicLimitInformation BasicLimitInformation;
            internal IoCounters IoInfo;
            internal UIntPtr ProcessMemoryLimit;
            internal UIntPtr JobMemoryLimit;
            internal UIntPtr PeakProcessMemoryUsed;
            internal UIntPtr PeakJobMemoryUsed;
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        internal static extern IntPtr CreateJobObject(IntPtr jobAttributes, string name);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool SetInformationJobObject(
            IntPtr job, uint informationClass, IntPtr information,
            uint informationLength);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool AssignProcessToJobObject(
            IntPtr job, IntPtr process);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool CloseHandle(IntPtr handle);
    }

    internal sealed class LauncherOptions
    {
        public bool AutoStart;
        public bool OpenBrowser = true;
        public int Port = 18081;

        public static LauncherOptions Parse(string[] args)
        {
            LauncherOptions options = new LauncherOptions();
            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--autostart")
                {
                    options.AutoStart = true;
                }
                else if (args[i] == "--no-browser")
                {
                    options.OpenBrowser = false;
                }
                else if (args[i] == "--port" && i + 1 < args.Length)
                {
                    int port;
                    if (int.TryParse(args[++i], out port) && port >= 1024 && port <= 65535)
                        options.Port = port;
                }
            }
            return options;
        }
    }

    internal static class Program
    {
        private static Mutex _singleInstance;

        [STAThread]
        private static void Main(string[] args)
        {
            bool created;
            _singleInstance = new Mutex(true, "SteelFrontLANLauncher.Singleton", out created);
            if (!created)
            {
                MessageBox.Show("启动器已经打开。", "赤潮：钢铁前线",
                    MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }

            try
            {
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                Application.Run(new LauncherForm(LauncherOptions.Parse(args)));
            }
            finally
            {
                _singleInstance.ReleaseMutex();
                _singleInstance.Dispose();
            }
        }
    }

    internal sealed class LauncherForm : Form
    {
        private enum ServerState
        {
            Stopped,
            Starting,
            Running,
            Stopping
        }

        private static readonly Color Background = Color.FromArgb(22, 25, 17);
        private static readonly Color Panel = Color.FromArgb(38, 42, 28);
        private static readonly Color Border = Color.FromArgb(95, 91, 52);
        private static readonly Color Gold = Color.FromArgb(222, 181, 65);
        private static readonly Color Pale = Color.FromArgb(224, 220, 186);
        private static readonly Color Muted = Color.FromArgb(153, 154, 128);
        private static readonly Color Green = Color.FromArgb(91, 210, 112);
        private static readonly Color Red = Color.FromArgb(214, 83, 72);

        private readonly LauncherOptions _options;
        private readonly string _repoRoot;
        private readonly string _logPath;
        private readonly object _logLock = new object();
        private readonly StringBuilder _recentLog = new StringBuilder();
        private readonly System.Windows.Forms.Timer _healthTimer;

        private Label _statusLabel;
        private Label _sourceLabel;
        private Label _localAddressLabel;
        private Label _lanAddressLabel;
        private NumericUpDown _portInput;
        private CheckBox _openBrowserCheck;
        private Button _toggleButton;
        private Button _openButton;
        private LinkLabel _logLink;

        private Process _serverProcess;
        private IntPtr _serverJob = IntPtr.Zero;
        private ServerState _state = ServerState.Stopped;
        private DateTime _startDeadline;
        private bool _healthChecking;
        private bool _browserOpenedForRun;
        private bool _stoppingByUser;

        public LauncherForm(LauncherOptions options)
        {
            _options = options;
            _repoRoot = FindRepoRoot(Application.StartupPath);
            _logPath = Path.Combine(_repoRoot, "launcher.log");

            Text = "赤潮：钢铁前线 - 服务器启动器";
            BackColor = Background;
            ForeColor = Pale;
            Font = new Font("Microsoft YaHei UI", 10F, FontStyle.Regular, GraphicsUnit.Point);
            ClientSize = new Size(620, 440);
            MinimumSize = new Size(636, 479);
            MaximumSize = new Size(636, 479);
            FormBorderStyle = FormBorderStyle.FixedSingle;
            MaximizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            AutoScaleMode = AutoScaleMode.Dpi;

            BuildInterface();
            _portInput.Value = options.Port;
            _openBrowserCheck.Checked = options.OpenBrowser;
            UpdateAddresses();
            UpdateStoppedState();

            _healthTimer = new System.Windows.Forms.Timer();
            _healthTimer.Interval = 400;
            _healthTimer.Tick += delegate { QueueHealthCheck(); };

            FormClosing += delegate { StopServer(true); };
            Shown += delegate
            {
                if (_options.AutoStart)
                    BeginInvoke((MethodInvoker)delegate { StartServer(); });
            };
        }

        private void BuildInterface()
        {
            Panel header = new Panel();
            header.SetBounds(0, 0, 620, 92);
            header.BackColor = Panel;
            Controls.Add(header);

            Label title = new Label();
            title.Text = "赤潮：钢铁前线";
            title.Font = new Font("Microsoft YaHei UI", 21F, FontStyle.Bold, GraphicsUnit.Point);
            title.ForeColor = Gold;
            title.AutoSize = true;
            title.Location = new Point(26, 15);
            header.Controls.Add(title);

            Label subtitle = new Label();
            subtitle.Text = "局域网服务器启动器  ·  当前源码直接运行";
            subtitle.Font = new Font("Microsoft YaHei UI", 9.5F, FontStyle.Regular, GraphicsUnit.Point);
            subtitle.ForeColor = Muted;
            subtitle.AutoSize = true;
            subtitle.Location = new Point(29, 59);
            header.Controls.Add(subtitle);

            _statusLabel = new Label();
            _statusLabel.AutoSize = true;
            _statusLabel.Font = new Font("Microsoft YaHei UI", 12F, FontStyle.Bold, GraphicsUnit.Point);
            _statusLabel.Location = new Point(30, 112);
            Controls.Add(_statusLabel);

            Label sourceCaption = MakeCaption("运行文件", 30, 153);
            Controls.Add(sourceCaption);
            _sourceLabel = MakeValue(Path.Combine(_repoRoot, "server.py"), 116, 151, 470);
            Controls.Add(_sourceLabel);

            Label portCaption = MakeCaption("服务端口", 30, 194);
            Controls.Add(portCaption);
            _portInput = new NumericUpDown();
            _portInput.SetBounds(116, 188, 112, 30);
            _portInput.Minimum = 1024;
            _portInput.Maximum = 65535;
            _portInput.BackColor = Color.FromArgb(13, 15, 11);
            _portInput.ForeColor = Pale;
            _portInput.BorderStyle = BorderStyle.FixedSingle;
            _portInput.ValueChanged += delegate { UpdateAddresses(); };
            Controls.Add(_portInput);

            Label modeNote = new Label();
            modeNote.Text = "拉取代码后无需重新生成 EXE，下次启动自动使用最新源码";
            modeNote.AutoSize = true;
            modeNote.ForeColor = Muted;
            modeNote.Location = new Point(246, 193);
            Controls.Add(modeNote);

            Label localCaption = MakeCaption("本机地址", 30, 239);
            Controls.Add(localCaption);
            _localAddressLabel = MakeValue("", 116, 237, 470);
            _localAddressLabel.ForeColor = Gold;
            Controls.Add(_localAddressLabel);

            Label lanCaption = MakeCaption("局域网", 30, 278);
            Controls.Add(lanCaption);
            _lanAddressLabel = MakeValue("", 116, 276, 470);
            Controls.Add(_lanAddressLabel);

            _openBrowserCheck = new CheckBox();
            _openBrowserCheck.Text = "服务器启动成功后自动打开浏览器";
            _openBrowserCheck.AutoSize = true;
            _openBrowserCheck.ForeColor = Pale;
            _openBrowserCheck.FlatStyle = FlatStyle.Flat;
            _openBrowserCheck.Location = new Point(30, 319);
            Controls.Add(_openBrowserCheck);

            _logLink = new LinkLabel();
            _logLink.Text = "查看启动日志";
            _logLink.AutoSize = true;
            _logLink.LinkColor = Muted;
            _logLink.ActiveLinkColor = Gold;
            _logLink.VisitedLinkColor = Muted;
            _logLink.Location = new Point(493, 319);
            _logLink.LinkClicked += delegate { OpenLog(); };
            Controls.Add(_logLink);

            _toggleButton = new Button();
            _toggleButton.SetBounds(30, 360, 385, 54);
            _toggleButton.FlatStyle = FlatStyle.Flat;
            _toggleButton.FlatAppearance.BorderSize = 1;
            _toggleButton.Font = new Font("Microsoft YaHei UI", 12F, FontStyle.Bold, GraphicsUnit.Point);
            _toggleButton.Cursor = Cursors.Hand;
            _toggleButton.Click += delegate
            {
                if (_state == ServerState.Stopped)
                    StartServer();
                else if (_state == ServerState.Running || _state == ServerState.Starting)
                    StopServer(false);
            };
            Controls.Add(_toggleButton);

            _openButton = new Button();
            _openButton.Text = "打开游戏";
            _openButton.SetBounds(429, 360, 161, 54);
            _openButton.FlatStyle = FlatStyle.Flat;
            _openButton.FlatAppearance.BorderColor = Border;
            _openButton.FlatAppearance.BorderSize = 1;
            _openButton.BackColor = Panel;
            _openButton.ForeColor = Pale;
            _openButton.Font = new Font("Microsoft YaHei UI", 11F, FontStyle.Bold, GraphicsUnit.Point);
            _openButton.Cursor = Cursors.Hand;
            _openButton.Click += delegate { OpenGame(); };
            Controls.Add(_openButton);
        }

        private static Label MakeCaption(string text, int x, int y)
        {
            Label label = new Label();
            label.Text = text;
            label.AutoSize = true;
            label.ForeColor = Muted;
            label.Location = new Point(x, y);
            return label;
        }

        private static Label MakeValue(string text, int x, int y, int width)
        {
            Label label = new Label();
            label.Text = text;
            label.AutoEllipsis = true;
            label.ForeColor = Pale;
            label.SetBounds(x, y, width, 28);
            return label;
        }

        private void StartServer()
        {
            if (_state != ServerState.Stopped)
                return;

            string script = Path.Combine(_repoRoot, "server.py");
            if (!File.Exists(script))
            {
                MessageBox.Show("找不到 server.py。请把启动器放在游戏仓库根目录。",
                    "无法启动", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            string python = PythonLocator.FindPython3();
            if (String.IsNullOrEmpty(python))
            {
                MessageBox.Show(
                    "没有找到 Python 3。\n\n安装 Python 3 并勾选 Add Python to PATH 后重试。",
                    "无法启动", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            int port = Decimal.ToInt32(_portInput.Value);
            InitializeLog(python, script, port);

            ProcessStartInfo startInfo = new ProcessStartInfo();
            startInfo.FileName = python;
            startInfo.Arguments = Quote(script);
            startInfo.WorkingDirectory = _repoRoot;
            startInfo.UseShellExecute = false;
            startInfo.CreateNoWindow = true;
            startInfo.WindowStyle = ProcessWindowStyle.Hidden;
            startInfo.RedirectStandardOutput = true;
            startInfo.RedirectStandardError = true;
            startInfo.StandardOutputEncoding = Encoding.UTF8;
            startInfo.StandardErrorEncoding = Encoding.UTF8;
            startInfo.EnvironmentVariables["PORT"] = port.ToString();
            startInfo.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
            startInfo.EnvironmentVariables["PYTHONUNBUFFERED"] = "1";

            Process process = new Process();
            process.StartInfo = startInfo;
            process.EnableRaisingEvents = true;
            process.OutputDataReceived += delegate(object sender, DataReceivedEventArgs e)
            {
                if (e.Data != null) AppendLog(e.Data);
            };
            process.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs e)
            {
                if (e.Data != null) AppendLog(e.Data);
            };
            process.Exited += delegate
            {
                int exitCode = -1;
                try { exitCode = process.ExitCode; }
                catch { }
                SafeBeginInvoke(delegate { HandleProcessExited(process, exitCode); });
            };

            bool started = false;
            try
            {
                if (!process.Start())
                    throw new InvalidOperationException("Python 进程没有启动");
                started = true;
                _serverProcess = process;
                if (!AttachKillOnCloseJob(process))
                    AppendLog("警告：无法建立进程树托管，停止时将使用 taskkill /T 兜底。");
                process.BeginOutputReadLine();
                process.BeginErrorReadLine();
            }
            catch (Exception exc)
            {
                if (started)
                {
                    bool killedByJob = ReleaseServerJob();
                    if (!killedByJob)
                        KillProcessTree(process.Id);
                    try
                    {
                        if (!HasExited(process))
                        {
                            process.Kill();
                            process.WaitForExit(3000);
                        }
                    }
                    catch { }
                }
                _serverProcess = null;
                process.Dispose();
                AppendLog("启动失败：" + exc);
                MessageBox.Show("服务器启动失败：\n" + exc.Message + "\n\n详情见 launcher.log。",
                    "无法启动", MessageBoxButtons.OK, MessageBoxIcon.Error);
                UpdateStoppedState();
                return;
            }

            _state = ServerState.Starting;
            _stoppingByUser = false;
            _browserOpenedForRun = false;
            _startDeadline = DateTime.UtcNow.AddSeconds(12);
            _portInput.Enabled = false;
            _toggleButton.Enabled = true;
            _toggleButton.Text = "停止服务器";
            _toggleButton.BackColor = Red;
            _toggleButton.ForeColor = Color.White;
            _toggleButton.FlatAppearance.BorderColor = Color.FromArgb(244, 121, 103);
            _openButton.Enabled = false;
            SetStatus("● 正在启动……", Gold);
            _healthTimer.Start();
            QueueHealthCheck();
        }

        private void QueueHealthCheck()
        {
            if (_healthChecking || _state != ServerState.Starting)
                return;
            if (_serverProcess == null || HasExited(_serverProcess))
                return;

            _healthChecking = true;
            int port = Decimal.ToInt32(_portInput.Value);
            ThreadPool.QueueUserWorkItem(delegate
            {
                bool healthy = false;
                try
                {
                    HttpWebRequest request = (HttpWebRequest)WebRequest.Create(
                        "http://127.0.0.1:" + port + "/api/health");
                    request.Method = "GET";
                    request.Timeout = 350;
                    request.ReadWriteTimeout = 350;
                    request.KeepAlive = false;
                    using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
                        healthy = response.StatusCode == HttpStatusCode.OK;
                }
                catch { }

                SafeBeginInvoke(delegate
                {
                    _healthChecking = false;
                    if (_state != ServerState.Starting)
                        return;
                    if (healthy)
                    {
                        MarkRunning();
                    }
                    else if (DateTime.UtcNow > _startDeadline)
                    {
                        SetStatus("● 启动较慢，仍在等待服务响应……", Gold);
                    }
                });
            });
        }

        private void MarkRunning()
        {
            if (_state != ServerState.Starting)
                return;
            _state = ServerState.Running;
            _healthTimer.Stop();
            _openButton.Enabled = true;
            SetStatus("● 服务器运行中", Green);
            AppendLog("服务器健康检查通过。");
            if (_openBrowserCheck.Checked && !_browserOpenedForRun)
            {
                _browserOpenedForRun = true;
                OpenGame();
            }
        }

        private void StopServer(bool closing)
        {
            Process process = _serverProcess;
            if (process == null)
            {
                ReleaseServerJob();
                return;
            }

            _state = ServerState.Stopping;
            _stoppingByUser = true;
            _healthTimer.Stop();
            if (!closing)
            {
                _toggleButton.Enabled = false;
                _openButton.Enabled = false;
                SetStatus("● 正在停止……", Red);
            }

            int port = Decimal.ToInt32(_portInput.Value);
            bool killedByJob = ReleaseServerJob();
            try
            {
                if (!HasExited(process))
                {
                    if (!killedByJob)
                        KillProcessTree(process.Id);
                    if (!HasExited(process))
                        process.Kill();
                    process.WaitForExit(3000);
                }
            }
            catch (Exception exc)
            {
                AppendLog("停止服务器时出现错误：" + exc.Message);
            }

            if (ReferenceEquals(_serverProcess, process))
            {
                _serverProcess = null;
                process.Dispose();
            }
            bool portReleased = WaitForPortRelease(port, 5000);
            AppendLog(portReleased
                ? "服务器进程树已全部停止，端口已释放。"
                : "停止异常：服务进程已结束，但端口仍被其他进程占用。");
            if (!closing && !portReleased)
            {
                MessageBox.Show(
                    "服务器进程树已经结束，但端口 " + port +
                    " 仍被其他程序占用。\n\n启动器不会把这种状态误报为已彻底停止，请检查 launcher.log。",
                    "端口仍被占用", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
            if (!closing)
                UpdateStoppedState();
        }

        private void HandleProcessExited(Process process, int exitCode)
        {
            if (!ReferenceEquals(_serverProcess, process))
                return;

            _healthTimer.Stop();
            _serverProcess = null;
            ReleaseServerJob();
            process.Dispose();
            bool expected = _stoppingByUser;
            UpdateStoppedState();

            if (!expected)
            {
                string detail = RecentLogTail();
                MessageBox.Show(
                    "服务器已退出（代码 " + exitCode + "）。\n\n" +
                    (String.IsNullOrEmpty(detail) ? "请查看 launcher.log。" : detail),
                    "服务器未运行", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }

        private void UpdateStoppedState()
        {
            _state = ServerState.Stopped;
            _stoppingByUser = false;
            _healthChecking = false;
            if (_healthTimer != null) _healthTimer.Stop();
            if (_portInput != null) _portInput.Enabled = true;
            if (_toggleButton != null)
            {
                _toggleButton.Enabled = true;
                _toggleButton.Text = "启动服务器";
                _toggleButton.BackColor = Gold;
                _toggleButton.ForeColor = Color.FromArgb(25, 22, 10);
                _toggleButton.FlatAppearance.BorderColor = Color.FromArgb(248, 214, 107);
            }
            if (_openButton != null) _openButton.Enabled = false;
            if (_statusLabel != null) SetStatus("● 服务器已停止", Muted);
        }

        private void SetStatus(string text, Color color)
        {
            _statusLabel.Text = text;
            _statusLabel.ForeColor = color;
        }

        private void UpdateAddresses()
        {
            if (_portInput == null || _localAddressLabel == null)
                return;
            int port = Decimal.ToInt32(_portInput.Value);
            _localAddressLabel.Text = "http://127.0.0.1:" + port;
            List<string> addresses = LocalIpv4Addresses();
            if (addresses.Count == 0)
                _lanAddressLabel.Text = "未检测到可用的局域网地址";
            else
                _lanAddressLabel.Text = "http://" + addresses[0] + ":" + port;
        }

        private void OpenGame()
        {
            try
            {
                ProcessStartInfo info = new ProcessStartInfo();
                info.FileName = _localAddressLabel.Text;
                info.UseShellExecute = true;
                Process.Start(info);
            }
            catch (Exception exc)
            {
                MessageBox.Show("无法打开浏览器：\n" + exc.Message,
                    "打开失败", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }

        private void OpenLog()
        {
            try
            {
                if (!File.Exists(_logPath))
                    File.WriteAllText(_logPath, "尚未启动过服务器。\r\n", new UTF8Encoding(false));
                ProcessStartInfo info = new ProcessStartInfo();
                info.FileName = _logPath;
                info.UseShellExecute = true;
                Process.Start(info);
            }
            catch (Exception exc)
            {
                MessageBox.Show("无法打开日志：\n" + exc.Message,
                    "打开失败", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }

        private void InitializeLog(string python, string script, int port)
        {
            lock (_logLock)
            {
                _recentLog.Length = 0;
                string header = "赤潮启动器 " + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") +
                    Environment.NewLine + "Python: " + python + Environment.NewLine +
                    "Script: " + script + Environment.NewLine + "Port: " + port +
                    Environment.NewLine + new String('-', 60) + Environment.NewLine;
                try { File.WriteAllText(_logPath, header, new UTF8Encoding(false)); }
                catch { }
            }
        }

        private void AppendLog(string line)
        {
            lock (_logLock)
            {
                if (_recentLog.Length > 12000)
                    _recentLog.Remove(0, _recentLog.Length - 8000);
                _recentLog.AppendLine(line);
                try
                {
                    File.AppendAllText(_logPath, line + Environment.NewLine,
                        new UTF8Encoding(false));
                }
                catch { }
            }
        }

        private string RecentLogTail()
        {
            lock (_logLock)
            {
                string text = _recentLog.ToString().Trim();
                if (text.Length > 1200)
                    text = text.Substring(text.Length - 1200);
                return text;
            }
        }

        private void SafeBeginInvoke(MethodInvoker action)
        {
            try
            {
                if (!IsDisposed && IsHandleCreated)
                    BeginInvoke(action);
            }
            catch (ObjectDisposedException) { }
            catch (InvalidOperationException) { }
        }

        private static bool HasExited(Process process)
        {
            try { return process.HasExited; }
            catch { return true; }
        }

        private bool AttachKillOnCloseJob(Process process)
        {
            IntPtr job = NativeMethods.CreateJobObject(IntPtr.Zero, null);
            if (job == IntPtr.Zero)
                return false;

            IntPtr buffer = IntPtr.Zero;
            bool assigned = false;
            try
            {
                NativeMethods.JobObjectExtendedLimitInformation limits =
                    new NativeMethods.JobObjectExtendedLimitInformation();
                limits.BasicLimitInformation.LimitFlags =
                    NativeMethods.JobObjectLimitKillOnJobClose;
                int length = Marshal.SizeOf(typeof(
                    NativeMethods.JobObjectExtendedLimitInformation));
                buffer = Marshal.AllocHGlobal(length);
                Marshal.StructureToPtr(limits, buffer, false);
                if (!NativeMethods.SetInformationJobObject(
                        job, NativeMethods.JobObjectExtendedLimitInformationClass,
                        buffer, (uint)length))
                    return false;
                if (!NativeMethods.AssignProcessToJobObject(job, process.Handle))
                    return false;
                _serverJob = job;
                assigned = true;
                return true;
            }
            finally
            {
                if (buffer != IntPtr.Zero)
                    Marshal.FreeHGlobal(buffer);
                if (!assigned)
                    NativeMethods.CloseHandle(job);
            }
        }

        private bool ReleaseServerJob()
        {
            IntPtr job = _serverJob;
            _serverJob = IntPtr.Zero;
            return job != IntPtr.Zero && NativeMethods.CloseHandle(job);
        }

        private static void KillProcessTree(int processId)
        {
            try
            {
                ProcessStartInfo info = new ProcessStartInfo();
                info.FileName = "taskkill.exe";
                info.Arguments = "/PID " + processId + " /T /F";
                info.UseShellExecute = false;
                info.CreateNoWindow = true;
                info.WindowStyle = ProcessWindowStyle.Hidden;
                using (Process killer = Process.Start(info))
                {
                    if (killer != null)
                        killer.WaitForExit(3000);
                }
            }
            catch { }
        }

        private static bool WaitForPortRelease(int port, int timeoutMs)
        {
            Stopwatch watch = Stopwatch.StartNew();
            while (watch.ElapsedMilliseconds < timeoutMs)
            {
                if (!TcpPortOpen(port))
                    return true;
                Thread.Sleep(100);
            }
            return !TcpPortOpen(port);
        }

        private static bool TcpPortOpen(int port)
        {
            try
            {
                using (TcpClient client = new TcpClient())
                {
                    IAsyncResult pending = client.BeginConnect(
                        IPAddress.Loopback, port, null, null);
                    try
                    {
                        if (!pending.AsyncWaitHandle.WaitOne(150))
                            return false;
                        client.EndConnect(pending);
                        return true;
                    }
                    finally
                    {
                        pending.AsyncWaitHandle.Close();
                    }
                }
            }
            catch
            {
                return false;
            }
        }

        private static string Quote(string value)
        {
            return "\"" + value.Replace("\"", "\\\"") + "\"";
        }

        private static string FindRepoRoot(string start)
        {
            DirectoryInfo directory = new DirectoryInfo(start);
            for (int depth = 0; directory != null && depth < 6; depth++, directory = directory.Parent)
            {
                if (File.Exists(Path.Combine(directory.FullName, "server.py")))
                    return directory.FullName;
            }
            return start;
        }

        private static List<string> LocalIpv4Addresses()
        {
            List<string> result = new List<string>();
            try
            {
                foreach (NetworkInterface item in NetworkInterface.GetAllNetworkInterfaces())
                {
                    if (item.OperationalStatus != OperationalStatus.Up ||
                        item.NetworkInterfaceType == NetworkInterfaceType.Loopback)
                        continue;
                    foreach (UnicastIPAddressInformation address in item.GetIPProperties().UnicastAddresses)
                    {
                        if (address.Address.AddressFamily != AddressFamily.InterNetwork)
                            continue;
                        string value = address.Address.ToString();
                        if (value.StartsWith("169.254.") || value == "127.0.0.1")
                            continue;
                        if (!result.Contains(value)) result.Add(value);
                    }
                }
            }
            catch { }
            return result;
        }
    }

    internal static class PythonLocator
    {
        public static string FindPython3()
        {
            List<string> candidates = new List<string>();
            string configured = Environment.GetEnvironmentVariable("STEEL_FRONT_PYTHON");
            if (!String.IsNullOrEmpty(configured)) candidates.Add(configured.Trim('"'));

            string launcherResult = Capture("py.exe",
                "-3 -c \"import sys; print(sys.executable)\"", 5000);
            AddLines(candidates, launcherResult);

            string whereResult = Capture("where.exe", "python.exe", 3000);
            AddLines(candidates, whereResult);

            string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string programs = Path.Combine(local, "Programs", "Python");
            if (Directory.Exists(programs))
            {
                try
                {
                    foreach (string directory in Directory.GetDirectories(programs, "Python*"))
                        candidates.Add(Path.Combine(directory, "python.exe"));
                }
                catch { }
            }

            foreach (string candidate in candidates)
            {
                string path = candidate.Trim();
                if (!File.Exists(path)) continue;
                string probe = Capture(path,
                    "-c \"import sys; print(sys.version_info[0])\"", 5000).Trim();
                if (probe == "3") return path;
            }
            return null;
        }

        private static void AddLines(List<string> target, string value)
        {
            if (String.IsNullOrWhiteSpace(value)) return;
            foreach (string line in value.Split(new[] { '\r', '\n' },
                StringSplitOptions.RemoveEmptyEntries))
            {
                string path = line.Trim().Trim('"');
                if (!target.Contains(path)) target.Add(path);
            }
        }

        private static string Capture(string fileName, string arguments, int timeoutMs)
        {
            try
            {
                ProcessStartInfo info = new ProcessStartInfo();
                info.FileName = fileName;
                info.Arguments = arguments;
                info.UseShellExecute = false;
                info.CreateNoWindow = true;
                info.WindowStyle = ProcessWindowStyle.Hidden;
                info.RedirectStandardOutput = true;
                info.RedirectStandardError = true;
                using (Process process = Process.Start(info))
                {
                    string output = process.StandardOutput.ReadToEnd();
                    if (!process.WaitForExit(timeoutMs))
                    {
                        try { process.Kill(); }
                        catch { }
                        return "";
                    }
                    return process.ExitCode == 0 ? output : "";
                }
            }
            catch { return ""; }
        }
    }
}
