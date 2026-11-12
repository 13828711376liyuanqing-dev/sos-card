---
name: goodix-gr5526-development
description: Use when analyzing, configuring, building, downloading, or debugging Goodix GR5526 SDK firmware or a GR5526 Starter Kit, especially Keil/GCC, Flash layout, NVDS, J-Link/SWD, UART, or custom-board bring-up.
---

# Goodix GR5526 开发与板卡核对

以 Goodix 两份 V1.2 官方指南为参考，先确认实际芯片型号、SDK 版本和板卡原理图，再应用指南中的配置。本文是核对规则，不代表已验证当前固件或真机。

## 选择依据

- 软件、Bootloader、Flash/NVDS、Keil 构建与调试：查 [开发者指南摘录](references/developer-guide.md) 及其原始页面。
- Starter Kit 的供电、接口、拨码与连接：查 [Starter Kit 摘录](references/starter-kit.md)、对应版本的官方手册和原理图证据。已记录用户提供的 GR5526-SK-BASIC Rev C 原理图；图纸网络仅证明设计连接，不证明实物开关状态/器件装配/实测供电。区分 Rev C 图纸未出现的 S3 手册配置与图纸明确的 S10/S11、J5/J29、板载 SWD 路径；先核对实物板修订和丝印。

## 工作核对

1. 固件布局：从 `custom_config.h`、链接脚本/scatter、map、HEX 核对芯片版本、应用加载/运行地址、`BUILD_IN_APP_INFO`、SCA、NVDS；不要从 HEX 文本文件大小推断功能完整性。
2. 构建：核对真实编译器、源文件清单、宏、芯片库、启动文件、链接脚本及 AXF/ELF 与 HEX 的对应关系。编译成功只是静态证据；GCC 与 Arm Compiler 6 可生成不同大小和字节内容。
3. 下载/调试：先确认实际板卡的 SWD/UART 连接、供电、Flash 算法和擦除范围。Keil 的调试对象须与所测试固件同一构建。下载、擦除、烧录和连接设备只在用户明确授权后执行。
4. 真机验收：按用户目标检查复位启动、BLE 连接/业务、UART 日志、CLI、低功耗以及持久化数据。静态/主机证据与真机证据分开报告。

若官方 V1.2 指南与当前 SDK、芯片变体或硬件原理图不一致，先列出差异并以可核实的当前硬件/SDK证据决定，不机械套用指南示例。
