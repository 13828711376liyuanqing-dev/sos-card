---
name: yp001-ota-factory-ready
description: YP001 整机 OTA 的当前标准流程（2026-11-10 起：出厂的机器就能接收 OTA，没有"接收端"、没有冻结 MD5、没有写死的版本范围）：改版本→编译→签名→打包→上传→推送；设备端规则、搭基线（J-Link 刷 GR + Luatools 清 KV/FS 刷 CAT1）、预检与监控写法、各种拒绝/卡住的判读（HTTP_NATIVE_CONTRACT、SOURCE_VERSION_MISMATCH、DATA_EVIDENCE_UNAVAILABLE）、评审清单与门禁的坑、验收状态。做台架 OTA、打升级包、搭新基线、推送后监视、OTA 报 REJECTED/卡 RECOVERY_HOLD 时先读这个；旧的接收端流程（yp001-whole-ota-run、yp001-ota-bench）只适用于 11-09 之前的旧固件。
---

# YP001 整机 OTA：出厂即可接收（2026-11-10 起的标准流程）

SAM | 2026-11-10 | 来源：用户基线"客人手里的机器不能逐台刷，CAT1 出厂就要能收 OTA，和 GR 一样"。实施记录 `doc/2026-11-10_OTA出厂即可接收_实施记录.md`，给同事的步骤 `doc/2026-11-10_整机基线与OTA升级_工具使用说明.md`。

**验收状态（2026-11-10 真机，已通过）**：同一块板、中间不重刷、没有接收端，连续两次 OTA：1.5.29 → 1.5.30（12:08 推送 → 12:23 完成）和 1.5.30 → 1.5.31（13:03 → 13:19，第一次推送没送到，重推后成功）；两次 owner 都是 `COMPLETE/CAT1/success`，Boot `CONFIRMED`；最终 GR `001.005.031/35`，CAT1 `LuatOS Ver 001.005.031`。
**已冻结**：基线 `YP001_1.5.31_b35_20261110_OTA_FACTORY_READY_PASS_KNOWN_ISSUES`（9106 个文件，`baseline.py verify` 通过，已登记 `baselines.json`，`make_review_manifest.py` 默认基线和 oneclick `state.json` 已切到它）；评审清单在 `logs/ota_1.5.30_to_1.5.31_20261110/review_manifest.json`（相对 b27 共 15 项）；5 个 CAT1 OTA 文件已同步到同事工程（他的 `audio_drv.lua`、`network_watchdog.lua` 和版本号没动）。
**还没验证**：一键工具 `oneclick.py` 改动后没有端到端跑过；同事的设备刷新基线后能否收 OTA；OTA 期间发业务消息的守卫测试。

## 0. 规则（设备端）

- 设备从**它当前运行的版本**升级到**任何更高版本**；源版本取运行时的 `PRODUCT_VERSION`，不再写死（`Air780EGH/ota_trial.lua`：`eligible` 用于安装前，`scoped` 用于数据范围，**安装重启前后都要成立**）。
- 谁能装由**签名清单 + 授权文件**决定（私钥是唯一闸门）；包清单里的源版本必须等于设备当前版本（`SOURCE_VERSION_MISMATCH`），目标版本必须更高（`VERSION_NOT_NEWER`），见 `ota_bundle.lua`。
- **升级包只认源版本**：设备在 1.5.29 就要 1.5.29→X 的包；另一个版本的设备要另打一个包。
- 每个任务一张一次性票据，新任务在 GRANT 时替换旧票据。
- 源码里**没有** `OTA_TRIAL_MD5/SOURCE/TARGET`，也没有"接收端"。台架命令是 `cat_at OTA_TRIAL=<目标版本> <带 md5= 的下载地址>`。

## 1. 流程（每次升级）

1. 4 号工具改版本：**新内容必须用新版本号**（同版本不同内容会让后台和日志分不清；版本不能倒退；构建号自动加 1）。
2. Keil F7（增量，不要 Rebuild；编完不要再打开 Keil，否则一键工具的评审清单会被界面状态文件弄失效）。
3. 2 号工具签名（期望版本填新版本）。
4. 4 号工具（v1.8）：**"读设备版本"**（3 号工具的源版本填它，填错的包设备会拒绝）和"读取设备可用空间"（GR 命令口；列表已去掉 CAT1 的口）；要用真实读数，门槛只是门槛。
5. 3 号工具：① 生成 CAT1 包 → ② 授权（**源版本 = 设备现在的版本**，两个确认框要人勾）→ ③ 打包 → ④ 验证；**工作文件夹每次新建**。
6. 上传平台，下载核对：`cmp` 和本地包字节一致、`YpOtaPack verify`。
7. 预检 `ota_check.py pre` → 开监控 `ota_run_monitor.py` → 用户在后台推送（推送对象填 IMEI；我没法替用户点后台）。
8. 最终核对 `ota_check.py post --target <版本>`（它会先唤醒 CAT1）；等价的手工写法（**先唤醒 CAT1**，否则 CAT1 已被 GR 关电，`cat_at` 没回应）：
   `python tools/ota/bench/boot_then.py logs/<轮>/verify.log "fw_version" "cat_at AT_INFO" "cat_at FOTA_STATUS"`
   GR 版本看 `fw_version`；**CAT1 版本看 `cat_at AT_INFO` 的 `LuatOS Ver`**（001.005.0XX）；`OTA_OUTBOX` 刚完成时可能是 1（结果消息在排队），唤醒后应为 0；再用 `gr_ota_probe.py` 看 owner 和 Boot。

