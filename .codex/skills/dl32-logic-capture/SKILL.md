---
name: dl32-logic-capture
description: Use when controlling the local ATK-Logic DL32 USB logic analyzer or diagnosing YP001 GR5526-Air780EGH UART with its captured data.
---

# DL32 快速采集与 UART 定位

本机 ATK-Logic：`D:\Program Files\ATK-Logic\ATK-Logic.exe`，手册为同目录 `ATK-Logic_en_US.pdf`。先通过 `Get-Process -Name ATK-Logic` 和 Computer Use 的 `sky.list_apps()` 复用唯一的 `ATK-LogicView - DL32` 窗口，不启动第二实例。Windows UI 操作必须先读 `computer-use` 技能，再观察界面、单步操作、刷新。本机 `set.ini` 已确认快捷键 `startCollecting=F1`、`stopCollecting=F2`；优先用 `sky.press_key` 向唯一窗口发送 F1 启动，再立即通过 COM26 发命令。若屏幕抓取超时且控件无名称，不猜按钮索引或坐标；以应用日志确认采集已开始。

YP001 GR5526 UART4 ↔ Air780EGH UART1 为 460800/8N1。对照 R21 两端时，CH0 接 GR AON_GPIO2/UART4_TX，CH1 接 CAT1 UART1_RXD/17 脚，共地。软件通道名称不能证明探头接线。正常上电信号约 3.3V，DL32 用 3.3V CMOS/1.6V 阈值、10MHz、10 秒、CH0/CH1、Stream。逻辑采集只证明数字跳变与解码；幅值、过冲和边沿质量仍需示波器。

## 快速执行

1. 核对 COM26 仍是 GR UART0（115200/8N1、DTR/RTS 关闭）及 CAT1 已上电；GR UART4 确认为 460800。先启动 DL32 采集，再经 COM26 发若干次只读 `cat_at AT+ANTSTATUS`，每次间隔约 0.5–1 秒。分别数 GR `[CAT1 TX] ok=1` 与 CAT1 `type=ACK op=STATUS ok=1`；发送成功不是端到端成功。
2. 只读 ATK 日志 `C:\Users\SamLi\AppData\Roaming\ALIENTEK\ATK-LogicView\log\*.log`，搜索 `开始采集`、`Hz:`、`Time:`、`使能通道`、`数据传输完成`。配置在同级 `set.ini`，`channelsSet` 与 `settingData` 可核对通道、采样率、阈值。
3. 临时缓存位于同级 `temp\memory\<session>`。`recovery.json` 记录采集时间；`<channel>\files.ini` 列出稀疏采样块。当前版本以每字节 8 个样本、最低位为先，`0xFF` 表示持续高。只读比较 CH0/CH1 相同时段的跳变；不修改、清理、移动仍由程序使用的缓存。软件版本或缓存格式变了，改用手册支持的 CSV/BIN 导出核对，不沿用旧解析。
4. R21 是 0Ω 串接件，比较两端主要用于排除断焊/探头问题，不应反复作为核心诊断。优先用 CAT 运行日志核对实收字节，再将 GR 已知发送内容与 DL32 在 CAT1 RX 引脚的采样对齐；异常时检查阈值、共地、发送边沿、负载与焊接。只有 CAT1→GR 回程异常时再检查 R85。

2026-10-13 同步采集复核：COM26 记录 20 次 TX 成功、8 次 ACK；10 秒采集窗内，CH1 解出 18 个 14 字节命令样式帧，仅 7 个严格等于 `AT+ANTSTATUS\r\n`，其他多有 bit0 清零错误；CH0 解出 8 个含 ACK 的帧，第 8 个的类型与时间对应待核。用户确认 CH1 位于 CAT1 第 17 脚 UART1_RXD；CH0 焊点未确认。后续重点为 CAT1 第 17 脚单点波形与 CAT 实收日志同步核对；1.6V 阈值和探头接触也需排查。CAT1 项目源码唯一入口为 `D:\CODEX\sos-card\Air780EGH`；不从旧 `cat_1` 输入代码。
第二轮 18:37 快速复核：18 次 GR TX 成功；10 秒窗口内 CH1（CAT1 第 17 脚）有 16 个 14 字节命令样式帧，仅 6 个严格正确；CH0 有 6 条正常 ACK 和 1 条 BAD_ARGS。CH1 7.717 秒错帧与 CH0 7.727 秒 BAD_ARGS 不能仅凭时间认定同一帧；CH0 焊点未确认。完整记录见 doc/2026-10-13_DL32逻辑分析仪_CAT1串口同步采集.md。
 19:38:53 真正同步采集：DL32 CH1（CAT1 17 脚）10MHz/460800 解出 22 条命令，11 条正确、11 条变形；变形文本与 CAT USB 日志逐字一致，例如 AT+ANTRTATUS、AT+ANTST@TTS、@T*@NTSTATUS。GR AON_GPIO2 空闲实测约 3.3V。CAT Lua 真实收错字节，但尚未区分 GR 输出错误与板级波形/输入门限；不能据此重刷或宣称 OTA 链路可用。证据见 doc/2026-10-13_DL32逻辑分析仪_CAT1串口同步采集.md。