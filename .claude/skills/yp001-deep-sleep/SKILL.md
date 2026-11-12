---
name: yp001-deep-sleep
description: YP001 GR5526 deep (ultra) sleep for current measurement — how to enter it from the COM30 debug serial (`sleep_test ...`) or from the BLE factory tool (`sleep_test enter force`), what stays powered (G-sensor GPIO7/1.8V GPIO9) and what is switched off (CAT1/EPD/LED/UART4), wake sources (KEY1/KEY2/G-sensor motion, ~407 s rescue, wake = reboot), refusals, log reading and current-measurement caveats (R82, USB 4 mA). Serial path board-verified 2026-10-16..20. Use when the user asks about 深度睡眠/深睡/睡眠电流/测功耗/sleep_test/进入低功耗/G-sensor 唤醒, or wants a sleep entry added to a tool.
---
# YP001 深度睡眠（测电流）

SAM | 2026-11-12 +08:00

完整交接说明见 `doc/2026-10-20_深度睡眠接口与代码交接说明.md`（第 10 节是 11-12 补充）；调试过程见同日的复盘、供电和预复位取证文档。

**用户的硬要求：G-sensor 不能关**，供电和运动中断都要保留，按键和 G-sensor 都必须能唤醒。

## 1. 怎么进入

| 途径 | 命令 | 说明 |
|---|---|---|
| 调试串口 COM30（115200 8N1，CRLF，DTR/RTS 关） | `sleep_test enter low long` | 推荐的串口用法，带业务门禁 |
| 同上 | `sleep_test enter force` | 工厂用：自动取消 CAT1 保电，不检查报警、找人、通话 |
| 蓝牙工厂工具 0.2.5（`tools/ble_console/nordic`） | 低功耗测试 → 进入深度睡眠（测电流） | 发送的就是 `sleep_test enter force`，免授权、无确认框 |
| 查询 | `sleep_test status` | 只读；蓝牙工具里叫"查询睡眠状态" |

其他模式（只供串口诊断用）：
- `keys long`：只有两键能唤醒，G-sensor 供电保留；
- `motion long`：只有运动能唤醒；
- `high long`：高有效极性对照；
- 不加 `long`：救援时间按 60 秒请求。

`sleep_test enter long` 不是合法写法，`long` 前面必须有模式名。

## 2. 进入后的状态

- **关闭**：LED（低有效，输出高）、LCD 接口和电源、CAT1 受控电源；UART4 置为输入隔离；调试串口 UART0 暂停。
- **保留**：G-sensor 供电 GPIO7（进入前会核对 DATAOUT、OUTEN、MUX 和睡眠 PAD）、1.8V GPIO9、G-sensor 运动中断（AON7，下降沿；参数为阈值 08、持续时间 03、推挽低有效）。
- **唤醒源**：唤醒掩码 92 = KEY1 + KEY2 + GS_INT。救援时间请求 300 秒，实际约 **407 秒**。
- **唤醒都会让整机重启**：串口重新打印 BOOT 和 `[ULTRA PRE-RESET]`，蓝牙重新广播。
- 深睡期间蓝牙整体断电，扫描搜不到，串口也不响应。这都是预期现象，说明真的睡下去了。

## 3. 会拒绝进入的情况

- 普通 `enter`：已在测试中、运输锁、OTA 不允许电源改变、CAT1 厂测保电、报警、找人、通话、按键按住。打印 `refused: busy/locked/key held`。
- `force`：只在已在测试中、运输锁、OTA、按键按住时拒绝。打印 `force refused: OTA/ship lock/key held`。
- 准备阶段还可能放弃（打印 `entry_failed` 或 `[SLEEP TEST] exit=`），原因可能是：G-sensor 在 2 秒内没能稳定 500ms、busy 或 extra 外设状态、UART 被占用、唤醒掩码读回不符。

## 4. 测电流的注意事项

- 2026-10 的 USB 5V 整机约 4mA，是在**拆掉 R82** 的板子上测的单点读数（拆 R82 是为了断开 USB 经 Q10 强制给 CAT1 供电的路径）。没拆 R82 的板子，CAT1 可能关不掉，电流会偏高，不能直接拿来比。
- ETA69631 的 USB 降压本身就有毫安级消耗；USB 供电时的读数不等于电池待机电流，电池侧要单独测。
- 普通睡眠不能用运输断电（BATFET），否则按键和运动唤醒就没有电源了。
- 测试时桌面不要震动，否则可能把卡片晃醒。执行命令时不要按着按键。

## 5. 改代码的边界

- 入口是 `bsp.c` 的 `cmd_sleep_test`；真实入睡在 `QV_onIdle` 里，先跑 `sleep_test_prepare`，再调 `pwr_mgmt_ultra_sleep`。不要在中断或 QP 事件里直接调用 SDK 的睡眠函数，也不要绕过 prepare。
- 新增入口（比如工具按钮）只加命令分支和白名单：
  - 白名单在 `user/factory/yp001_factory_protocol.h`，同时补 `tools/factory_final/tests/test_factory_protocol.c`；
  - 免授权在 `yp001_factory_ble.c`，与 `charger ship start` 同一行处理。
- 改 G-sensor 参数会影响其他诊断命令（`gsensor_sleep_motion_arm` 是共用的）。改极性必须两头一起改：传感器配置和 GPIOTE 边沿。
- 改动要同步 `D:\CODEX\sos-card` 和 `D:\123\YP01`（`D:\SVN` 的工厂协议是旧版）。改之前先备份到 `D:\CODEX\_archive`。

## 6. 验收状态（2026-11-12）

- 串口进入、G-sensor 保留、按键和运动唤醒、预复位取证：已在实板验证（10-16 至 10-20）。用户明确说过不要让他重复做已经测过的动作。
- `force` 入口和蓝牙工具入口：代码和主机测试已完成，**实板未验证**。
- 待确认：蓝牙连着的时候，busy 检查会不会让 prepare 放弃进入。如果会，工具改成发完命令后主动断开蓝牙。