一键工具 `tools/ota_oneclick/oneclick.py` 可代替 2~3 步（`--from <设备版本>`，需要 `make_review_manifest.py` 生成的评审清单；**清单生成后立刻打包**）。它不再生成接收端，`2_CAT1刷机目录` 是目标版本完整脚本，出厂用。**注意：11-10 改了它之后还没端到端跑过，第一次用请先做一次 `check`。**

## 2. 搭基线（旧固件设备、新板子都用这个）

旧固件（带写死范围）收不了。基线 = 完整的新固件，**一次**：
1. GR：2 号工具签名 → `GrJLinkFlash.exe`（或 `yp001_gr_jlink_flash.py`）有线烧；会清 Boot 回滚记录、GR 的 OTA 记录和 B 槽，并做出厂清空（姓名、房号、园区）。
2. CAT1：1 号工具生成 `USB_IMPORT` → Luatools：先"删除全部"再加目录；**设备上有卡住的 OTA 记录时必须同时勾"清除KV分区"和"清除FS分区"**（会丢绑定号码、MQTT/SIP 参数，要后台重发）。
3. 确认：GR 命令口 `fw_version`；CAT1 信标 `IDLE`、`cat_at FOTA_STATUS` 的 `OTA_IO=nil/0 TRIAL=nil`。
刷 CAT1 前先开保电 `keep_cat1.py`，刷完关掉 Luatools 并停保电。

## 3. 预检、监控（只读，写法）

**一条命令的写法（11-10 起，优先用；都要求 GR 命令口没被别的程序占用）**：
```
# 推送前：包名/范围、平台文件是否字节一致、设备两端版本是否等于包的源版本、OTA 空闲、空间够不够、打包时填的空间是否多于设备实际
python tools/ota/bench/ota_check.py pre --zip <包.zip> --url "<平台下载地址>"
# 推送时：一条命令开保电+信标日志+owner 监控，只输出阶段变化和异常；owner 到 COMPLETE 自己结束；超时没收到推送会提醒
python tools/ota/bench/ota_run_monitor.py --round logs/<本轮目录>        # 配合 Monitor 工具用，--max-min 默认 45
# 升完：两端版本、OTA 状态、owner、Boot、安装错误一张表
python tools/ota/bench/ota_check.py post --target <目标版本>
# 只读设备：python tools/ota/bench/device_probe.py
```
`pre` 能拦下"包的源版本和设备版本不一致"这类错（11-10 实际发生过一次：1.5.28→1.5.29 的包，设备已是 1.5.29）。`ota_run_monitor.py` 停时会结束自己启动的三个辅助进程。

下面是它们背后的手工等价写法：

```
# 预检（等 CAT1 稳定后再发命令；GR 口自动识别）
python tools/ota/bench/boot_then.py logs/<轮>/pre.log "cat_at FOTA_STATUS" "cat_at OTA_FS"
# 推送前：保电 + 信标日志 + owner 监控（后台）
YP_RAW_LOG=logs/<轮>/keep.log python tools/ota/bench/keep_cat1.py 60
python tools/ota/cat1_vuart_log.py --log logs/<轮>/run_vuart.txt --min 80
python tools/ota/gr_owner_watch.py --target GR5526 --max-min 40
# 完成后
python tools/ota/gr_ota_probe.py > logs/<轮>/probe_post.json     # J-Link 只读：owner、Boot
python tools/ota/gr_cli.py --wait-ms 9000 "fw_version" "cat_at FOTA_STATUS"
```
Monitor 过滤只报阶段变化：`[OTA] B` 行取阶段、原生安装状态（`N=` 字段）和最后一列，`owner gen`、`OTA_RX|REJECT|DATA_` 单独报。预检读 `OTA_FS` 前要先停我自己的保电进程（它占着 GR 口）。

