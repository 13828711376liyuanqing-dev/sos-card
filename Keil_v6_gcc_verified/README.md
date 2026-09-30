# ble_app_uart_c — Keil Arm Compiler 6 独立工程

本工程使用 Keil MDK 中的 Arm Compiler 6.14（AC6）独立编译、链接和生成固件，不再在 Build 前调用 GCC。安装目录 `C:\Keil_v5` 是 MDK 的目录名，不代表本工程使用 ARMCC5。

## 使用

1. 用 Keil 打开 `ble_app_uart_c_v6.uvprojx`，确认编译器为 Arm Compiler 6。
2. 在工程树中编辑共享源码 `..\ble_app_uart_c\Src`；GCC 工程也使用这份源码，无须分别修改两套代码。
3. 选择 Rebuild。Keil 固件为 `Objects\ble_app_uart_c_ac6.hex`，调试符号为 `Objects\ble_app_uart_c_ac6.axf`，映射文件为 `Listings\ble_app_uart_c_ac6.map`。
4. 需用 J-Link/JTAG 调试时，工程的 `ac6_debug.ini` 加载当前 AC6 AXF。连接、下载和断点功能仍须真机验证。

GCC 对照基线仍位于 `..\ble_app_uart_c\GCC\out\ble_app_uart_c.hex` 和 `..\ble_app_uart_c\GCC\out\lst\ble_app_uart_c.elf`。`Objects\ble_app_uart_c.hex` 是此前遗留的 GCC 副本，**不是**本工程的新 AC6 输出；不要混用。两种编译器生成的 HEX 不要求逐字节相同，用户须分别在同一硬件上验证启动、BLE、UART、CLI、低功耗及调试行为。尚未进行真机烧录或功能验证，AC6 HEX 不应直接替代已验证的 GCC 量产固件。

工程使用 `..\SDK\platform\soc\linker\keil\flash_scatter_common.sct`，应用信息固定在 `0x00202200`。构建时头文件 `custom_config.h` 会检查该地址与 `APP_CODE_RUN_ADDR + 0x200` 一致。CLI 命令段使用 Keil scatter 的 `ER_CLI_CMDS` 边界；GCC 仍使用自身链接脚本的 `__cli_cmds_start/end`。

## 编译警告

Keil AC6 使用常规警告档位并显式启用 `-Wall`。原“全部扩展诊断”档位会把 SDK 头文件中的结构体填充、符号转换和未用参数等提示在每个编译单元反复输出，完整构建达 4557 条。调整后完整 Rebuild 为 0 错误、0 警告，AC6 HEX 的 SHA-256 与调整前相同；这次仅改了 Keil 编译诊断配置，没有改变固件内容。若要专项审查第三方 SDK，可临时启用更严格诊断，但不建议把海量提示作为日常构建输出。

## 官方参考

[Goodix 开发指南](https://docs.goodix.com/zh/online/detail/developer_guide_bl_b/V1.2/c69307e0f4a49b276ff9f1e9051d80d9)
