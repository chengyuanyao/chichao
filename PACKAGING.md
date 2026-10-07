# 发行打包（itch.io Windows 一键包）

本仓库的运行时仍是「Python 标准库服务器 + `public/` 浏览器客户端」，**不增加玩家依赖**。
Windows 买家要的是：解压后双击即可，不必先安装 Python。

## 选哪条路线

| 路线 | 结果 | 何时用 |
|---|---|---|
| **PyInstaller onedir（默认）** | `ChichaoSteelFront.exe` + `_internal/`，把 `server.py`、全部游戏模块和 `public/` 打进包 | itch 的 Windows 主下载 |
| 嵌入式 Python | 在启动器旁边放官方 embeddable `python\python.exe`，`start-game.bat` / 启动器会优先用它 | 想少改启动器、或本机暂时不便跑 PyInstaller |
| 源码包 | 去掉测试和调试文件的目录 + `start-game.sh` | **macOS / Linux 现阶段**；需要系统 `python3` |

本 PR 按 **PyInstaller onedir** 落地，同时让 `start-game.bat` 和启动器源码优先发现捆绑解释器 / 冻结 exe。

## 在 Windows 上打 zip

构建机需要：Windows 10/11、已安装 **Python 3.8+**（只给打包用，不会打进「玩家必须先装 Python」的说明）。

```
powershell -ExecutionPolicy Bypass -File scripts/build_windows_release.ps1
```

产物：

- `release/ChichaoSteelFront-win64.zip` — 给 itch 的 Windows 包
- `release/ChichaoSteelFront-source.zip` — 给 macOS / Linux（或愿意自己装 Python 的人）

Windows 包解压后大致是：

```
ChichaoSteelFront-win64/
  ChichaoSteelFront.exe    ← 双击这个
  _internal/               ← PyInstaller 运行库 + 打包进去的 public/
  start-game.bat
  开始游戏.txt
  README.md
  PACKAGING.md
```

Linux / macOS 上可以先跑检查和源码包（**不会**交叉编译出 Windows exe）：

```
./scripts/build_windows_release.sh
python3 scripts/stage_release.py check
```

## 冻结后的路径

`paths.py` 统一处理：

- **读**（`public/` 等）：冻结时用 `sys._MEIPASS`，源码运行时用仓库根目录。
- **写**（`battle_reports/`）：冻结时写到 **exe 旁边**；若目录只读（例如装到 `Program Files`），改写 `%APPDATA%\ChichaoSteelFront`（Unix 为 `~/.local/share/chichao-steel-front`）。
- 可用环境变量覆盖：`STEEL_FRONT_RESOURCE_DIR`、`STEEL_FRONT_DATA_DIR`。

`server.py` 里的 `ROOT` / `PUBLIC_ROOT` 来自 `paths.resource_root()`，不再写死 `__file__`。

### 怎么确认（不必真的打 Windows 包）

```
python3 tests/packaging_paths_test.py
python3 tests/packaging_manifest_test.py
python3 scripts/stage_release.py check
```

路径测试会假装 `sys.frozen` + `sys._MEIPASS`，检查静态文件从包内读、战报目录不落在只读 bundle 里。

在 Windows 打出 exe 之后再做一次实机确认：

1. 把 `ChichaoSteelFront-win64` 拷到一台 **没有安装 Python** 的 Windows 10/11。
2. 双击 `ChichaoSteelFront.exe`。
3. 控制台出现本机 / 局域网地址，浏览器应打开 `http://127.0.0.1:18081/`。
4. 首页和 `/api/health` 正常；打一局后 `battle_reports\` 出现在 exe 旁边。
5. 启动器若已用 `launcher/build-launcher.ps1` 重新编译，可再测「启动服务器」是否优先跑冻结 exe，且不会打开两个浏览器标签。
   仓库里现成的 `SteelFrontLauncher.exe` 是旧二进制；要让图形启动器识别冻结 exe / `python\python.exe`，必须在 Windows 上重编。未重编时，itch 买家直接双击 `ChichaoSteelFront.exe` 即可。

## 自动打开浏览器

满足下面之一就会在端口绑定成功后打开本机 URL：

- 冻结 exe（itch 包默认）；
- `start-game.bat` / `start-game.sh` 设置了 `STEEL_FRONT_OPEN_BROWSER=1`；
- 命令行 `--open-browser`。

不会打开的情况：`--no-browser`、`STEEL_FRONT_OPEN_BROWSER=0`、`STEEL_FRONT_LAUNCHER=1`（C# 启动器自己会开标签）、Linux 且没有 `DISPLAY` / `WAYLAND_DISPLAY`。

## SmartScreen

未签名的 exe 在 Windows 上常出现「Windows 已保护你的电脑」。请在商店页写明：

1. 点 **更多信息**；
2. 再点 **仍要运行**。

要消掉这层提示需要购买代码签名证书并改构建脚本签名，不在本包范围内。

局域网联机还需要允许 TCP **18081** 入站（或你改过的 `PORT`）。

## zip 里不要带什么

`scripts/stage_release.py` 是唯一清单。至少排除：

| 排除 | 原因 |
|---|---|
| `tests/` | 开发回归，约一百多个文件 |
| `.git/`、`.github/` | 版本库 |
| `.kiro/`、`.cursor/` | 编辑器 / 规格草稿 |
| `give_cash.py` | 本机调试加钱 |
| `CLAUDE.md` | 给代理看的开发备忘 |
| `ai_commander/llm.example.json`、`ai_commander/llm.json` | 密钥样例 / 本机凭据 |
| `__pycache__/`、`*.pyc`、`*.pid`、`*.log` | 生成物 |
| `dist/`、`build/`、`release/`、`scripts/` | 打包中间物；脚本只留在仓库 |
| `artifacts/`、`battle_reports/` | 本机输出 |

**要保留：** `public/`（含 `public/vendor/three.js` 与 MIT 声明）、`public/assets/audio/KENNEY-LICENSE.txt`、`server.py` 与同目录游戏模块、`start-game.sh` / `start-game.bat`、`README.md`。

嵌入式 Python 备选布局（手工）：

```
ChichaoSteelFront-win64/
  SteelFrontLauncher.exe
  start-game.bat
  python/          ← 官方 Windows embeddable 3.x，解压到这里
  server.py
  paths.py
  …其余 .py 与 public/
```

`start-game.bat` 和启动器源码会先找 `python\python.exe`，再回退到系统 Python。

## macOS / Linux（现阶段）

不提供冻结包也可以先发源码 zip：

```
./scripts/build_windows_release.sh
```

玩家：

```
unzip ChichaoSteelFront-source.zip
cd ChichaoSteelFront-source
./start-game.sh
```

需要系统 `python3`（3.6+，只要标准库）。脚本默认会在有桌面会话时打开浏览器。不要浏览器：`STEEL_FRONT_OPEN_BROWSER=0 ./start-game.sh`。

以后若要做 macOS / Linux 的 PyInstaller 包，可复用 `scripts/chichao.spec`，另开一条构建任务即可。

## 和 IP 清理 PR 的关系

若 [PR #56](https://github.com/chengyuanyao/chichao/pull/56)（`cursor/itch-ip-cleanup-d216`）尚未合并，本打包分支应在 #56 落地后再 rebase / 合并，避免商店包还带着旧单位名。本分支不重做那些改名。
