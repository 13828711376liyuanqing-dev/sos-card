---
name: yp001-ota-bench-runbook
description: YP001 台架整机 OTA / 后台推送 OTA 的实战流程与纪律（2026-11-06 实板成功 1.5.10→1.5.11 后整理）：CAT1 保电、Luatools 刷机坑、CAT1 空间（ble.ini、两步法）、下载被服务器掐断的诊断方法与结论（改用系统 HTTP 库）、GR 遗留授权取消、发令与监视写法、后台推送验收流程（升版本、推送对象填 IMEI）、GR 确认新镜像要等静止、成功后核对与收尾。做台架 OTA、后台推送验收、OTA 卡住（RECOVERY_HOLD 很久）/COMPONENT_SPACE/HTTP_NATIVE_OVERFLOW、CAT1 总掉电时先读这个。**11-08 起本技能同时是统一入口**：每项代码合并/修复的 OTA 影响红线（含字库通道）、activation_validation_failed/TRIAL_SCOPE/SPENT/G0 判读、同版异包、整板恢复到干净起点（已并入原 `.codex/skills/yp001-ota-recovery`，副本在 references/）。
---

> **2026-11-10 起 CAT1 出厂即可接收 OTA，不再有"接收端"、冻结 MD5 和写死的版本范围。** 本技能里关于接收端、`OTA_TRIAL_MD5`、`OTA_TRIAL_SOURCE/TARGET`、`USB_IMPORT` 接收端的内容只适用于 11-09 之前的旧固件。新的标准流程见技能 `yp001-ota-factory-ready`。

# YP001 台架 OTA 实战流程（11-06 实板成功：主动下载 1.5.10→1.5.11、后台推送 1.5.11→1.5.12）

SAM | 2026-11-06 | 与 `yp001-whole-ota-run`（流程骨架）、`yp001-space-budget`（红线）配合；本文是那天踩过的坑和对应做法。设备 GR=COM30（115200），CAT1 日志口 COM21/COM23，IMEI 864317088496529。

## 0. 铁律（每条都踩过）

| 铁律 | 原因 |
|---|---|
| **等待期间一直保电**：`YP_GR_PORT=COM30 python tools/ota/bench/keep_cat1.py 90`（只用 COM30，只在最后一次电源事件是 off 时才上电） | GR 在 CAT1 空闲约 60 秒后断电；`[OTA_HOLD] 1` 只在设备收到 OTA 命令后才生效；断电期间后台推送会丢（MQTT 不存离线消息） |
| **发令和保电不能有空档**：同一个 Python 会话里"`at FOTA_STATUS` 确认在线 → 没电就 `cat1_power on` + `cat1_power key` → 立刻 `cat_at OTA_TRIAL=<url>`" | 先停保电再另起命令，空档里被断电，命令没回复 |
| **OTA 开始后不要再开保电脚本** | 设备自己保电，脚本会干扰串口 |
| **刷 CAT1 前停掉 `cat1_vuart_log.py`**（占 COM21/COM23），Luatools 不要选 COM30 | 抢口，刷机失败 |
| **Luatools 添加目录前先清空文件列表** | 列表里已有同名文件会弹"文件夹中存在超过3个重复文件名，已终止添加"，**静默沿用旧文件，等于没刷进去**。刷完用日志里是否出现新代码输出确认 |
| **保电脚本的"断电"判断只看最后一次 rail 事件** | 看缓冲区里任何历史 `rail_request=off` 会把在线的 CAT1 误上电重启，MQTT 掉线，推送丢 |
| **OTA 期间不要碰板子、不要动线、尽量别用 J-Link 读** | GR 确认新镜像要求**连续 120 秒无活动**，而且"静止"要**连续 5 分钟没有检测到振动**（`YP_MOTION_STILL_MS`）；动一次就重新等 5 分钟 + 120 秒（11-06 推送那次为此多等了 15 分钟）。J-Link 读会让 GR 内核暂停，也算观察空档 |
| **工具要独占 COM30 的步骤（一键工具读空间等）会让保电脚本停下** | 这段时间 GR 会把 CAT1 断掉；跑完立刻重新上电保电，或让工具前先确认在线 |
| **监视过滤不要放 `FAILED`、`COMPLETE`** | `ACTIVATION_RECHECK_FAILED` 是正常等待、`COMPLETE_PENDING` 每 10 秒一条，会刷屏 |

