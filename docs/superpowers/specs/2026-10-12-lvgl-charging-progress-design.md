# LVGL 充电进度条接入设计

日期：2026-10-12（北京时间）

## 目标

将 YP001 已验证的电池电量采样和充电状态接入 GUI Guider 生成的 LVGL 页面，在主页面和时间页显示动态黑白充电进度条。

## 方案

- 在 `screen_main` 与 `screen_time` 页面各增加一个 LVGL `lv_bar`。
- 进度条宽约 60 像素、高约 8 像素，放在顶部静态电池图标左侧，保留原电池图标。
- UI 层提供统一更新接口，接收 `known`、`percent`、`charging`。
- `battery_display_poll()` 继续负责采样：百分比只来自 `yp001_battery_estimate()`，充电状态只来自 `yp001_charger_display_status()` 及现有完成判断。
- 电池 ADC、充电 I2C、NTC 或充电故障时，进度条隐藏填充并显示未知状态；不把异常伪装成正常电量，不自动改变充电控制。
- 页面切换后由下一次 UI 更新重新绑定当前页面对象，避免旧页面对象继续显示。

## 文件范围

主工程和交付副本同步修改：

- `Src/user/gui/guider/gui_guider.h`
- `Src/user/gui/guider/setup_scr_screen_main.c`
- `Src/user/gui/guider/setup_scr_screen_time.c`
- `Src/user/gui/epaper_ui.c/.h` 或专用 UI 更新模块
- `Src/platform/bsp.c`
- 对应 `doc` 中文修改记录

保持不变：

- e-paper display driver 和 flush
- LVGL 库本体
- 充电 IC 控制策略
- Flash/scatter/download 配置

## 验证

- 两份 Keil_6 工程重新编译，确认 0 Error、0 Warning。
- 静态检查确认异常状态不会进入正常百分比路径。
- 实板仍需分别验证：电池供电、接入 5V、充电中、充满、ADC/I2C/NTC 异常，以及页面切换后的像素更新。
