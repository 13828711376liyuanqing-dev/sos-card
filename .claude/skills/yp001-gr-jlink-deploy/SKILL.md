---
name: yp001-gr-jlink-deploy
description: Deploy a freshly compiled YP001 GR5526 application to the bench board through J-Link, end to end, and bring CAT1 back up afterward. Covers acceptance of the Keil build, signing, pairing the Boot (baseline descriptor + live R6 PREPARED scope), read-only snapshots, Keil command-line download, the one SYSRESETREQ, 1 MiB readback acceptance, GR/CAT1 startup confirmation and the authorized J-Link CAT1 PWRKEY pulse. Use when the user asks to download/flash/烧录/下载 GR firmware, deploy a new GR build, or power on/open CAT1 after a GR reflash.
---

# YP001 GR5526 J-Link 下载与 CAT1 开机

SAM | 2026-10-28 +08:00 | 由 2026-10-28 运动采样修复的实际部署整理（`doc/2026-10-28_台架OTA忽略普通运动修改.md`、`logs/motion_sampling_delivery_20261028/`）。本技能记录已实测可行的流程；**不授权**任何未经用户当次明确同意的写 Flash、复位或 CAT1 开机。

## 何时使用 / 前提

- 用户已在唯一工程 `ble_app_uart_c/Keil_6/YP001_GR5526.uvprojx` 编译成功（2026-10-28 由 `YP001_BASELINE_UART_RECOVERY_20261025.uvprojx` 原样改名而来，其余旧工程已归档到 `archive/keil6_cleanup_20261028/`；输出目录仍为 `firmware_releases/gr_uart_recovery_20261025/baseline/Objects`），并**明确要求由我下载**。AGENTS.md 默认 GR 下载由用户手动，必须有当次授权。
- 板上当前跑的是上一次成套交付（`firmware_releases/<上次>/baseline/baseline_signed.bin` + `boot/BOOT_BOUND.bin`），Boot 日志最新为干净的 PREPARED 记录（R6 维护范围）。不满足就停下报告。
- 工具：J-Link V9（S/N 69407663，SWD，设备名 `CORTEX-M4`）；GR CLI = **COM26** 115200；CAT1 开机后出现 COM21/22/23。Python：签名配对用 **3.11**（含 `cryptography`），其它用 3.12。

**绝不能直接烧 Keil 产出的 `YP001_GR5526.hex`**：它未签名，Boot 的基线描述符与 R6 PREPARED 绑定不匹配，可能拒绝启动。必须走下面的签名+配对成套下载。

脚本都在 `.claude/skills/yp001-gr-jlink-deploy/scripts/`（下称 `$S`）。每轮新建 `logs/<round>/` 存全部证据。

## 本地工具（2026-10-29，优先使用，省 token）

`tools/gr_release/gr_build_tool.py`（或双击 `gr_build_tool.bat`）把下面第 1–7 步串成命令：`check`（只读验收编译）、`sign --format hex|bin|both`（任何版本，OTA 用签名包）、`prepare`（仅 1.0.2/b3 基线：快照×2、改动确认、签名配对、导出 `FLASH/APP_SIGNED_*`、`FLASH/BOOT_PAIRED.*`）、`flash <目录>`（输入 FLASH 确认后下载、复位、读回、读 GR 版本）、`auto`。CAT1 开机仍按第 7 步手动。check/sign 已实测；prepare/flash 待下一次基线交付实测。说明见 `doc/2026-10-29_GR编译后本地烧写工具.md`。

## 步骤

