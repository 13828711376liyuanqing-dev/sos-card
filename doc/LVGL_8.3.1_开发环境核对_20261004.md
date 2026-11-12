# GR5526 / LVGL 8.3.1 开发环境核对（2026-10-04）

## 工程与版本

- 主工程：`ble_app_uart_c/Keil_6/YP001_GR5526.uvprojx`，Target `YP001_GR5526_AC6`。
- 交付副本：`SVN交付_YP001_GR5526_20261001/ble_app_uart_c/Keil_6/YP001_GR5526.uvprojx`。
- 两个工程均自带 LVGL 8.3.1 源码；版本宏为 8.3.1。汇顶 SDK 还提供 `graphics_lvgl_v831_lib.lib`。
- 本机 Keil MDK 位于 `C:/Keil_v5`，Arm Compiler 为 6.14；J-Link 位于 `C:/Program Files/SEGGER/JLink`。GCC 工具链路径见 `doc/工具链目录说明.md`。

## 本轮处理

- 未修改固件源码或 Keil 配置；保留 LCD 和下载基线。环境所需组件已经存在，无须重复安装。
- 两份工程的 `验证Keil6交付.ps1` 均通过，已核对 scatter、SDK 库、Flash 算法及下载参数。
- 主工程重新编译：`doc/lvgl_env_build_20261004.log`，Arm Compiler 6.14，0 错误、0 警告；生成新的 AXF/HEX。
- 交付副本独立重新编译：`doc/lvgl_env_delivery_build_20261004.log`，Arm Compiler 6.14，0 错误、0 警告；生成新的 AXF/HEX。

## 使用入口及验证边界

在 Keil 打开主工程，选择 `YP001_GR5526_AC6` 后执行 Build。交付时应在交付副本目录中独立 Build。修改源码后旧 AXF/HEX 不代表新源码，须重新编译。

本轮仅验证本机开发环境和编译。未下载到设备；屏幕显示、BLE、电子纸刷新及其他实板功能仍需实板验证。
