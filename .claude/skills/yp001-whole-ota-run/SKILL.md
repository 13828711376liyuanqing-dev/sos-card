---
name: yp001-whole-ota-run
description: End-to-end YP001 whole-device OTA (GR5526 + Air780EGH CAT1) as currently run successfully on the bench — latest 2026-11-02 1.5.7 -> 1.5.8 with the colleague's business code merged (earlier 10-29, 10-30, 11-01). Covers preparing the CAT1 receiver and target, host tests, packing and freezing the MD5, checking the platform URL, flashing the receiver, preflight with the settle-wait bench scripts, starting with cat_at OTA_TRIAL, event-only monitoring, the normal beacon sequence, every known stall with its fix, post-OTA checks and syncing source. Use when the user asks to 准备/发起/走一次整机OTA, 下一轮OTA, 打包新版本, OTA进度, OTA卡住, OTA_TRIAL=REFUSED, SNAPSHOT/DIRECTORY_UNVERIFIED, or OTA后核对.
---

> **2026-11-10 起 CAT1 出厂即可接收 OTA，不再有"接收端"、冻结 MD5 和写死的版本范围。** 本技能里关于接收端、`OTA_TRIAL_MD5`、`OTA_TRIAL_SOURCE/TARGET`、`USB_IMPORT` 接收端的内容只适用于 11-09 之前的旧固件。新的标准流程见技能 `yp001-ota-factory-ready`。

# YP001 整机 OTA 全流程（最近实板成功：11-02 10:57→11:18，1.5.7→1.5.8，含同事业务代码）

SAM | 2026-11-02 +08:00 | 按 11-02 成功流程重写。记录：`doc/2026-11-02_CAT1重新合并记录.md`；同事改代码的约束：`doc/2026-11-02_CAT1代码交接清单_同事改代码与OTA.md`。其他技能：打包/URL/USB_IMPORT 细节 `yp001-ota-bench`，空间 `yp001-space-budget`，有线恢复 GR `yp001-gr-jlink-flash-tool`。**实板**＝板上测过，**主机**＝只在主机测过。

## 0. 规则

- SAM | 2026-11-06 | **台架实战纪律（保电、Luatools 刷机坑、CAT1 空间与 `ble.ini`、下载被掐断的诊断、GR 遗留授权）见技能 `yp001-ota-bench-runbook`，做 OTA 前先读它。**

- 回复中文；结论写进 `doc/*.md`，聊天里只给路径；改动注释 `SAM | 北京时间 +08:00 | ...`。
- **不碰 Git/SVN**（命令、`.git`/`.svn` 都不碰，命令文本里也别出现这两个词，钩子会拦）。`D:\SVN\Air780EGH` 只做普通文件复制。提交交给用户或 Codex。
- 用户负责：Luatools 刷 CAT1、上传平台、J-Link 恢复 GR。每次新的安装机会都由用户同意。
- Lua 源码都是 CRLF：用 Python 二进制读写；Git Bash `sed -i` 会剥掉 CR。
- 合并同事代码：**以实板验证过的代码为底**，同事改动逐项移植，扫描重复函数和缺失的 `require`。
- SAM | 2026-11-03 | 与姓名字库下载共用的下载规则（CAT1 真在线再发令、`[OTA_HOLD]` 全程保电且共用锁不被字库流程误释放、下载前清 CAT1 日志、平台存储地址带 `md5=`）见技能 `yp001-cat1-download-flow` 第 0 节。OTA 前清日志用一键工具 `--clean-ota-log`/`--auto-prune`。

## 1. 时间线（11-02 实测，约 21 分钟）