### 1. 接受编译产物（只读）
- 看 `Objects/YP001_GR5526.build_log.htm`：`0 Error(s), 0 Warning(s)`；如实记录编译单元数和耗时。2026-10-28 起增量编译已恢复（根因：输出目录绝对路径使 AC6 `.d` 首行带盘符冒号，µVision 解析失败；已改为相对路径 `..\..\firmware_releases\gr_uart_recovery_20261025\baseline\Objects\`，`.dep` 含约 3 万条 `I (` 头文件依赖）。若再次出现每次全编，先查 `.dep` 的 `I (` 行数与 `.d` 首行是否又变成绝对路径。
- 全编时 HEX 每次都不同：`user_periph_setup.c` 开机信息嵌入 `__DATE__ __TIME__`。同源码不同 HEX 属正常，不代表功能变化。
- 列出相对上次交付变化的源码（第 3 步脚本会强制校验；只有经审核的文件可用 `--allow` 放行）。

### 2. 下载前确认设备与只读快照
- 红线：先确认 GR 正常运行、CAT1 已供电并实际启动（`$S/gr_cli.ps1 -Commands fw_version,'business status'`；`cat_at FOTA_STATUS` 等 8 s 取 `[CAT1 RX]` 真实回应）。
- `$S/jlink.ps1 -Action Snapshot -Out logs/<round>/pre_flash_1.bin`，过几分钟再拍 `pre_flash_2.bin`，两次逐页比较必须一致（owner 页 0x2F9000–0x2FAFFF 不得在变）。DHCSR S_HALT 须为 0。
- 可用 `tools/ota/inspect_gr_flash_snapshot.py` 查看：A/Boot 是否等于上次交付、最新 PREPARED 代数、owner/候选哈希。

### 3. 签名与 Boot 配对（只在电脑上）
```
python3.11 $S/prepare_delivery.py --previous firmware_releases/<上次> --out firmware_releases/<本次> \
  --audit logs/<round> --frozen firmware_releases/<上次>/frozen_inputs.json \
  --snapshot logs/<round>/pre_flash_2.bin --allow <改动源文件> ...
```
（10-28 之前的交付没有 `frozen_inputs.json`，当时用的是 `logs/r6_query_readonly_20261027/frozen_inputs.json`。）
脚本做的事：核对编译新鲜度与输入集合 → 调用 `tools/ota/pair_gr_adc_resync_build.py` 签名（`GrBaselineSign_current.exe`，测试密钥）并生成两个“只下载”Keil 工程 → 改写 Boot 40 B 基线描述符 + 148 B R6 范围数据（代数 G→G+1，owner/候选取自实时快照）→ 逐字节确认 Boot 代码未变 → 写本次 `frozen_inputs.json` 供下一轮。
任何断言失败（尤其 `owner pages changed`、`not a clean PREPARED`）都**停下报告**：owner 哈希不对时 Boot 会拒绝启动。

### 4. 下载（写 Flash，需当次授权）
- 提醒用户下载期间不要在 Keil 里编译/下载/调试。
- 依次：
```
UV4.exe -f "<本次>\baseline\SIGNED_DOWNLOAD\DOWNLOAD_SIGNED_APP_ONLY.uvprojx" -j0 -o logs/<round>/download_app.log
UV4.exe -f "<本次>\boot\DOWNLOAD_PAIRED_BOOT_ONLY.uvprojx" -j0 -o logs/<round>/download_boot.log
```
  （PowerShell 用 `Start-Process ... -Wait -PassThru`。）两份日志都须 `Erase Done.Programming Done.Verify OK.`。工程设置 JL2CM3 + `GR5xxx_16MB_Flash.FLM`、`-FO7`（按扇区擦/写/校验，不运行）——若看到整片擦除设置立即停止。

### 5. 一次复位
- 下载后 PC 停在 `0x20000000`（下载算法 SRAM 循环），此时映射读回为 FF，**不能当作 Flash 被擦**。
- `$S/jlink.ps1 -Action Reset -LogDir logs/<round>`：只做一次 SYSRESETREQ；之后 DHCSR 如 `0x03010001`（S_HALT=0）即运行。不重复复位。

### 6. 读回验收（只读）
```
$S/jlink.ps1 -Action Snapshot -Out logs/<round>/post_flash_1.bin
python $S/check_readback.py --out firmware_releases/<本次> --pre logs/<round>/pre_flash_2.bin --post logs/<round>/post_flash_1.bin
```
必须 `pass: true`：A/Boot 与产物逐字节一致；Boot 日志 PREPARED 代数 = G+1、index/stage/attempts=0、旧镜像=新 A、候选不变；SCA 只有第 2 字（Boot 字节和校验，下载算法自动更新，ROM 需要）变化；除 A/Boot 外仅一个日志页变化；owner、B 区、NVDS 未变。任何不符先停。

### 7. GR 与 CAT1 启动确认
- `gr_cli.ps1 -Commands fw_version,'business status'`：版本、`usb_bench_test` 等符合预期。
- GR 复位通常使 CAT1 掉电（COM21/22/23 消失、`link=0`）。按红线顺序：
  1. `cat1_power on` → 须见 `rail_request=on code=0x0000`；等待 ≥200 ms（实际等 ≥10 s 并 `cat_at FOTA_STATUS`）。
  2. 仍无 `[CAT1 RX]`：只发**一次** `cat1_power key`，核对 ACK；ACK 丢失不盲目重发。
  3. 若回 `[OTA] power change denied: installation pending or journal unknown`（owner INSTALL_PENDING 安全门）：**停止，不绕过**，向用户说明并请求授权。获授权后才执行一次：
     `python -I $S/start_cat1_once.py logs/<round>`
     脚本只在 GR 运行、电源轨已开、PWRKEY 为 MUX7 释放输出时打 1600 ms 脉冲并释放；同一目录拒绝重复执行；不写 Flash/owner/OTA。
  4. 必须取得真实启动证据：COM21/22/23 重新出现，且 `cat_at FOTA_STATUS` 有 `[CAT1 RX]` 回应、`MQTT_STAT state=CONNECTED`、`business status` 为 `link=1 net=4`。电源 ACK、GPIO 电平、VTref 都不能替代。
- 测试中持续观察 CAT1 在线；掉电先暂停定位，不在模块下电时继续发命令。

### 8. 记录
在 `doc/` 当轮中文说明里写：编译事实、产物 SHA-256、配对代数、下载/校验日志、复位前 PC、读回 PASS 明细、GR/CAT1 实证、开机脉冲是否使用及授权来源、未完成项。不得把编译或下载校验写成功能实板通过。

## 已知坑（均已实测）
- 默认 Python 3.12 无 `cryptography` → 签名步骤用 3.11。
- J-Link Commander 的 `CORTEX-M4` 无 GR5526 Flash 算法，只用于读/复位；写 Flash 一律走 Keil Download-only 工程。
- `savebin` 长度必须写 `0x` 前缀（无前缀按十六进制解释会多读）。
- 下载后 SCA `0x200004` 变化是 Boot 校验和更新，属正常。
- 不新增 OTA 机会、不发送 ACTIVATE；R6 selector 5 已 SPENT。
