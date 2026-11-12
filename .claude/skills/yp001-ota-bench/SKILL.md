---
name: yp001-ota-bench
description: YP001 dual-end OTA bench workflow that has been confirmed on the real board — serial pre-check through GR COM26, token-saving event-only OTA watcher, building a first-controlled-trial upgrade package (GR sign + CAT1 sota + review/trial + pack-trial + verify, short file name), verifying a platform download URL with the device's own Lua download chain, building a CAT1 receiver USB_IMPORT within the 512 KiB LuaDB, and starting/re-arming a one-use trial ticket. Use when the user asks to 打包/升级包/上传地址/检查下载地址/开始OTA/补票/监控OTA/预检/CAT1接收端/USB_IMPORT, or to check OTA progress.
---

> **2026-11-10 起 CAT1 出厂即可接收 OTA，不再有"接收端"、冻结 MD5 和写死的版本范围。** 本技能里关于接收端、`OTA_TRIAL_MD5`、`OTA_TRIAL_SOURCE/TARGET`、`USB_IMPORT` 接收端的内容只适用于 11-09 之前的旧固件。新的标准流程见技能 `yp001-ota-factory-ready`。

# YP001 双端 OTA 台架流程（已实板确认部分）

> SAM | 2026-10-30 09:59 +08:00 | 目录已调整：`Air780EGH/` 根目录就是设备当前代码（与 `_ota_release/ota153_20261030/receiver/source` 相同），旧完整版在 `Air780EGH/_archive/`；`_ota_release` 只保留 ota153/ota152/trial151，其余调试版本、`_luatools_release` 和 78 个一次性旧脚本（r5/r6/t151 等测试与 prepare/verify）已归档到 `D:\CODEX\_archive\*.zip`（清单：`_ota_release/ARCHIVED.txt`、`tools/ota/ARCHIVED_ONEOFF.txt`）。下文提到的已归档路径或测试，需从归档包中取用。

SAM | 2026-10-29 11:57 +08:00 | 由 10-29 的 1.0.2→1.5.1 受控试验整理（`doc/2026-10-29_1.5.1受控试验升级包与CAT1接收端.md`）。每条标注确认级别：**实板**＝板子上实测通过；**主机**＝只有主机测试。本技能不授权任何安装机会：发 `OTA_T151` / `OTA_T151R` 或任何新票前都必须有用户当次明确同意。

## 0. 硬约束（AGENTS.md / CLAUDE.md）

- 回复用中文；代码注释 `SAM | 实际北京时间 +08:00 | 内容及原因`。**写注释前先 `date`**，本项目多次写成超前时间。
- Git 写操作交给 Codex（只读 `git status/diff/log` 可用）。
- 每轮在 `doc/` 写中文修改说明；主机测试或编译通过不能写成实板通过。
- OTA/串口测试前先确认 GR 运行、CAT1 已启动（§1）；CAT1 未启动时不得触发 OTA。
- PowerShell 工具可能被禁用，从 Bash 调 powershell.exe 也会被拦。**统一用下面的 Python 串口工具**。
- Python：`/c/Users/SamLi/AppData/Local/Programs/Python/Python312/python.exe`（已有 pyserial、lupa(vendored)、cryptography）。

## 1. 串口工具与预检（实板）

| 工具 | 用途 |
|---|---|
| `tools/ota/gr_cli.py [--wait-ms 8000] "cmd" ...` | 逐条发 GR CLI 命令并打印回包。`cat_at XXX` 转发到 CAT1，需约 8 s 窗口 |
| `tools/ota/ota_watch.py --log logs/x.log --state logs/x.json` | **省 token 的事件监控**：本地每 30 s 查 `FOTA_STATUS`、每 120 s 查 `fw_version`，只在阶段/原因/步骤变化、进度每过 25%、GR 版本变化、完成/停止/卡住/无回包时输出一行。退出码：0 完成，2 停止，3 卡住，4 无回包，5 超时。**用 `run_in_background` 启动，等通知，不要轮询日志** |
| `tools/ota/ota_monitor.py --start "cat_at ..." --minutes 2` | 发一条启动命令后短时记录全部行，用于确认命令被接受 |

预检命令（只读）：

```
python tools/ota/gr_cli.py --wait-ms 8000 "fw_version" "cat_at FW_VERSION" "cat_at FOTA_STATUS" "cat_at HELP" "business status"
```

通过条件：GR `YP001_FW|GR5526|...` 回包；CAT1 `FW_VERSION=` JSON（真实启动证据）；`FOTA_STATUS` 符合预期阶段；`HELP` 含本轮要用的命令（证明刷入的是正确修订）；`[BUSINESS] alarm=0 call=0`、电量。EPD 刷新日志可能截断 GR 回包，必要时单独再读一次 `fw_version`。