## 1. CAT1 空间

- 读：`cat_at OTA_FS`（根目录和已用块数）；`cat_at OTA_FS=/log`、`OTA_FS=/ble` 看目录里的文件。OTA 进行中 GR 拒绝串口命令（`[OTA] UART change denied`）。
- 需要 ≥ GR 签名镜像 + 32768（红线）。11-06 实测的真正占用者是 **`/log/ble.ini`（BLE 定位缓存）涨到 75 KB**（CAT1 反复断电离线时只写不上传）。
- **规则：OTA 发令前一并清 `/log/ble.ini`**（`update.lua` 的 `LOG_FILES`，输出 `[OTA] LOG_CLEARED n` 包含它）。字库下载那条流程仍只清 app.log、保留 ble.ini。
- **两步法**（打包要真实空间读数，读数要先清空间，清空间要刷机）：
  1. 刷只带一次性清理块的接收端（`oneclick` 的 `add_cleanup`；标记名用新的，已存在的标记不会再执行）→ 开机后读真实空间。
  2. 读数 ≥ 红线再 `oneclick.py run`，生成最终包和接收端。
  - 空间读数里还有会在 OTA 发令时被清掉的东西（如 ble.ini），可用"实测可用 + 实测文件大小"传 `--free`，**必须在报告里写明口径，发令前再真实读一次确认**。
- 取消 `OTA_PRUNE` 的期待：它只清 OTA 自己的历史（常常 0 字节）。

## 2. 下载失败的诊断方法（HTTP_NATIVE_OVERFLOW / HTTP_PORT_ERROR）

先分清**推送入口**和**下载**：用主动发令（`cat_at OTA_TRIAL=<url>`，同一个地址）对照。主动也一样失败 → 与推送无关。

`HTTP_PORT_ERROR` 是任务上下文问题：平台入口不能在 MQTT 回调里做要等待的 HTTP（已改为 `sys.taskInit`，并提前 `[OTA_HOLD] 1`）。

`HTTP_NATIVE_OVERFLOW` 在设备日志里加一行 `[OTA_HTTP] RX success= n= limit= closed= fault= tx= ms=` 才能分辨原因（11-06 这次：请求发出后 0.5 秒连接被关闭，或收到 200 头但响应体 6 秒不来）。

**排除顺序**（11-06 逐项试过，全部无效）：SIM 卡、推送/主动、User-Agent、Accept-Encoding、Connection、HTTP 版本、先 HEAD 再 GET、读取速度、域名解析（直连 IP）、去掉地址参数、官方平台头（BusinessId/Timestamp/AppId/Request_node_ip）。

**判决性对照**：同一台设备、同一张 SIM、同一个地址，**系统 HTTP 库**（`http.request(...).wait()`，`NAME_URL` 字库下载用的）能整文件下载，原始 socket 不行；同事在自己网络用 `tools/ota/device_like_probe.py`（只用标准库，发设备同款字节）20 次全 206。**结论：问题在设备原始 socket 与这台负载均衡（QingCloud ELB，`test-ccrcapp`）之间，不在后台、请求内容或网络。**

**修复**：`Air780EGH/ota_http_range.lua` 分段下载优先用系统 HTTP 库（设备上 `http` 是 **userdata**，别写 `type(http)=='table'`），检查（206 / Content-Range / 长度 / ETag）不变；流式读取和无库环境（主机测试）走原始 socket。测试 `tools/ota/test_http_lib.py`。

**诊断版做法**（改请求、不改后台）：复制接收端源码到新目录改 `ota_http_range.lua`，`Cat1UsbImport.exe --source … --out …` 生成，冻结的 MD5 不变所以**后台包不用重新上传**；诊断行用 `_G.ota_diag`；用变量 `_G.ota_http_variant`（`cat_at HTTP_VAR=` 切换）可以不刷机连试多种请求。生成后用 `grep -c <新字符串> ota_http_range.luac` 确认确实编进去了；补丁匹配不到时 `assert t.count(old)==1` 会拦住，不要用没验证过的目录。

## 3. GR 遗留授权（owner DOWNLOADING）

