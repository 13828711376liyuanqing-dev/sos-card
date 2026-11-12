# GR5526 Starter Kit 用户指南 V1.2：核对索引

来源：[指南首页](https://docs.goodix.com/zh/online/detail/starter_kit_manual_bl_b/V1.2/982222d55257af4b96067c81bc228364)。下述开关和连接器编号仅针对官方 GR5526 SK 板，不适用于未核实的自制板。

## 用户提供的 Rev C 原理图核对记录

来源：`GR5526-SK-BASIC-RevC (1).pdf`，图纸日期 2023-02-24，Rev C，共 5 张原理图（该 PDF 文件共 11 页，前部含封面/目录等页面）。下列网络按原理图第 2、3、5 张目视核对；这证明的是设计连接关系，不证明特定实物板的跳线/拨码当前位置、器件已装配或电源实测值。

- **调试路径（第 3 张，JLINK & UART）**：J5 是板载 J-Link/UART Type-C 口；U3 为 STM32F072C8 板载接口 MCU。外部 J4 标注 VTref、SWDIO、`#RES`、SWCLK、GND、SWO。接口 MCU 侧的 `SWDIO_OB`、`SWCLK_OB`、`RESET_OB` 经 U4（TXB0104 电平转换）对应至 GR5526 的 `SWDIO`、`SWCLK`、`CHIP_EN`/复位相关网络；SWO 为 NC。由此确认板载调试采用 SWD，而非依据口语“JTAG”推断为 JTAG 接口。
- **备用串口（第 3 张）**：J29 是另一 Type-C 口，连 CP2102 USB-UART；CP2102 的 UART 信号为 `UART0_RX`/`UART0_TX` 网络。它与 J5 的板载 J-Link USB 不是同一个接口。J5 同时引出 USB D+/D−至板载 STM32，不能仅凭“J-Link & UART”标题就断言 J5 的虚拟 COM 一定接到 GR5526 的应用日志 UART；仍须结合手册描述、拨码设置及当前固件 UART 配置核对。
- **目标供电/复位（第 2、5 张）**：第 5 张 S10 是电源选择/开关，图纸备注为 “Down: 5V from Jlink; Up: OFF”，相关网络包含 `BATT_IN`、`VBAT`、`+5V`、`BAL_PWR`；S11 在 `VCC`（来自外设 3.3V LDO）与 `Li-BAT` 之间选择 GR5526 供电。第 2 张 S1 选择 `VDD_IN`、`VIO_OUT` 或 `VCC3P3V` 相关供电/测试路径；S9 为 `CHIP_EN` 复位按键。外接供电、跳帽及测试点操作前，按实物丝印和测量确认，不能只照搬图纸网络名。
- **芯片和外设（第 2、4 张）**：图纸 U1 标为 GR5526VGBIP；包括 32 MHz 晶振、32.768 kHz RTC 晶振、外部 Flash U9（P25Q128L）、PSRAM U10（APS6404L）、音频/麦克风和显示/按键接口。图纸标出的 GPIO 复用及焊接选件只作为该 Rev C 设计参考，不能自动套用到其它板卡变体。
- **与 V1.2 用户指南的关系**：上文关于 S3 的 J-Link/UART 模式、J5/J29 的用途和默认 CDC GPIO 来自官方 Starter Kit V1.2 用户指南；用户提供的这份 Rev C 原理图为 5 张板级图纸，并未出现 S3。若实物开关命名/配置与指南不一致，以实物板版本、丝印和对应版本资料为准，并记录差异；不要把手册的 S3 位置写成原理图已证明。

### J-Link 显示 `No Cortex-M SW Device Found` 时

先分别确认主机是否识别 J-Link OB、目标侧 SWD 是否连通；枚举到调试器不等于 MCU 已被识别。按 Rev C 原理图依次核对：目标板电源路径（S10/S11 等）和 GR5526 实际供电、J5/J-Link OB 路径、SWDIO/SWCLK 通路与电平转换器 U4、复位/`CHIP_EN` 路径、地线，以及实物板卡修订。然后参考 V1.2 用户指南核对对应版本的接口开关配置，并尝试在复位状态下连接。每次只改一个可观测因素并记录结果；不要因该报错就改 Flash 算法、擦除范围或固件映像，也不要把 SWD 故障叫作 HEX 编译问题。未连接真机时不得声称硬件排查已验证。

- [快速入门](https://docs.goodix.com/zh/online/detail/starter_kit_manual_bl_b/V1.2/746a7cd95dc3126e21367e303b4f507b)：官方 SK 的板载 J-Link 路径使用 `JLINK_USB J5`，S3 的 1–2、5–6 置 ON 以连接 UART/SWD；USB 供电示例把 S11 置 VCC、S10 置 ON。UART/GProgrammer 路径使用 `UART_USB J29`，S3 3–4 置 ON，并保持 1–2 不置 ON。两条路径择一，不混用拨码配置。示例运行后复位，再用 GRToolbox 做 BLE 扫描/连接测试。
- [接口 MCU](https://docs.goodix.com/zh/online/detail/starter_kit_manual_bl_b/V1.2/930badfbfe29e2141a699b97703fa27c)：SK 板载 STM32F 接口 MCU 提供 J-Link OB 与 CDC 虚拟串口。其默认 CDC UART 对应 GR5526 TX=GPIO4、RX=GPIO5；手册限制 CDC 速率不超过 1 MHz，J29 UART_USB 路径可到 3 MHz。
- [电源供电](https://docs.goodix.com/zh/online/detail/starter_kit_manual_bl_b/V1.2/22f719035c1f8e0d3d538d782a3eaee2)：S11 选择 VCC（USB）或 Li-BAT；不同供电路径和电压取决于开发板电路，外接模块前核对实测电压。

术语：官方 SK 主要使用 J-Link 的 **SWD** 连接目标芯片；用户口语所说“JTAG 调试”须落到实际接线和 Keil Debug 配置上核实。
