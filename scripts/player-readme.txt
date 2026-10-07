赤潮：钢铁前线 — 开始游戏（Windows 一键包）

1. 解压整个文件夹，不要只拷贝其中一个 exe。
2. 双击 ChichaoSteelFront.exe（或 start-game.bat）。
3. 控制台会打印本机地址和局域网地址；默认会打开浏览器到
   http://127.0.0.1:18081/
4. 把「局域网地址」发给同一网络里的队友，用 Chrome / Edge 打开即可。
5. 关闭控制台窗口即停止服务器。

Windows SmartScreen（未签名 exe 很常见）
- 若提示「Windows 已保护你的电脑」，点「更多信息」，再点「仍要运行」。
- 这不是游戏自带的杀毒扫描。正式签名证书需要另外购买，本包目前未签名。
- 防火墙若弹出 ChichaoSteelFront 入站提示，局域网联机请允许 TCP 18081。

换端口
  set PORT=8090
  ChichaoSteelFront.exe
或：
  start-game.bat 8090

战报
  自动保存在本 exe 旁边的 battle_reports\ 目录。
  若该目录不可写（例如装到了 Program Files），会改存到 %APPDATA%\ChichaoSteelFront\battle_reports。

不要把这个包和开发仓库混在一起发给玩家：
  不要附带 tests\、.git\、.kiro\、give_cash.py 或调试脚本。

macOS / Linux 玩家
  请使用源码包里的 ./start-game.sh，并自行安装 python3（只要标准库）。