OTA 卡在 `GR_GRANTED / ARMED / COMPONENT_SPACE`：GR 的 owner 记录 `DOWNLOADING`、B 槽标记占用但 `durable 0`（没写任何数据）。处理：刷清理接收端让 CAT1 一侧丢掉任务 → `cat_at OTA_GR_CANCEL_EMPTY`（返回 `CANCELLED cancelled_before_install COMPLETE`）；B 槽不全空才需要 J-Link 擦 B 槽（先问用户）。核对：`python tools/ota/gr_ota_probe.py`（只读，两条 owner 记录取代数大的）。

## 3.4 合并/修复的 OTA 红线与故障判读（并入 yp001-ota-recovery，用户 11-07/11-08 指定）

**权威原文**在 `references/`（从 `.codex/skills/yp001-ota-recovery` 复制，Codex 侧更新后要重新复制）：`codex_ota_recovery_SKILL.md`（红线全文）、`ota-impact-review.md`（每项修改的影响审查表）、`operating-notes.md`、`case-index.md`。下面是我执行时的要点，冲突时以原文和用户最新指示为准：
1. **每项合并/修复先做 OTA 影响评估**并写进 `doc/YP001_代码修改强制检查项.md`：父版本、精确 diff、候选版本/build、影响链（IRQ/BLE/UART-DMA/按键报警通话/电源/内存/Boot/NVDS-FS-KV/版本打包）、主机专项、回退点。OTA 目录没改也要沿调用方和共享资源查。
2. **以验证基线为底做 delta**，不整文件替换、不猜来源；基线 = 1.5.14/b18（冻结 R2）及其后经真实 OTA 的版本（现 1.5.22/b26 单任务回归通过，范围见 `doc/2026-11-08_双端OTA实测_1.5.21到1.5.22_记录.md`）。逐功能记 base/delta/candidate。
3. **同版本/build 只能对应一份内容**，冻结目录不覆盖；不用"同版本不同字节的清理接收端"（11-06 的 diag 接收端属此类）。
4. **字库通道与 OTA 同为红线**：residentNameMsg/NAME_URL/缺字补发的 HTTP/MD5/CRC/Seq/原子提交；OTA 在途字库到达、字库在途 OTA 到达的资源让出与恢复（P0 待修）。
5. **准入要绑定**：接收端实际版本、冻结 MD5、来源/目标范围、旧试装票、GR owner job/hash/epoch 一起核对；后台受理不替代票据范围；成功一次后"连续再升一版"单独验证。
6. **控制事件降权**：OTA 全程忽略运动/普通按键/找人/休眠及其采样失鲜，不等 60 秒/5 分钟静止、不重置 120 秒健康计时（生产台架一致）；真实报警/通话、链路、实际新鲜供电、签名/事务/数据保持继续判定。供电规则：有效电量 ≥50% 或健康 USB（覆盖旧 70%+充电）。
7. **判读**：`activation_validation_failed` 且新 GR 未运行 → 先查预校验/入口门控/首错，不直接怪 HTTP 或签名；新 GR 已运行后重复 ACTIVATE 报 stage11 → 已知误报（b18 原样仍有），核对同 owner、Boot TRIAL/CONFIRMED、old/new 版本，不清票重来；`G0` 单样本不证明推进，看同任务≥2 个有时间顺序样本（但 D 完成后到 PREPARED 之间约 5 分钟 G0 是正常预校验）；io2 存在先匹配当前 job.id；`AUTO_FAULT` 历史与当前分开；IDLE/outbox0 只证设备侧收尾，不证平台页面已收。
8. **失败先保护现场**：先存 owner/job/hash/epoch、串口/设备/后台记录，再动手；不强制 reset/断电绕过事务门控；回退不回退用户最新数据，不整片回写 Flash/FS/KV；`CANCEL_EMPTY` 只用于 durable=0 的空 owner，不泛用到 PREPARED/full B。恢复前先判当前票归属、native 和持久 owner，昨日方案不自动套今日。
9. **晋升/交付**：隔离候选可连续合入已审查功能（每项独立差异+回退），整批统一 F7 + 真实双端 OTA；对应实际镜像的双端 OTA、字库链路、双向并发、数据保持都有实板证据后才晋升稳定或标"已验证"。规则文本、主机专项、自动门禁、实板验收分别记录各自范围，缺项写 PENDING。
10. **不要**用 `--reviewed-ota-change/--yes-attest` 一类整批声明替代逐项评审；评审声明按精确 manifest，由人确认。

