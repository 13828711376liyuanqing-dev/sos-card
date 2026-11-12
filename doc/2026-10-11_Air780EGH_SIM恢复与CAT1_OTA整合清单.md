# Air780EGH SIM 恢复与 CAT1 OTA 整合清单

时间：2026-10-11（北京时间）｜修改人：SAM｜唯一源码入口：`D:\CODEX\sos-card\Air780EGH`

本轮在当前项目源码内实现已确认值得借鉴的机制。旧 `cat_1` 只用于此前的只读差异分析；没有从旧目录复制、合并、加载代码或底包。目标是先建立可观测、可重试且相互避让的链路；参数和硬件行为留待实板调优。

## 已整合

| 功能及位置 | 修改前 → 修改后 | 原因及主机验证 |
|---|---|---|
| 启动网络观察器：`main.lua` 的 `require"netdrv_device"` | 文件存在但未加载 → 启动时加载 SIM、注册和 IP 观察模块 | 让下述事件处理实际运行；Lua 语法检查覆盖 |
| SIM 状态与自动恢复：`netdrv_device.lua` | 状态上报不完整 → 启动主动读取 IMSI，处理 `SIM_IND` 的 RDY/NORDY/SIM_PIN，尝试 `mobile.setAuto(10000,0,5,false,60000)`，不可用或异常记录日志 | 卡拔出时立即清除旧注册状态并发布 `SIM_LOST`；主机桩测试覆盖拔插与恢复配置。IMSI 仅用于就绪判断，不输出号码 |
| 注册/IP 观察：`netdrv_device.lua` | 旧观察器未运行 → 5 秒查询一次 `mobile.status()` 的原始数值，处理 `IP_READY`/`IP_LOSE` 并经 `[NET_ENV]` 上报 | 给汇顶侧提供状态证据；主机桩测试覆盖状态变化。原始注册值的实际含义及 1/5 对应关系须按目标底包实测确认 |
| 业务会话回收：`mqtts_main.lua`、`sip.lua` | SIM 拔出可能保留旧会话 → `SIM_LOST` 触发 MQTT 现有关闭/重连路径和 SIP 现有错误清理路径 | 避免旧连接掩盖拔卡；主机桩测试已覆盖事件触发，重订阅和重新注册尚待实板 |
| CAT1 自身 OTA 调度：`update.lua` | 仅开机检查，无法要求重试，结果易误判 → 开机排队一次；支持 `FOTA_CHECK`、`FOTA_STATUS` 和 `CAT1_FOTA_REQ`；运行锁防重复，无 IP 或 GR5526 DFU 忙时等待 | 主机桩测试覆盖开机、重触发、等待、重复拒绝、异常结果。沿用当前项目 PRODUCT_KEY |
| FOTA 结果处理：`update.lua` | `ret=4` 可能被误报为最新 → 上报 `NO_UPDATE_OR_ERROR`；`ret=0` 上报下载成功待重启，500ms 后调用重启 | 测试覆盖结果分支与定时重启。500ms 仅是 UART 排空机会，未证明上位机已收悉或新版本已安装 |
| 双端升级互斥：`dfu_transfer.lua` | CAT1 FOTA 与 GR5526 下载/传输可能交叉 → DFU_DL/DFU_START 在 FOTA 运行时拒绝；重复 DFU 操作拒绝；DFU_START 排任务前占用传输状态 | 主机桩测试覆盖双向互斥与排队竞态；不代表汇顶 OTA 全链路已通过 |

主机验证命令：`C:\Users\SamLi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tools\cat1_antenna\tests\cat1_integration_tests.py`，结果 6 项 PASS。以同一 Python 运行 `tmp\check_cat1_lua_syntax.py`，用本地 Lupa 对 `Air780EGH` 全部 22 个 `.lua` 执行 `load` 语法检查，0 错误。以上是源码/桩验证，不是模块底包或实板验证。

## 保留和未引入