| 时间 | 事件 |
|---|---|
| 10:57 | `OTA_TRIAL=WAIT_GR`，GR 开始往 PSRAM 暂存（512 KB 区） |
| 11:07 | 暂存完成，CAT1 进入 `WAIT_ACTIVATE`，GR 安装（owner PREPARED / Boot INSTALL）；CAT1 断电约 50 秒 |
| 11:08 | `RECOVERY_HOLD ACTIVATION_RECHECK_FAILED S HEALTH_IDENTITY`（**正常**，GR 安装期间的等待），Boot TRIAL |
| 11:11 | Boot CONFIRMED，owner 切到 `DOWNLOADING CAT1` |
| 11:12 | CAT1 `INSTALLING … N WRITING` |
| 11:13 | CAT1 重启 |
| 11:15 | `COMPLETE_PENDING … RESULT_CHALLENGE_PENDING` |
| 11:18 | owner `CAT1 / COMPLETE / success / 1.5.8`，Boot CONFIRMED |

## 1.5 一键工具（优先用）

`tools/ota_oneclick/oneclick.py`（双击 `oneclick.bat`；说明 `使用说明.md`）：给 GR 的 HEX 和 CAT1 源码两个位置，自动做完 §2 的版本检查、OTA 规则检查、主机测试、GR 签名、CAT1 包、授权、读设备空间、打包验证、接收端和 USB_IMPORT，产物在新目录 `firmware_releases/ota_<源>_to_<目标>_<时间>/`（1_GR烧写文件、2_CAT1刷机目录、3_上传平台的升级包、报告.md）。评审声明首次由人确认一次。OTA 实板成功后用菜单「记录 OTA 已成功」更新设备版本和验证基线。刷机、上传、发令（§3 起）仍按下文做。下面 §2 是工具里每一步的手工做法，工具出问题时对照。

## 2. 准备

1. **目录**：每轮新建 `firmware_releases/ota<轮>_<日期>/`，内含 `receiver/`（设备当前版本）、`target/`（目标版本）、`work/`（包）、`receiver_out/`（USB_IMPORT）。
2. **receiver**：以上一轮实板成功的 `target` 为底：
   - `main.lua` 的 `VERSION` / `PRODUCT_VERSION` / `FW_RELEASE_BUILD` 改成设备当前版本；
   - `OTA_TRIAL_SOURCE` / `OTA_TRIAL_TARGET` 改成本轮范围；
   - `ota_trial.lua`、`ota_native_fota.lua` 的版本对同步改；
   - 需要清上次失败任务时，加一次性清理块，并**换新标记名**（旧标记已存在就不会执行）。
3. **target**：同一份源码，版本改成目标版本，去掉一次性清理块。
4. **主机测试**（全部通过才往下走）：
   - `python tools/ota/test_ota152_flow.py <receiver>`；
   - `python tools/ota/bench/test_inv_dirs.py <receiver>` 和 `<target>`：覆盖数据快照、目录、GNSS 缓存；
   - `OTA_SOURCE_DIR=<源码>` 下的 test_cat_manager / test_cat_health / test_native_fota。
   - test_data_inventory、test_data_transaction 在已验证基线上也失败（测试脚本过时），不算回归。
5. **GR**：签好的镜像（`GR5526_<ver>_b<build>_signed.bin`，不超过 441464 B）。GR 不改时沿用上一轮的镜像。
6. **打包**：`YpOtaPack.exe cat1 → auth → pack → verify`，`--free` 填 `cat_at OTA_FS` 的真实空闲字节。记下包的 MD5。
7. **冻结与生成**：MD5 写进 receiver 的 `main.lua` 的 `OTA_TRIAL_MD5`，然后 `Cat1UsbImport.exe --source <receiver> --out <receiver_out> --force`（LuaDB 不超过 524288）。
   - USB_IMPORT 里的 `main.lua` 排版和源码不同，检查时 `grep OTA_TRIAL_MD5`，**别按行号找**。