## 2. 首次受控试验升级包（实板：包被设备 4G 下载、签名/清单/组件校验通过）

工具：`ReleaseCli`（`tools/ota/portable/*.cs` 用 `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe` 编译，见 `tools/ota/portable/build.ps1` 的源文件组合）。首试范围只认白名单 `PackCore.FirstTrialRanges`（1.0.2→1.5.0、1.0.2→1.5.1），新范围要先改白名单并加测试。

1. GR：用户 Keil F7 后复制 HEX 冻结；签名
   `logs/ota_first_trial_live_20261024/GrBaselineSign_current.exe <hex> tools/toolkit/test_keys tools/toolkit/contracts/layout_candidate.json tools/toolkit/contracts/data_contract_candidate.json <版本> <out.bin>` → 输出 `SIGNED_VERIFIED`。核对 bin 内 `YP001_FW|GR5526|<版本>|<build>|END`。注意工程是否定义了 `YP001_OTA_USB_BENCH_TEST=1`（台架版）。
2. CAT1 目标：`ReleaseCli cat1 <target/source> D:\Installers <target/native>`，看 `script_bytes` ≤ 524288。
3. `review.json`：如实写 `native_installation_accepted=false`、`raw_kv_accepted=false`、未验证项、各源文件 sha256（main.lua 除外，因其内嵌 review 哈希）。把 review 的 sha256 写进**目标和接收端** main.lua 的 `evidence_sha256`，再生成 sota。
4. `trial.json`（schema `YP001_FIRST_CONTROLLED_TRIAL_V1`）：`gr_payload_sha256`＝签名 bin 去掉末尾 904 B 的 sha256；`cat_package_sha256`＝sota sha256；`review_sha256`。
5. `ReleaseCli pack-trial <signed.bin> <sota> <outdir> 495616 <trial.json> D:\Installers tools/toolkit/test_keys tools/toolkit/contracts <目标版本>`。输出短名 `YP001_<源>---<目标>_FIRST.zip`；同名已存在会拒绝（改目录或先归档旧包）。
6. 复核：用 `BundleSigning.VerifyArchive(zip, tools/toolkit/test_keys/OTA_TEST_PUBLIC.xml)` 输出 VERIFIED；记录 MD5/SHA-256/大小。**任何源码改动都会改变 MD5**，接收端冻结的 MD5 必须同步更新，旧包作废。

## 3. 校验平台下载地址（实板对照一致）

用户贴来的地址去掉 `< >`。两步：

```
curl -sS -o f.bin "<URL>"; md5sum f.bin        # 必须等于包 MD5
echo "<URL>" | python tools/ota/check_sequential_tcp.py --archive <本地zip>
```

第二步用电脑 TCP 把真实服务器字节喂给设备同一套 Lua HTTP/顺序 ZIP 代码，期望 `passed/range_refused/whole_md5_verified/signature_verified/gr_digest_verified/cat_digest_verified` 全 true。本平台（tkaiot…tkhealthcare）不支持 Range，chunked 传输，走顺序流回退——正常。服务器限速 7 分钟不断开（10-29 实测）。

## 4. CAT1 接收端 USB_IMPORT（实板：修订 1–5 均由 Luatools 刷入并运行）

- 基础：以设备当前已验证的维护集合为底（例 `Air780EGH/_ota_release/ota_cancel_query_20261029/baseline/USB_IMPORT`），只替换改过的模块。全量主源码超容量约 40 KB，不能直接用。
- 编译：`cd <source> && /d/Installers/_temp/tools/luac_64bit.exe -s -o ../USB_IMPORT/<m>.luac <m>.lua`（与设备字节一致）。
- main.lua：USB 版 = 原 USB main 的依赖锚点前缀 + 新的源 main.lua（前缀 = 旧 USB main 去掉旧源 main 的尾部）。
- 容量：`python tools/ota/luadb_size.py <USB_IMPORT>`，必须 spare ≥ 0。注释不占空间；每个函数原型有固定开销，删除无调用方的退休存根很省空间。
- **换行**：源文件是 CRLF。Python 读写用二进制并按 `\r\n` 替换；Git Bash `sed -i` 会去掉 CR，改完要检查 `tr -cd '\r' | wc -c` 等于行数。
- 新鲜度：对每个 luac 重新编译比对，确保无陈旧文件；写 `receiver/integrity.json`（revision、changed、size、frozen MD5、文件 sha256）。
- 用户刷机时保留 FS/KV。刷后用 §1 预检的 `HELP` 确认命令表。