**推送没反应时**：推送后 30 秒内日志里没有 `LOG_CLEARED` 和 `[OTA_RX]`，就是消息没送到设备（11-10 13:03 实际发生：设备一直 `IDLE`，用户重推后 10 秒内就 `ACCEPTED`）。让用户在后台查推送状态、IMEI、目标版本；**不要在设备已经 `ACCEPTED` 之后重推**。
**监控注意**：Monitor 30 分钟到期会停，整个 OTA 约 16 分钟但推送可能晚，到期通知出现而 OTA 还在跑就重新开；`gr_owner_watch` 在 GR 暂存完成、安装、复位期间报 `PROBE_ERROR`，或读出乱码的 owner 值（如 `536901980, 92, ' \y'`，同时 Boot 字段是 `INSTALL`）都是 J-Link 读复位中的 GR，**不是故障**，等 `INSTALL_PENDING`。
**正常时间线（1.5.29→1.5.30，约 15 分钟）**：LOG_CLEARED → `[OTA_RX] ACCEPTED` → PREPARING（下载）→ owner DOWNLOADING GR5526 → `PROBE_ERROR`（GR 复位，正常）→ `RECOVERY_HOLD … SPENT … ACTIVATION_RECHECK_FAILED … HEALTH_IDENTITY`（正常）→ owner `INSTALL_PENDING` GR、Boot `TRIAL` → CAT1 `IDLE`、PREPARING → INSTALLING（写入 `N=WRITING`）→ CAT1 重启（`PC COM21 lost`）→ `RECOVERY_HOLD COMMITTING … HEALTH_OBSERVING` → `COMPLETE_PENDING … CONFIRMED CONFIRMED … RESULT_CHALLENGE_PENDING` → `IDLE`，owner `COMPLETE`。

## 4. 判读

| 现象 | 原因 | 处理 |
|---|---|---|
| `[OTA_RX] REJECTED HTTP_NATIVE_CONTRACT` | 设备是**旧固件**（写死范围/冻结 MD5），或不是 Air780EGH/V2052 | 按第 2 节刷新基线 |
| 设备拒绝、提示源版本不符 | 包的源版本 ≠ 设备当前版本（3 号工具"源版本"填错，或用了旧包） | 重新打包，源版本填设备真实版本；**推送前先看包名 `YP001_<源>---<目标>`** |
| CAT1 卡在 `INSTALLING … N RECOVERY_HOLD COMMITTING … DATA_EVIDENCE_UNAVAILABLE`（超过 5 分钟） | **安装后重启的数据对比**用了"运行版本必须等于源版本"。11-10 我犯过的错，已改成 `scoped`（源或目标版本都行） | 如果又出现，先查 `ota_native_fota.lua` 的 `valid_data` 用的是不是 `scoped`；设备要刷新基线并清 FS/KV、GR 重刷才能脱困 |
| 同版本号两份不同内容 | 没升版本号 | 一律升版本号，后台已有的版本号不要复用 |
| 3 号工具 ② 报"请填写源版本" | 没填 | 填设备当前版本 |
| 门禁拒绝 `source inputs changed since review` | Keil 在评审后改了界面状态文件 `.uvguix.*` | 重新生成评审清单，立刻跑一键工具 |

**空间实测（11-10）**：清 FS/KV 后基线 `used=9`（可用 487424）；第一次 OTA 后 `used=15`（462848），第二次之后仍是 15，没有逐次增长；门槛（红线 GR）≥ 425984。**以后每次要读真实值**，余量大约 36864。

## 5. 教训（别再犯）

- 主机测试要**模拟安装后重启**（运行版本变成目标版本）；11-10 的 `DATA_EVIDENCE_UNAVAILABLE` 就是主机测试版本不变所以没抓到。`test_data_transaction.py` 现在有这条。
- 新内容用新版本号；用一个目录一个包，别在 `123` 这样的旧目录里反复出包。
- COM 号会变，脚本用 `tools/ota/gr_port.py` 自动识别（排除 CAT1 的 19D1/17D1 和 nRF 的 1915）；4 号工具列表也同样排除。
- 工具包重建时有工具窗口开着会锁住 exe，先建到临时目录，关掉窗口后再复制。
- 不要把空间"门槛"当设备实际可用空间填给 3 号工具。

## 6. 还没做

- 同事设备用新代码重刷基线后做一次 OTA 验证（他们的树里 5 个 CAT1 OTA 文件已同步，旧固件设备收不了）。
- 守卫测试（OTA 期间发业务消息）、强制船运实物验收、救援演练仍是 pending（冻结清单 `known_issues` 里有）。
- 一键工具端到端验证；第一次推送没送到的原因（平台侧，待查后台记录）；`ota_check.py`/`ota_run_monitor.py` 的真机回归（`ota_run_monitor.py` 完整跑一次 OTA）还没做，只做了 30 秒自测。
