# CAT1 Luatools 下载时序上位机修改说明

SAM | 2026-10-15 11:10 +08:00 | 新增离线 Windows 上位机，固化 Air780EGH 进入 USB 下载模式的人工/软件协作时序。

## 本轮目标

现场已将 `BOOT` 与 `EXT` 飞线接到手动开关，用户要求通过上位机提示和控制 CAT1 固件更新时序。CAT1 未上电时 USB 设备不会枚举。核对当前 GR 源码后确认，`cat1_power on` 只拉高 VCC_4G，未操作 PWRKEY；工具现依次下发 `cat1_power on` 和 `cat1_power key`，后者在 GR 内保持 PWRKEY 约 1.6 秒。Luatools 已提供“模块重启”按键，因此该按键仍是进入下载模式的默认重启方式。

截图现场选择了 `COM29`，仅看到 TX、没有 GR CLI RX。工具现优先选择已有记录的 GR UART0 `COM26`，并在上电前发送 `help` 做端口探测；没有 GR CLI 回显时停止，不再把静默串口误判为上电成功。

## 新增文件

| 文件 | 作用 |
|---|---|
| `tools/cat1_download_assistant/DownloadSession.cs` | 独立、可测试的流程状态机，禁止跳过 BOOT 接通、重启、USB 枚举的顺序。 |
| `tools/cat1_download_assistant/MainForm.cs` | WinForms 操作界面，逐步显示现场动作和实际边界。 |
| `tools/cat1_download_assistant/tests/DesktopTests.cs` | 不开串口、不触碰硬件的状态机回归测试。 |
| `tools/cat1_download_assistant/build.ps1` | 使用系统 .NET Framework C# 编译器离线构建测试和 EXE。 |
| `tools/cat1_download_assistant/启动CAT1下载时序助手.bat` | 双击构建并启动入口。 |
| `tools/cat1_download_assistant/README.md` | 工具使用步骤及串口备用方案。 |

## 操作流程

1. 在新工具选择 GR UART0 COM 口，点击“连接并给 CAT1 上电”。工具依次发送 `cat1_power on`（VCC_4G）和 `cat1_power key`（约 1.6 秒 PWRKEY 脉冲）。
2. 先等待 Windows 设备管理器出现 CAT1 USB 设备；未枚举时不得进入下载步骤。
3. 在 Luatools 选定已核对的发布集合，保持等待下载，CAT1 USB 数据线持续连接；人工拨动飞线开关，使 `BOOT ↔ EXT` 接通。`EXT` 为 Air780EGH `VDD_EXT`；不能将 BOOT 接地、接 5 V 或接电池。
4. 在新工具点第 1 步，随后在 Luatools 点击“模块重启”。
5. Luatools 识别下载端口后，人工断开 `BOOT ↔ EXT`，在新工具确认第 3 步，再从 Luatools 开始下载。
6. 仅在 Luatools 明确显示下载完成后，才在新工具点第 4 步。

工具不自动点击 Luatools，也不从串口发送成功、USB 枚举成功推断固件下载成功。

## 串口备用路径

若 Luatools 的模块重启按键不可用，工具可连接 GR UART0（115200/8N1），并且只有在已确认 BOOT↔EXT 接通后，允许发送：

```text
cat_at ATREBOOT\r\n
```

既有 GR 串口桥将其转发到 Air780EGH UART1；当前 `Air780EGH/main.lua` 的 `ATREBOOT` 在 OTA 无挂起时调用 `rtos.reboot()`。这只能要求 Air780EGH 软件重启，不能替代飞线开关，也不能证明 Luatools 已接管 USB 下载。

## 不改变的范围

- 未修改 `Air780EGH` Lua、SOC 底包、分区、文件系统、KV 或 CAT1 固件内容。
- 未修改 GR5526 主工程或交付副本，故本轮没有新 GR AXF/HEX，也不把旧 AXF/HEX 称为本轮构建结果。
- 未自动发送擦除、清文件系统、清 KV 或底包下载命令。

## 验证结果

| 检查项 | 结果/证据 |
|---|---|
| 修改前工作区和目标文件检查 | 已检查；工作区存在大量用户未提交改动，本轮只新增独立工具目录。 |
| 主工程/交付副本差异检查 | 本轮未修改两份 GR 工程，无需同步。 |
| 代码时间/修改人/原因注释 | 新增 C# 和 PowerShell 文件均有 `SAM | 2026-10-15 11:10 +08:00` 注释。 |
| 本轮中文修改说明 | 本文档。 |
| 上位机状态机测试 | `tools/cat1_download_assistant/build.ps1`：上电请求、顺序限制和串口备用路径测试通过。 |
| 上位机 EXE 构建 | 每次构建生成 `tools/cat1_download_assistant/bin/CAT1DownloadAssistant_YYYYMMDD_HHMMSS.exe`，并由 `bin/latest.txt` 指向本次版本。这样不会覆盖现场正在运行的旧 EXE；每次重新编译均应重新取哈希。 |
| 主工程 Keil 6 编译 | 不适用：本轮未更改 GR 工程源码。 |
| 交付工程 Keil 6 编译 | 不适用：本轮未更改 GR 工程源码。 |
| 实板测试及未完成项目 | 尚未进行。需现场确认 Luatools 的“模块重启”在当前底包/USB 驱动下能识别下载端口，并以 Luatools 日志确认实际下载及模块启动。 |

本轮主机测试只证明上位机状态顺序和构建正确，不证明飞线极性、USB 下载端口、实际下载、脚本运行或用户数据保留已经实板通过。