## 5. 试装票（实板）

- `cat_at OTA_T151=<URL>`：接单，只认冻结 MD5，GR 授权时发一张票（实板 08:20 接单成功）。
- `cat_at OTA_T151R`：补票，只能用于同一任务/epoch/MD5，且只认两种状态各一次：`MAINTENANCE_RETIRED`（实板 08:41 成功）、网络类失败（实板 11:49 成功）。
- 修订 5 起，下载阶段的网络错误不再作废票，受原 3 次/退避上限约束。PAUSED/RUNNING 时 CAT1 重启仍会作废票（安全规则，不放宽）。
- **GR 转发白名单**：GR owner 为 INSTALL_PENDING 时 `cat_at` 只转发 `FOTA_STATUS` 和 `OTA_HANDOFF_RESUME=782fc7f0bca7b0ef37f67a4e633604e4[,2-9]`（`yp001_ota_recovery_control.h`），其余（含 FW_VERSION/HELP）回 `[OTA] UART change denied`。设计任何恢复命令前先核对这里。
- 仅安装恢复：`cat_at OTA_HANDOFF_RESUME=782fc7f0bca7b0ef37f67a4e633604e4,9`（修订 7 实板：转发通、回 `T151I_PREFLIGHT` 未消耗；修订 8 起回 `T151I_PREFLIGHT_<vrui><字母>` 逐项诊断，字母 A/G/F/I/P/D/U/O 见 `ota_runtime.lua` verify_install_recovery）：GR 收完并 INSTALL_PENDING 但提交被拒（`boot_commit_failed`）时，仅重发一次 ACTIVATE，不重新下载。先跑 `gr_ota_probe.py` 确认 owner INSTALL_PENDING、durable=total、Boot PREPARED。修订 6 起 `OTA_T151`/`OTA_T151R` 已删除。
- 发令后：先 `ota_monitor.py --start ... --minutes 2` 确认 `=ARMED`/`=WAIT_GR` 和进度开始增长，再后台 `ota_watch.py` 等通知。

## 5b. GR 仅安装恢复（实板 10-29 13:11 成功）

前提（全部由预检确认）：CAT1 `RECOVERY_HOLD / boot_commit_failed`；探针 owner `INSTALL_PENDING`、durable=total、B 已占用；Boot 最新 `PREPARED`；未停核；无报警/通话。
1. `cat_at OTA_HANDOFF_RESUME=782fc7f0bca7b0ef37f67a4e633604e4,9`（GR 白名单唯一能转发的形式）。约 20 s 后回 `READY`（拒绝时回 `T151I_PREFLIGHT_<vrui><字母>`，不消耗）。
2. 随后 GR 拒绝普通 `cat_at`（安装中），约 40 s 后 GR 重新启动；`fw_version` 应为新版本；Boot 日志 `TRIAL`；CAT1 不掉线（实测 `link=1 net=4`）。
3. 后台 `ota_watch.py` 等试运行确认与 CAT1 组件阶段。
原理：GR 对 INSTALL_PENDING 的 ACTIVATE 在窗口内 `safe(true)` 后立即提交，绕开 PREPARED 分支在写 Boot 日志后重查门控导致的运动样本过期（`yp001_ota.c:594-609`，GR 侧缺陷待下一版修复）。

## 5c. 整机 1.0.2→1.5.1 实板完成（10-29 19:37）

GR owner 310 `CAT1/COMPLETE/success/1.5.1`；GR `001.005.001/b5`；CAT1 `IDLE`、outbox 0、`FW_VERSION` product 1.5.1、code_identity/health VERIFIED。成功路径与每一步的缺陷/绕开方式见 `doc/2026-10-29_1.5.1受控试验升级包与CAT1接收端.md` §29。完成判定用：`gr_ota_probe.py`（owner COMPLETE success）+ `gr_cli.py "cat_at FOTA_STATUS" "cat_at FW_VERSION"`（GR owner COMPLETE 后 cat_at 恢复）。

## 5d. 第二轮整机 1.5.1→1.5.2 实板完成（10-29 23:19，完整记录见 doc/2026-10-29_第二轮OTA准备方案.md §6–10）