8. **平台地址**：用户上传后把 URL 存到 `logs/<轮>/url.txt`（须带 `?md5=<包MD5>`；接收端只认 MD5，换地址/文件名不用重打包）。SAM | 2026-11-04：一条命令 `python tools/ota/check_url.py logs/<轮>/url.txt --package <上传的zip>`：下载核对 MD5、探测 Range/ETag/传输方式/跳转/空闲断开，自动判断 Range 或流式后台并跑对应的设备 Lua 校验（`check_range_tcp.py` / `check_sequential_tcp.py`，后者要求服务器拒绝 Range），`report.json` 里 `PASSED=true` 才往下走。
9. **刷 receiver**：用户用 Luatools 刷 `receiver_out/USB_IMPORT`，保留 FS/KV。刷之前停掉占 COM21/COM23 的 VUART 日志；**刷完让用户关掉 Luatools 对 COM26 的占用**。
10. **在主机上改过代码，就重新打包、重新冻结、重新生成 USB_IMPORT，并让用户重刷、重传**，旧包作废并移到 `old_<md5前8位>/`。

## 3. 预检（COM26，只读）

`python tools/ota/bench/boot_then.py logs/<轮>/pre.log "cat_at FOTA_STATUS" "cat_at OTA_FS"`

- 脚本会先 `cat1_power reset`，等 CAT1 连上 MQTT、且之后 12 秒内没有断电（`cat1wait.settle`），再发命令。GR 的电源状态机会二次复位 CAT1，GR 也可能自己重启一次，直接发命令会落空。
- 通过条件：
  - CAT1 `IDLE`、`OTA_OUTBOX=0`；
  - 空间：`(128 − used) × 4096 ≥ GR 镜像 + 16384`（11-02 used=17，空闲 454656，需要 440552）；
  - `OTA_FS` 列表里根目录只有文件，以及 `luadb`、`log`、`ble` 三个目录，没有别的目录。
- 空间不够：用户同意后执行 `cat_at OTA_PRUNE`（详见 `yp001-space-budget`）。

## 4. 发令与监控

1. 后台启动：
   - `python tools/ota/cat1_vuart_log.py --log logs/<轮>/run_vuart.txt --min 80`
   - `python tools/ota/gr_owner_watch.py --target GR5526 --max-min 40 > logs/<轮>/run_owner_gr.txt`（走 J-Link，不占串口）
2. 发令：`python tools/ota/bench/start_ota.py logs/<轮>/url.txt logs/<轮>/start.log`，期望回复 `OTA_TRIAL=WAIT_GR`，随后 `[OTA_HOLD] 1`。
   **必检清单** `doc/2026-11-04_整机OTA必检清单与出厂状态.md`。发令脚本还必须看到 GR 打印的 `[OTA_HOLD] on`（`MUST OTA_HOLD: PASS`，保电）。GR B 槽不是每次必清：首次确认空后 owner 带 `OTA_B_OWNED` 标记延续；只有出厂/有线烧录后首次和 `CANCEL_EMPTY` 要求 B 全 FF。
   **必检（SAM | 2026-11-04，用户规定）：发令时设备必须先清 CAT1 日志**，脚本输出 `MUST LOG_CLEARED: PASS <字节> B` 且退出码 0 才算发令成功；`FAIL`（退出码 2）= 没看到 `[OTA] LOG_CLEARED`，停下查原因，不进入监控。打包前一键工具也静态检查 CAT1 源码里"发令前清日志 / OTA 中不写日志"5 项代码齐全（`oneclick.py` 的 `MUST_HAVE`），缺了直接停，`--reviewed-ota-change` 也不能放行。
