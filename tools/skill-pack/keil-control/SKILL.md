---
name: keil-control
description: Use when controlling Windows Keil uVision to build or download firmware, or when Keil window capture times out and input geometry is unavailable.
---

# Keil 编译、下载与窗口故障处理

SAM | 2026-10-14 +08:00 | 固化本地Keil控制方法，避免最小化窗口导致重复无效操作。

## 选择控制路径

编译和已核准的下载优先使用官方命令行；需要查看或调整设置时才操作GUI。Windows UI使用 `computer-use` 技能与 `sky` 公共API，重新选择唯一的真实窗口，不复用旧控件索引。

- 本机程序：`C:\Keil_v5\UV4\UV4.exe`。
- YP001主工程：`D:\CODEX\sos-card\ble_app_uart_c\Keil_6\YP001_GR5526.uvprojx`，Target=`YP001_GR5526_AC6`。
- 交付副本独立编译；不随意更改既有Keil、J-Link、Flash算法、scatter和LCD配置。
- 本地官方依据：`C:\Keil_v5\ARM\Hlp\uv4.chm` 中 `uv4_commandline.htm`、`uv4_fl_dlconfiguration.htm`。

## 命令行

通过正常shell工具运行，不能通过终端UI或Windows运行对话框执行。用 `Start-Process -WindowStyle Hidden -PassThru` 启动，保留进程对象；等待退出后 `Refresh()`，读取该进程的ExitCode和本次日志。不要把PowerShell直接启动GUI程序后空白的 `$LASTEXITCODE` 当成成功。

```powershell
$taskArgs=@('-b','"D:\CODEX\sos-card\ble_app_uart_c\Keil_6\YP001_GR5526.uvprojx"','-t','"YP001_GR5526_AC6"','-j0','-o','"D:\CODEX\sos-card\logs\keil_build_current.log"')
$taskKeil=Start-Process -FilePath 'C:\Keil_v5\UV4\UV4.exe' -ArgumentList $taskArgs -WindowStyle Hidden -PassThru
# 通过后续shell调用检查进程/日志，避免阻塞用户沟通。
```

官方 `-b` 为增量编译，`-r` 为重新编译，`-f` 为下载后退出，`-j0` 为隐藏GUI，`-o` 为保存日志。不要调用 `-c/-cr` 绕过项目清理白名单。编译后检查错误/警告、AXF/HEX及源码对应关系；增量无变化时产物时间不更新不等于失败。

下载前必须有用户明确授权，并核对当前目标、构建产物、备份、Flash布局及 **Erase Sectors**。该选项只擦程序涉及的扇区；禁止用 `-FO15` 猜测擦除含义，禁止因有备份就全片擦除。满足条件后才把上述 `-b` 换成 `-f`，使用独立下载日志。核对Program/Verify结果、设备启动、用户数据保护区及具体功能；不能用编译或下载成功代替功能通过。

## GUI失败时快速收敛

`FrameArrived timed out` 或 `coordinate input geometry is unavailable` 时，检查真实桌面的窗口是否最小化。最小化窗口常见矩形位于 `-32000,-32000`；可读到控件树不代表存在可点击/可抓图区域。受限shell与真实桌面的进程窗口视图可能不同；`sky`窗口ID是opaque，不能单凭与Get-Process句柄不同断言缓存失效。

按computer-use恢复规则刷新选择并重试一次。仍失败则停止UI循环，采用命令行；需要设置证据时让用户恢复窗口/查看选项，或使用已授权的只读真实桌面诊断。不要自建UI输入、猜坐标、强杀用户Keil进程或修改配置来绕过故障。下载尚未完成或擦除范围未知时，不能重复下载。

2026-10-14实测：真实Keil窗口仍响应但处于最小化，位置为 `-32000,-32000`；受限环境返回不同窗口信息。此证据解释本轮捕获/几何失败，不证明其他机器的同类报错均为此原因。详细证据见项目 `doc/2026-10-14_Keil控制故障与UART原始字节同步结论.md`。
