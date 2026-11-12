---
name: atk-c2-meter
description: Use when reading or recording voltage and current from the local Alientek ATK C2 USB meter on Windows, including YP001 sleep-current debugging, live monitoring, or opening the C2 measurement interface.
---

# ATK C2 电流电压读取

本机工具位于 `D:\CODEX\sos-card\tools\c2_meter`，依赖现有 Python 3 与 WinUSB 驱动。设备 VID/PID 为 `2E88:C2C2`，当前已验证序列号为 `C20000C2`。

## 调用

用户要求读取当前电流、电压时，执行单次命令，并将返回的 V、mA、时间及错误情况如实反馈。

```powershell
python D:\CODEX\sos-card\tools\c2_meter\c2_meter.py read
```

需要关联休眠/唤醒过程时，按用户要求的窗口采集。未指定时可先采集 10 秒。输出路径每轮用唯一名称，父目录需存在。

```powershell
python D:\CODEX\sos-card\tools\c2_meter\c2_meter.py record --seconds 10 --output D:\CODEX\sos-card\logs\c2_<本轮唯一时间>.jsonl
```

要 CSV 时加 `--format csv`，并使用 `.csv` 扩展名。命令默认超时为 2000 ms，`--timeout-ms` 可调整。`list` 返回设备路径，多台连接时用 `--device` 指定本轮测量设备。

需要图形界面时运行以下命令，`--start` 会随窗口打开开始采集。手动启动也可双击 `D:\CODEX\sos-card\tools\c2_meter\启动C2采集.cmd`。

```powershell
pythonw D:\CODEX\sos-card\tools\c2_meter\c2_meter_gui.py --start
```

界面数字与曲线先使用约 100 ms 窗口均值，再采用时间常数默认 1 秒的指数移动平均。用户可切换关闭、0.5 秒、1 秒、2 秒。关闭时显示窗口均值。CSV 自动存入 `D:\CODEX\sos-card\logs\c2_meter`，记录全部接收的原始样本。

## 数据与判断

- `voltage_v` 为 V，`current_a` 为 A，`current_ma` 为 mA，`power_w` 是对应电压、电流的乘积。量程读数与接线位置有关，结合当前接线记录解释 USB 输入侧或电池侧的电流。
- `timestamp_utc` 是主机接收时间，北京时间加 8 小时。每个 USB 帧有四个样本，`sample_index` 为帧内序号。一批样本共享主机时间，设备端精确时刻尚未取得。
- 图形界面平滑显示适合观察稳定值，瞬态分析读取 CSV 原始样本。长期窗口可计算最低值、平均值、峰值和稳定段，并说明窗口及统计方法。
- 工具 stdout 为 JSON/JSONL 或 CSV，错误 JSON 在 stderr。退出码 0 表示成功、1 表示错误、130 表示中断。失败时沿用错误结果，重新取得有效样本后再报告当前读数。

## 连接处理

工具独占 USB。运行 CLI 前先停止 GUI 采集并等到显示已停止，或关闭 GUI。官方 ATK-C 同样需要先释放连接。用户正在采集时，优先使用该轮日志，避免另开读取者。

找不到设备时先执行 `list`。读取超时可在确认其它程序已经释放设备后重新打开一次。USB 重插/重新上电后的首轮独立读取仍待验证，若持续超时，可请用户通过官方 ATK-C 正常采集一次并退出，再重试工具。当前尚未取得自动初始化这一状态的命令。

工具仅提供测量读取能力。固件下载、复位、供电变更和睡眠命令按各自任务的授权执行。当前帧校验覆盖长度、帧头和帧尾，完整校验算法尚未确认。读取成功的证据范围为 C2 数据接收，产品深睡验收还需对应状态与测量窗口证据。

完整协议边界和实测记录见 `D:\CODEX\sos-card\doc\2026-11-13_C2电流电压AI读取工具.md`。