3. 用 Monitor 只看阶段变化，把 PREPARING/PAUSED 合并成一种等待，否则会每 10 秒提醒一次：
   ```
   tail -n 0 -F logs/<轮>/run_vuart.txt | awk '/\[OTA\] B /{ph=$5; if(ph=="PREPARING"||ph=="PAUSED") ph="WAIT"; k=ph" "$7; if(k!=p){print $1,$5,$7,$NF; fflush(); p=k}; next} /SNAPSHOT|ERROR|error|traceback|stack/{print "!!",substr($0,1,160); fflush()}'
   ```
   不要把 `FAIL` 放进报警词：`ACTIVATION_RECHECK_FAILED` 是正常状态。
   SAM | 2026-11-04：1.5.10 起发令时设备先删 `/log/app.log`/`.bak`（VUART `[OTA] LOG_CLEARED <字节>`，`ble.ini` 保留），OTA 进行中 `fs_log` 不写日志文件，回到 IDLE 恢复；并兼容新后台 ccrcapp（openresty：重复 `Accept-Ranges`/`Vary`、不带引号的 ETag，`If-Range` 被忽略）。1.5.10 起信标末尾多 `P <进度>`（`V`整包 MD5 预检、`D`组件下载、`G`串口转 GR，`字节/总`），上面 awk 的 `$NF` 打印的就是它；1.5.10 起下载为 16 KB 一段、每 tick 最多 3 秒连续下（参数在 `ota_device_options.lua` 的 `download_tuning`），PAUSED/PREPARING 交替仍是正常等待。
4. GR 切到 CAT1 后，停掉 GR5526 的 watcher，改开 `gr_owner_watch.py --target CAT1 --max-min 20`，它在 owner 到 `COMPLETE` 时退出。

正常信标顺序：
1. `PREPARING/PAUSED DOWNLOAD_PENDING`
2. `WAIT_ACTIVATE`
3. CAT1 断开约 50 秒
4. `RECOVERY_HOLD … ACTIVATION_RECHECK_FAILED S HEALTH_IDENTITY`
5. `IDLE RUNNING`
6. `PREPARING PENDING_GR` ↔ `PAUSED DOWNLOAD_PENDING`
7. `INSTALLING … S IO_READY → NATIVE_INSTALL_PENDING`
8. CAT1 重启
9. `COMPLETE_PENDING … RESULT_CHALLENGE_PENDING`
10. `IDLE … N CONFIRMED CONFIRMED`

## 5. 已知卡点（实板）

| 现象 | 原因 | 处置 |
|---|---|---|
| `OTA_TRIAL=REFUSED` | 设备里接收端冻结的 MD5 和 URL 不一致（用户刷的是旧 USB_IMPORT 或没刷进去），或者 `PRODUCT_VERSION ≠ OTA_TRIAL_SOURCE` | 请用户在 USB_IMPORT 的 `main.lua` 里 grep `OTA_TRIAL_MD5`，确认后重刷；URL 不用重传。拒绝发生在任何动作之前，板子不受影响 |
| `could not open port 'COM26'` | Luatools 等程序占着 COM26 | 请用户关掉占用的程序 |
| 发令后没反应，只有 `rail_request=off` | CAT1 被 GR 空闲关电（最后一行 `[TAG]` 后约 60 秒）或二次复位 | 用 bench 脚本（settle 等待），不要手动发令 |
| `CAT1_INSTALL_ARMED`，`[OTA] SNAPSHOT` 每秒重复 | 根目录有未登记的目录 → `DIRECTORY_UNVERIFIED`（11-02 同事 `fs_log` 的 `/log`、`/ble`） | `ota_data_inventory.lua` 只按名字放行；GR 那半已完成的话要用 J-Link 把 GR 恢复到源版本，重刷 receiver 后整轮重来 |
| 预检时根目录出现新缓存文件（`hxxt.dat`/`hxxt_tm`/`hxxtloc`） | exgnss 定位时改写；安装前后两次快照会不一致 | 已按名字放行；再出现新的缓存名，同样加进放行名单，并补主机测试 |
| `GR_GRANTED … S COMPONENT_SPACE` | CAT1 空闲空间不足 | 用户同意后执行 `cat_at OTA_PRUNE`；票不会被扣 |
| `RECOVERY_HOLD ACTIVATION_RECHECK_FAILED` | GR 安装期间 CAT1 掉电重启 | 正常，等 GR 确认 |

### 5b. 2026-11-04 实板新增（1.5.9→1.5.10，约 16 分钟成功）