| 项目 | 本轮处理 |
|---|---|
| 声音、TTS、SIP 业务接口、UART 分帧、当前音频引脚和供电控制 | 保留当前项目实现；只给 SIP 增加拔卡清理事件，未采用旧音频/串口实现 |
| GR5526 DFU Host | 保留当前传输实现，只加与 CAT1 FOTA 的互斥；未声称镜像接收、校验、刷写、启动确认已完成 |
| 卡座 DET GPIO/WAKEUP2 与飞行模式切换 | 未接入；YP001 DET 引脚、有效电平、边沿和目标底包能力尚未核实。当前热插拔依据 `SIM_IND` 和底包自动恢复 |
| 双卡轮换、自定义 APN/频段、旧项目底包与 PRODUCT_KEY | 不引入；与当前单卡硬件及产品配置无关或尚无依据 |

## 后续优化与实板验收准备

1. 核对原理图卡座 DET 到 Air780EGH 的实际连接、有效电平及去抖；再决定是否加入硬件中断。避免与 `mobile.setAuto` 同时触发飞行模式或切卡。
2. 用当前目标底包和已接 4G 主天线实测：上电供电/串口 → SIM RDY → 注册状态达到允许值 → IP_READY → MQTT 重连和订阅 → SIP 重注册/通话。分别记录无卡、PIN、拔卡、插卡、弱信号、拒绝注册和长时无网。
3. CAT1 OTA：补请求超时/重试节流、目标版本与重启后版本核对、断网及断电恢复、UART 最终确认。`NO_UPDATE_OR_ERROR` 需用底包日志进一步分类。
4. 汇顶 OTA：先补齐并实测 GR5526 镜像接收、完整性/来源校验、DFU UART 应答、写入后启动确认及失败回退；再测试与 CAT1 FOTA 互斥和 SIM 热插拔交叉场景。
5. 本轮未下载/烧写设备，未做在线注册、通话、声音或双端 OTA 实板验收；旧 AXF/HEX 不能证明新 Lua 已运行。

## YP001 代码修改强制检查项核对

| 检查项 | 结果/证据 |
|---|---|
| 修改前工作区和目标文件检查 | 已检查 `git status --short` 和目标 Lua；工作区已有大量用户改动，均保留 |
| 主工程/交付副本差异检查 | 本轮未修改两份 GR5526 源码；修改前两份 `bsp.c` 与 `YP001_GR5526.uvprojx` 对应 SHA256 一致，未做目录覆盖 |
| 硬件与失败/超时/复位路径 | 未写未经核实的 DET 引脚；SIM 拔出清状态、FOTA 无 IP/DFU 忙等待、错误返回可见；OTA 安装后确认仍待补 |
| 代码时间/修改人/原因注释 | 本轮修改点附近均标 `SAM | 2026-10-11 09:24 +08:00` 及原因 |
| 改动边界及两份同步 | 仅改 `Air780EGH` 中与目标相关 Lua；GR5526 主/交付副本无本轮修改，故无需同步 |
| 清理脚本及 Keil 输入 | 未改、未运行清理 BAT 或脚本；未动 `.sct`、工程配置和下载算法。两份 AXF/HEX 因本轮重新编译而更新，并非被清理 |
| 本轮中文修改说明 | 即本文件，列明改动、验证和实板缺口 |
| 静态/主机测试 | 22 个 Lua 文件语法检查通过；6 项主机桩测试通过 |
| 主工程 Keil 6 编译 | 本轮执行 `UV4.exe -b YP001_GR5526.uvprojx -t YP001_GR5526_AC6`；`logs/cat1_integration_keil_main_20261011.txt` 显示 0 Error、0 Warning，9:38 新生成 AXF/HEX。Keil 不编译 CAT1 Lua |
| 交付工程 Keil 6 编译 | 同一命令在交付副本 `Keil_6` 独立执行；`logs/cat1_integration_keil_delivery_20261011.txt` 显示 0 Error、0 Warning，新生成 AXF/HEX。Keil 不编译 CAT1 Lua |
| 实板测试及未完成项目 | 未执行；见上一节。不得将主机测试或 Keil 编译等同实板功能通过 |
