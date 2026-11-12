# LVGL 充电进度条接入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将真实电池电量和充电状态接入 GUI Guider 的主页面与时间页动态进度条。

**Architecture:** 在两个生成页面增加 `lv_bar` 对象；`epaper_ui` 保存当前页面对象并提供统一更新接口；`battery_display_poll()` 在现有采样周期内将已验证的 `battery_known/percent/charging` 传给 UI。主工程修改后以交付同步工具同步到交付副本。

**Tech Stack:** GR5526、Keil 6/Arm Compiler 6、LVGL 8.3.1、GUI Guider 生成 C、DEPG0150 1bpp e-paper。

## Global Constraints

- 保持 LVGL 8.3.1、1bpp 配置、24 KB 内存池。
- 保持 e-paper display driver 和 flush 不变。
- 百分比只来自 `yp001_battery_estimate()`；充电状态只来自 `yp001_charger_display_status()` 与现有完成判断。
- ADC/I2C/NTC/充电故障时不得显示为正常电量或正在充电。
- 主工程 `ble_app_uart_c` 与交付副本必须同步，先检查交付副本独立差异。
- 每个代码改动附近加入北京时间、SAM、修改内容和原因注释。
- 在 `doc` 维护中文修改说明并填写强制检查项；不自动提交 Git。

---

### Task 1: Add progress bar objects to the two GUI Guider pages

**Files:**
- Modify: `ble_app_uart_c/Src/user/gui/guider/gui_guider.h`
- Modify: `ble_app_uart_c/Src/user/gui/guider/setup_scr_screen_main.c`
- Modify: `ble_app_uart_c/Src/user/gui/guider/setup_scr_screen_time.c`
- Test: `tools/test_guider_ui.py` and existing host UI executable

**Interfaces:**
- Produces `lv_ui.screen_main_bar_battery` and `lv_ui.screen_time_bar_battery`.

- [ ] **Step 1: Add object members**

Add two `lv_obj_t *` members next to the existing battery image members in `lv_ui`.

- [ ] **Step 2: Create bars in each page**

Create `lv_bar` objects at `(105, 9)` with size `60x8`, range `0..100`, default value `0`, black indicator and white background, with a nearby SAM timestamp comment. Keep the existing 20x10 battery image unchanged.

- [ ] **Step 3: Run host UI build before integration**

Run: `C:\Users\SamLi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tools/test_guider_ui.py`

Expected: existing host build/run remains successful; any new compile error is fixed before proceeding.

### Task 2: Bind the active page to real battery data

**Files:**
- Modify: `ble_app_uart_c/Src/user/gui/epaper_ui.h`
- Modify: `ble_app_uart_c/Src/user/gui/epaper_ui.c`
- Modify: `ble_app_uart_c/Src/platform/bsp.c`
- Test: `tools/test_battery_display.py` plus static assertions

**Interfaces:**
- Add `bool epaper_ui_set_battery(uint8_t percent, bool known, bool charging);`.
- The function updates only the active `screen_main` or `screen_time` bar and returns false when no matching active page exists.

- [ ] **Step 1: Add a failing source-contract test**

Extend `tools/test_battery_display.py` with checks for the new API, both bar members, and the `battery_known` guard around the update call. Run it and confirm it fails before implementation.

- [ ] **Step 2: Implement the UI API**

Implement `epaper_ui_set_battery()` in `epaper_ui.c`: select `s_ui.screen_main_bar_battery` or `s_ui.screen_time_bar_battery` according to `s_loaded`; set `lv_bar_set_value(bar, known ? percent : 0, LV_ANIM_OFF)`; hide the indicator when unknown and restore it when known; invalidate the bar. Do not touch pages outside the selected two.

- [ ] **Step 3: Feed verified sample data**

In `battery_display_poll()`, derive `charging` only when `charge_known`, `soc_known`, no fault bits, input is present, and the existing state resolves to `CHARGING`; call `epaper_ui_set_battery(home.battery_percent, home.battery_known, charging)` after `epaper_ui_update()` and before refresh.

- [ ] **Step 4: Run the source-contract test**

Run: `C:\Users\SamLi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest tools.test_battery_display -v`

Expected: PASS, with invalid battery paths still guarded.

### Task 3: Synchronize the delivery copy and document the change

**Files:**
- Modify: `SVN交付_YP001_GR5526_20261001/ble_app_uart_c/Src/user/gui/guider/gui_guider.h`
- Modify: corresponding generated page/UI/BSP files
- Create: `doc/YP001_LVGL充电进度条接入_20261012.md`

- [ ] **Step 1: Inspect delivery differences**

Compare each target file with `Compare-Object`; stop and resolve any delivery-only edit before synchronization.

- [ ] **Step 2: Preview and run the delivery sync tool**

Run `D:\CODEX\sos-card\YP001_交付同步工具\Invoke-YP001Delivery.ps1` in preview mode, review only expected `ADD/UPDATE`, then run its normal synchronization mode.

- [ ] **Step 3: Write the Chinese modification record**

Record files/functions, before/after behavior, reason, source-contract results, both Keil build results, and explicitly list pending real-board checks: battery supply, 5 V input, charging, charge complete, ADC/I2C/NTC faults, and pixel refresh after page switching. Copy every row from `doc/YP001_代码修改强制检查项.md` and fill evidence.

### Task 4: Build both Keil projects and verify

**Files:**
- Build: `ble_app_uart_c/Keil_6/YP001_GR5526.uvprojx`
- Build: `SVN交付_YP001_GR5526_20261001/ble_app_uart_c/Keil_6/YP001_GR5526.uvprojx`

- [ ] **Step 1: Run the existing Keil 6 build workflow for the main project**

Capture a fresh log and require `0 Error(s), 0 Warning(s)` plus a newly timestamped AXF/HEX.

- [ ] **Step 2: Run the same workflow for the delivery project**

Capture a separate fresh log and require the same result.

- [ ] **Step 3: Run final static checks**

Run `rg -n "epaper_ui_set_battery|screen_main_bar_battery|screen_time_bar_battery|battery_known"` across both trees and rerun `tools/test_battery_display.py`.

- [ ] **Step 4: Report evidence boundaries**

Report build and host evidence separately from device evidence. Do not claim real-board charging or visible pixels until the user tests the hardware.
