# DesktopTests 双击窗口修正（2026-10-10）

修改文件：`tools/cat1_antenna/tests/DesktopTests.cs` 的 `Main`、`Check`、`Run`；`tools/cat1_antenna/build.ps1` 的测试调用。

修改前：双击 `DesktopTests.exe` 时，测试完成后窗口立即关闭；断言失败会直接退出，用户来不及看结果。修改后：手动双击运行会显示 PASS 或错误信息，并等待按键关闭；构建脚本使用 `--no-pause`，保持自动测试退出码。原因是让本地测试结果可见，同时不阻塞构建。

验证：2026-10-10 20:15 +08:00 重新运行 `tools/cat1_antenna/build.ps1`，39 项断言通过，生成新 `bin/DesktopTests.exe`；使用 `--no-pause` 单独运行退出码 0；加载 Lua 协议夹具运行 56 项断言通过，退出码 0。新 EXE SHA256：`31B78E2D4A1E0C6F55189B9A2E20C54D3341953EBF3E41DE955F45936F30A3C9`。双击交互停留尚待现场用户验证。

`DesktopTests.exe` 仅为主机协议测试，不连接实板。`CAT1Antenna.exe` 的状态查询超时与停止回执问题仍需独立现场日志和串口验证。本轮不修改汇顶或 Air780EGH 固件，原有 AXF/HEX 不作为本轮上位机验证证据。

| 检查项 | 结果/证据 |
|---|---|
| 修改前工作区和目标文件检查 | 已查看工作区状态及测试源、构建脚本、停止状态机与现场会话日志；保留既有改动。 |
| 主工程/交付副本差异检查 | 本轮仅改 `tools/cat1_antenna`，不改两份固件工程；固件同步项不适用。 |
| 代码时间/修改人/原因注释 | 双击修正标 `SAM | 2026-10-10 20:14 +08:00`；停止修正标 `SAM | 2026-10-10 20:19 +08:00`。 |
| 本轮中文修改说明 | 本文件。 |
| 主工程 Keil 6 编译 | 本轮未修改汇顶源码，不适用；未据旧 AXF/HEX 声称新固件已编译。 |
| 交付工程 Keil 6 编译 | 本轮未修改交付固件源码，不适用。 |
| 实板测试及未完成项目 | 本轮只读取现场日志；双击停留、新版 GUI STOP ACK、启动无 ACK 的通讯原因仍待现场验证。 |
| 清理脚本与 AXF/HEX | 未改动清理脚本或固件产物。 |

## 20:19 后续：停止按钮被状态机拦截

现场截图显示“请等待当前 ACK”；对应会话 `raw.log` 只有 `AT+ANTSTART=ALL,2` 发出，没有天线协议 ACK，也没有 STOP TX。问题在 `tools/cat1_antenna/Protocol.cs` 的 `Session.Request`：等待 START/STATUS 或命令超时后，STOP 被本地拒绝，设备从未收到停止请求。

修改 `Session.Request`：STOP 可以覆盖正在等待的 START/STATUS ACK，也可在超时后下发；START 的旧 ACK 不得覆盖等待 STOP 的状态。修改 `Session.Accept`：只有收到有效 STOP ACK 才显示“已停止”并清除超时锁；STOP 再次超时显示“停止未确认”。`tests/DesktopTests.cs` 增加这些回归断言，`tools/cat1_antenna/README.md` 更新操作说明。未修改汇顶或 Air780EGH 固件，两份 Keil 编译和固件同步不适用。

验证：重新编译 DesktopTests 后 44 项通过；加载 Lua 夹具共 61 项通过。旧 `bin/CAT1Antenna.exe` 正被现场窗口占用，构建器报 CS0016 无法覆盖；已将同一源码编译为 `bin/CAT1Antenna_停止修复.exe`，编译退出码 0，SHA256 `E8E0B82D21DFEA84F6996521A287FE9C39901926326F16B3EEB3C1DBDE6ADB24`。新 GUI 尚未在实板完成 STOP ACK 验收；需关闭旧窗口、释放 COM26 后用新版测试。`AT+ANTSTART` 无 ACK 的通讯原因仍未定位，不能以本地主机测试代替实板结果。旧版 EXE 仍保留，未强制关闭用户进程。