## 3.5 整板恢复到"干净起点"（11-08 实板成功：21→22 从 TRIAL_SCOPE 卡死恢复后一次推送成功）

适用：GR 有遗留 owner **且** CAT1 trial 是 `SPENT`（信标 `GR_GRANTED nil/0 SPENT … TRIAL_SPENT`，`cat_at` 回 `[OTA] UART change denied`）。**不要**做"同版本不同字节的清理接收端"（违反同版本唯一内容红线），整板重刷：
1. **先只读取证**：`PYTHONIOENCODING=utf-8 python tools/ota/gr_ota_probe.py > x.json`（不设编码会 gbk 报错；PowerShell 重定向的 JSON 带 BOM，读用 `utf-8-sig`）；GR CLI 在 **COM30**（不是 COM26），先 `python -m serial.tools.list_ports -v` 确认。
2. **GR**：`tools/gr_release/GR_JLink_Flash/yp001_gr_jlink_flash.py <签名.bin> --yes --keep-name --port COM30`，烧"板上当前应有的版本"（本次 1.5.21/b25，先核对签名镜像 sha256 与记录一致）。读回要出现 `Boot 日志/owner 已清空`、`B 槽已清空`。
3. **CAT1**：Luatools 先"删除全部"再加 `USB_IMPORT` 目录，**必须勾"清除KV分区"和"清除FS分区"，点"下载脚本"前让用户截图确认两个勾**。不勾 = 旧 `yp001_ota_state_*`/`yp001_cat_fota_*` 保留，信标仍 SPENT（本次白刷两次）。清 FS/KV 的代价：绑定号码、MQTT/SIP 参数丢，要后台重发；GR 姓名字形不受影响。
4. 验收干净：信标 `IDLE nil/0 nil … S nil`；`cat_at FOTA_STATUS` 为 `IDLE / OUTBOX=0 / TRIAL=nil`；`OTA_FS` used≈9 块；GR owner 两页 erased。
5. 全程保电脚本在跑；要读 COM30 时 **Stop-Process 杀 keep 脚本 → 同一命令里读 → 立刻重启**（Git Bash 没有 pkill，用 PowerShell `Get-CimInstance Win32_Process` 按命令行杀）。
6. 之后照第 4 节：`check_url.py` → 开 `cat1_vuart_log.py` + Monitor → 用户推送（IMEI）。

**G0 长预校验**：D 下载完到 `PREPARED` 之间 GR 会在 `G0/总数` 停约 5 分钟（PREPARING/PAUSED 往复），这是正常的 GR 预校验，没有 ERROR/DENY 就别慌、别读 GR。信标顺序：V → D → G0（约 5 分钟）→ PREPARED/WAIT_ACTIVATE（CAT1 USB 断开）→ RECOVERY_HOLD → IDLE RUNNING → CAT1 D → INSTALLING → COMPLETE_PENDING → IDLE，全程约 16 分钟。

## 4. 一次完整的台架 OTA

1. 预检：CAT1 `IDLE`、`OUTBOX=0`、空间够（第 1 节）、接收端是新的、`ble.ini` 大小已知。
2. `python tools/ota/check_url.py url.txt --package <zip>` 通过（整包 MD5、Range、设备同款 Lua 读取器、签名、GR/CAT1 摘要）。
3. 开日志 `cat1_vuart_log.py` + 监视（只报阶段变化和异常，别含 FAILED/COMPLETE）。
4. 同一会话 ensure_up → `OTA_TRIAL`（期望 `OTA_HOLD` → `LOG_CLEARED` → `WAIT_GR`）。
5. 正常节奏约 15 分钟：`DOWNLOAD_PENDING`（V=字节）→ GR 暂存 `G375016/375016` → CAT1 断电约 50 秒 → `RECOVERY_HOLD ACTIVATION_RECHECK_FAILED HEALTH_IDENTITY`（正常）→ `D…/189298`（CAT1 包）→ `INSTALLING` → `COMPLETE_PENDING … RESULT_CHALLENGE_PENDING` → `IDLE`。
6. 核对：`gr_ota_probe.py`（owner `COMPLETE/CAT1/<目标>/success`）、`fw_version`（GR 版本和 build）、`cat_at AT_INFO`（CAT1 版本）、`FOTA_STATUS IDLE`、MQTT 连接。
7. `python tools/ota_oneclick/oneclick.py done`（记设备版本和验证基线）→ `python tools/wrapup/wrapup.py`（同步 + 清理，同事有新改动会停下，先 `tree_sync.py pull/merge`）。

