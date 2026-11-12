# YP001 BLE 扫描与 Beacon 调试记录

日期：2026-10-01。工程：`Keil_6/YP001_GR5526.uvprojx`，Arm Compiler 6.14。当前目标按顺序为：连续扫描无 HardFault、真实 Beacon 稳定解析、多 Beacon 正确选择、每分钟扫描 3 秒、整机功耗测量。

## 本轮已完成

- 对照 `user_app.c`：开机仅初始化 scanner，未调用 `ble_scanner_start()`；断线回调原本仍直接启动扫描，形成未门控的异常入口。现已让断线回调保持扫描关闭。
- 新增串口 CLI `ble_scan start` / `ble_scan stop`，让扫描启动由人工控制，便于 J-Link 抓取首次失败现场。开机仍不自动扫描，LCD/CAT1 管脚及显示流程未改。
- `bsp.c` 的 HardFault 处理从打印处理器自身 PC 改为保存异常栈帧：`yp001_fault_snapshot[0..11]` 含标记、EXC_RETURN、栈指针、异常前 LR/PC/xPSR、CFSR/HFSR/BFAR/MMFAR、R0/R1。串口同时输出关键寄存器。原有旧日志的 `PC=0x002048C2` 不能作为真正故障指令地址。
- 首次 Keil 6 构建因缺少 `Keil_6/YP001_GR5526.sct` 报 L6031U。现已按当前 `custom_config.h`、SDK `flash_scatter_config.h` 和链接器所需区域恢复该文件。`Keil_6/ble_scan_diag_build5.log` 为最终构建证据：Arm Compiler 6.14，0 错误、0 警告，AXF/HEX 已生成。map 核对向量表 `0x00202000`、应用信息 `0x00202200`、RAM_CODE `0x00106000`、数据区 `0x2000B000`、栈顶 `0x20080000`；本轮仍未下载或运行诊断版。
- 当前 Windows 仅列出 COM5；COM5 115200 可打开，2 秒内未收到字节。这不能证明板卡未运行或 UART0 已接对。
- Keil Debug 截图报 `Cannot load driver C:\Keil_v5\ARM\Segger\JL2CM3.dll`。文件存在；32 位加载实验表明 `JL2CM3.dll` 与 `JLTAgdi.dll` 在普通搜索路径下失败，给进程 PATH 加入 `C:\Keil_v5\ARM\Segger` 后均可加载。工程新增 `Keil_6/启动Keil6_JLink.cmd`，用该路径启动 µVision 并打开本工程；这只验证 DLL 加载条件，尚未验证用户界面 J-Link 连接与下载。
- 第二张截图仍报相同错误。进一步确认 32 位 µVision 的程序目录 `C:\Keil_v5\UV4` 原先没有 `JLinkARM.dll`，虽然 `ARM\Segger` 有该 DLL。已将现有 6.70e 的 32 位 `JLinkARM.dll` 复制到 `UV4` 目录（复制前目标不存在）；用 32 位加载器模拟 `UV4` DLL 搜索目录后，`JL2CM3.dll` 返回非零模块句柄。旧 Keil 进程/设置窗口仍需重新尝试；此项仍不是 J-Link 连板或下载成功证据。
- 后续 Keil 截图显示 `Insufficient RAM for Flash Algorithms`。用户实际打开的 `SVN交付_YP001_GR5526_20261001` 副本的 `.uvoptx` 被本机 Keil 设置改成 `-FC1000`（工作 RAM 4 KB）和 `-FS0100000`，与 `.uvprojx` 的 `-FC8000` / `-FS0200000` 不一致。现已同步修正交付副本 `.uvoptx` 的 J-Link 和 Utilities 两处，并在主工程、交付副本各加入 `验证Keil6交付.ps1`。两处检查均通过；此前主工程 `scan_safe_flash.log` 在 32 KB 设置下曾显示 Programming Done / Verify OK。本轮修正后尚未重新下载实板。
- 用户再次截图后复查发现，交付副本 `.uvoptx` 在 Keil 窗口打开期间又保存回 4 KB / 错误 Flash 起址。用户明确关闭 Keil 后，已备份该文件为 `.before-flash-ram-fix-20261001`，再次修正两处参数；重新打开工程后文件仍保持 `-FC8000`、`-FS0200000`，交付检查通过。主工程和交付副本的 `启动Keil6_JLink.cmd` 现在启动前均运行交付检查，错误配置会直接停止启动。尚无这次重新下载结果。

## 待恢复后执行的第一阶段

1. 在板子确认供电、J-Link SWD 可连接、串口确实对应 UART0 后，下载本诊断版；记录 LOGO 正常、BLE 初始化完成。此 scatter 是本轮依据源码恢复并通过静态 map 核对的新文件，尚无实板启动证明。
2. 从串口发 `ble_scan start` 一次；如异常，保存 `[FAULT]` 行和 J-Link 中 `yp001_fault_snapshot`、异常栈及 AXF 对应 map。若正常，记录扫描开始事件、广播计数和连续运行时间；再测 `ble_scan stop/start` 循环。
3. 得到异常前 PC 及调用栈后再定位根因。现阶段不更改扫描窗口、协议过滤或 Beacon 排序，以免混淆第一阶段结果。

## 后续阶段的已知检查点

- 园区 Beacon 样本须保存原始 AD 字节、地址类型、MAC 和 RSSI。当前解析器要求 MAC 前缀 `FC:18:19`、Flags 和至少 25 字节厂商字段，不能预先认定与现场设备兼容。
- 多 Beacon 缓存满时的最弱 RSSI 选择从 `-127` 开始，可能无法找出真实最弱项；在完成真实广播采样后单独修复并验证。
- 扫描间隔和窗口当前均为 100（单位 0.625 ms），超时 0；每分钟扫描 3 秒需待稳定性和兼容性通过后单独实现，最后用仪器测整机平均电流。

## 证据边界

本轮已有源码修改、成功链接和 map 地址静态证据。没有下载、当前板上扫描、园区 Beacon、长稳或功耗证据。旧 COM24 日志曾多次打印 `BLE Scanning started`，但与当前 Keil 6 诊断构建不同，不能替代本轮验收。