- 板子 GR 口现为 **COM30**：`boot_then.py`/`start_ota.py` 前设 `YP_GR_PORT=COM30`；`gr_cli.py --port COM30`。
- 提速后各段：MD5 预检约 25 s、GR 下载约 40 s、**串口转发 GR 约 5 分钟（现在最慢）**、GR 安装确认约 3.3 分钟、CAT1 下载约 40 s、CAT1 写入确认约 6 分钟。
- 信标 `G` 是 GR 已持久确认字节，PSRAM 暂存期间一直 `G0`，传完跳到总数，**不是卡住**（1.5.11 改为显示已接收字节）。
- 失败任务在 GR 留下 `DOWNLOADING` owner 时，新包会被 GR 回 `busy`：刷带清理块（`--clean-ota-log`）的接收端 → `cat_at OTA_GR_CANCEL_EMPTY`。GR 要求 B 槽全 FF，否则 `cancel_not_empty_or_safe`；用户授权后 J-Link 只擦 `0x280000–0x2EBFFF`（`tools/gr_release/GR_JLink_Flash` 的 `jlink(DEVICE, ['erase 0x280000 0x2EBFFF','r','g'])`），擦前后 1 MB 比对 B 以外逐字节相同、SCA 不变。
- GR 重启后有 `DOWNLOADING` 记录时约 10–15 分钟内 `cat_at` 回 `[OTA] UART change denied`（保护窗口），放行后 GR 会关 CAT1，用 `boot_then.py` 重新上电再发。
- `gr_owner_watch.py` 一启动看到旧的 `COMPLETE`（如取消收据）会立刻退出，发令后再开；与 `gr_ota_probe.py` 同时用 J-Link 会读失败。
- 教训：设备侧参数（段大小等）必须用**真实端口**做主机测试（`test_download_speedup.py` 的真实候选文件接口用例），夹具会掩盖上限。

## 6. 完成后

1. `python tools/ota/bench/boot_then.py logs/<轮>/post.log "cat_at FOTA_STATUS" "cat_at OTA_FS"`：
   - CAT1 `IDLE`、`OUTBOX=0`；
   - 业务正常：`[MQTT_ENV] CONNECTED`、`[NTPSYNC]`、`RSSIBAR`、`POWERON`。
2. `python tools/ota/gr_ota_probe.py > logs/<轮>/probe_post.json`：owner `COMPLETE/CAT1/success/<目标>`，Boot CONFIRMED。
3. 停掉所有 watcher 和 Monitor。
4. 同步源码（工具 `tools/tree_sync/`，说明见其 `使用说明.md`）：
   - 先 `python tools/tree_sync/tree_sync.py scan`，确认 SVN 侧没有同事的新改动；有的话先走 `pull` / `merge`。
   - 把两处顶层文件和 `soc/` 备份到 `D:\CODEX\_archive\before_sync_<轮>_<日期>_<时分>`，再把 `target/` 复制到本项目 `Air780EGH`；`tree_sync.py push --yes` 推到 SVN（覆盖前自动备份）。
   - `python tools/ota/bench/cmpdir.py <target> <目的>` 核对，应只剩 `DSTONLY`；目的目录多出的文件不删，列出来由用户决定。
   - 两边一致后执行 `tree_sync.py baseline`（记基线并存档内容，下次三方合并要用）。
   - 交给同事前执行 `tree_sync.py handoff`。
5. 更新 doc 记录和日报，给出待提交清单与建议的提交信息，并列出还没在实板上验证的项。

## 7. 下一轮

- 新一轮的 receiver = 这一轮的 target：版本号保持不变，只改范围和 `OTA_TRIAL_*`，再走 §2。
- 同事交来的新代码：先 `tree_sync.py scan` 和 `merge`（以实板验证版为底；受保护文件不会被拉进来），`ota_guard.py` 自动查交接清单规则；人工再核对：不改 `ota_*`/`business_*`/`update.lua`，不新建目录，重启前先查 `reboot_allowed()`，控制空间占用，UART1 只在 `uart_app` 注册。
- 11-02 OTA 后 CAT1 已用 23 块（多出的是 OTA 历史），**下一轮发起前要先清**，否则空间不够。