## 4b. 后台推送验收（11-06 17:00 受理，升级跑完）

1. **推送要比设备现版本更高**：设备已是 1.5.11 就要出 1.5.12。只改版本号也行：`YpVersionTool.exe set --header <yp001_fw_version.h> --lua <main.lua> --version 1.5.12 --build 16`（两端必须同版本同 build，改前自动备份到 `logs/firmware_versions/`）→ **用户在 Keil 里 F7 编译 GR** → `YpVersionTool.exe check --gr <hex> --cat1 Air780EGH --header <h>` 核对 HEX 里的版本标记。
2. `oneclick.py run`（读设备真实空间，生成 `YP001_<旧>---<新>_FIRST.zip` 和接收端）；用户**上传包 + 刷接收端（冻结了新包 MD5）**；我对地址跑 `check_url.py`。
3. 后台推送的字段：`CurrentVersion=YP001_1.5.11`、`TargetVersion=1.5.12_FIRST`（设备端 `ota_runtime.lua` 已兼容这两个前后缀）、`Address`（带 appId/signature/md5）、`Md5`、`Time`、`MsgType=otaMsg`。
4. **推送对象必须是设备的 IMEI（`864317088496529`），不是 IMSI（SIM 卡号，换卡后会变）**。11-06 用户先填了 IMSI，设备 `recv=0`，一直没收到。设备自己上报 `IMEI=…`、`IMSI=…`，不确定时对一下。
5. 等待推送时保电（`keep_cat1.py`）+ 开日志和监视；**设备一收到（`LOG_CLEARED` / `OTA_RX ACCEPTED`）立刻停保电脚本**，之后设备自己保电。
6. 判断收到了没有：CAT1 的 `MQTT_STAT … recv=N recv_bytes=350`（每条 otaMsg 约 350 字节）。`recv` 不涨 = 消息没到设备（对象填错、掉电、MQTT 重连期间）。
7. 四项证据：`[OTA_RX] ACCEPTED`、`otaReplyMsg`（回复）、GR/CAT1 两段升级（`gr_ota_probe` owner `COMPLETE/CAT1/<目标>/success`）、`otaResultMsg`。
8. 11-06 实测节奏：受理 → GR 暂存约 5 分钟（377064 字节）→ GR 安装 → **等静止 + 120 秒观察（动过板子就是 10 分钟以上）** → CAT1 下载 189 KB → 安装 → 完成。`RECOVERY_HOLD … HEALTH_IDENTITY` 很久不走：用 `yp_motion` 看是不是 `state=moving`（只读 CLI；`business status` 看 `link/net`）。

## 5. 工具

`tools/ota/bench/`：`keep_cat1.py`（保电）、`boot_then.py`、`start_ota.py`、`http_variants.py`（诊断版的请求方式试验）；`tools/ota/`：`check_url.py`、`device_like_probe.py`（给别人在别的网络跑）、`gr_ota_probe.py`、`test_http_lib.py`；`tools/ota_oneclick/oneclick.py`；`tools/wrapup/wrapup.py`。

## 6. 还没解决的

- 后台推送：受理、下载、升级已在 11-06 通过（见 4b）；`otaResultMsg` 回报到平台那一步以后台看到为准。
- **需求（用户 11-06 提出，待实现）：OTA 期间运动、按键、找人、休眠这类控制事件降权，不再拖住确认；报警、通话、链路保留**。分析和方案见 `doc/2026-11-06_需求_OTA期间控制事件降权.md`，要在合并同事 GR 代码之后做（同在 `yp001_business.c`/`bsp.c`）。
- 同事在版本库另一侧的改动待合并：GR 8 个文件加 6 个冲突，CAT1 8 个文件加 3 个冲突，`business_core.lua` 把 SOS 发送注释成 "GR send sos"；"四类下行消息没到 GR"（`doc/2026-11-06_CAT1下行四类消息未到GR_检查结论.md`）在合并后做。
- 设备下载请求按平台 header 标准（Timestamp/BusinessId/AppId/Request_node_ip）带头；AppId 要后台分配，不能借用 `ccrc-customer-personupload`；Timestamp 依赖 NTP。
- 现场 CAT1 平时被 GR 关电，后台推送能否及时到达是产品设计问题。