- 接收端：`Air780EGH/_ota_release/ota152_20261029/receiver`（通用“仅安装”路径、io2 按任务绑定、GR `boot_commit_failed` 自动重发一次、发 REBOOT 前快照）。发令：`cat_at OTA_TRIAL=<完整平台URL>`（只认冻结 MD5，URL 必须含同一 `md5=`，运行版本须为源版本）→ 回 `OTA_TRIAL=WAIT_GR`。
- 只读命令：`FOTA_STATUS`（含 `OTA_IO=<io>/<次数> TRIAL=<票>`）、`OTA_FS`（fsstat + 根目录）、`FOTA_PROBE`（init/wait 计时后 finish(false)，实测 init 23 ms）。`OTA_PRUNE`：先把第一轮历史键归档到 VUART，再删除（已执行过，空闲 +约 12 KB）。
- 打包：`ReleaseCli pack-trial ... <目标> <源>`（第 11 参数为源版本）；csc 用 Python 调用（反斜杠路径），Git Bash 下 `/nologo` 会被路径转换。
- 坑：①GR 组件 438472 B 需 CAT1 FS 空闲 ≥454856 B，OTA 日志变大即 `COMPONENT_SPACE`（先 `OTA_FS`）；②VUART 日志程序占 COM21/23 时 Luatools 反复重开 COM22——刷机前先停日志；③GR 健康 120 s 会因 CAT1 掉线/刷机重新计时；④包内 1.5.2 目标脚本不含 22:17 后的修复，下一轮先刷新接收端。
- 监控：`cat1_vuart_log.py`（`[OTA] B` 信标）+ `gr_owner_watch.py`（J-Link），GR 健康窗口内不发 cat_at；GR 健康变量用新 AXF `fromelf -s` 取地址后 J-Link `mem32` 只读。

## 6. 数据审计（实板）

`cat_at OTA_DATA_AUDIT`：返回 `list={o,n,i,l,d,k}` 定位。设备 V2052 `io.lsdir` 翻页有 bug（offset 跳过时把 `.`/`..` 计数），根目录改为一次读取（上限 100）。10-29 实板：19 项无重名，文件全部读通，停在 `KV_STATUS/KV_UNAVAILABLE`（KV 未初始化，首试策略记为 KV 未验证）。

## 6b. GR 端只读探针（实板 10-29 12:13）

`python tools/ota/gr_ota_probe.py --epoch <N> --json logs/gr_probe_<时间>.json`：J-Link 只读（不停核，`halted:false`）一次给出：
- owner 两页：generation、phase、total/durable（B 区持久进度）、版本。`OTA_PROGRESS=GR5526:x/y` 只是 CAT1 本地文件进度，GR 实际进度以这里的 durable 为准。
- Boot 日志最近几代状态（PREPARED/INSTALL/TRIAL/ROLLBACK/CONFIRMED/REVERTED）。
- RAM 中 `g_ota_install_first_error`（按内容特征搜索，不需要运行镜像的 map）：阶段号（6 = 提交门控）、失败门控名、电量/按键/运动样本年龄。
CAT1 报 `boot_commit_failed`、`activation_validation_failed` 或长时间 DOWNLOAD_PENDING 时，先跑它再分析。

## 6c. CAT1 安装期可见性（10-29 实证）

- GR 在 CAT1 组件 INSTALL_PENDING 期间拒绝**全部** `cat_at`（含 FOTA_STATUS），FOTA_STATUS 不可用。
- GR 的 CAT1 接收环 `s_cat_diag_rx`（1.5.1：0x2001CACC，4 KiB）约 20 s 覆盖一遍；读一次性诊断必须先开 `tools/ota/cat_ring_capture.py`（每 3 s）**再**让 CAT1 重启。去重输出不能用来推断帧频率（10-29 曾因此误判）。
- 修订 16 起 CAT1 在 USB 虚拟串口（VUART，COM21 或 COM23）写明文 `[T151K]` 诊断与 10 s 信标：`python tools/ota/cat1_vuart_log.py --log logs/x.txt` 后台长期记录。COM22 是二进制跟踪口（需 Luatools）。
- CAT1 原生安装的核心约束：GR 授权新鲜度 3 s，凡是慢操作（重哈希、数据扫描、fota.init）之后必须重新取得 STATUS；排查时先列出路径上所有慢操作。

## 7. 主机回归（改接收端后全跑）

```
S=Air780EGH/_ota_release/trial151_20261029/receiver/source
for t in test_t151_native test_t151_k test_t151i_route test_file_list_diag; do python tools/ota/$t.py $S; done
```

修订 8 起 R6 selector 入口已删，R6 专项测试（selector 6/7/8、result_unlock、trial151、t151_runtime/network）只在旧修订备份上作历史回归。

关键教训：只测 manager 层会漏掉 runtime 路径（08:20 的 adopt_r6 就是这样漏的）。改动涉及准备/下载时，必须用 `test_t151_runtime.py` 这类走真实 `ota_runtime` 的测试，并先在旧修订上复现板子上的失败（`--expect-device-failure`）。
