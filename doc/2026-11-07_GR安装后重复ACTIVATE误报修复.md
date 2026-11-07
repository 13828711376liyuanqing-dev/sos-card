# GR 安装后重复 ACTIVATE 误报修复

SAM | 2026-11-07 +08:00 | 源码修复与主机回归记录

## 结论与交付边界

已修复 GR 安装后重复 ACTIVATE 沿用旧源版本校验而误报 stage11 / activation_validation_failed 的源码路径。主机真实端口和 Boot 状态机回归通过；尚未执行 Keil F7、签名、烧写或本轮实板验收。设备当前成功版本仍为 1.5.14/b18，本轮旧 AXF/HEX 不包含修复。

未生成压缩包；未修改 CAT1、Boot 源码、Flash 布局、电源门槛、用户数据区或 Keil 工程配置。先前版本管控方案仍待用户评估，没有借本次修复执行分支、标签、提交或发布操作。

## 故障证据与根因

2026-11-07 的 1.5.13/b17 → 1.5.14/b18 实板 OTA 中，新 GR 已运行且 Boot 为 TRIAL，旧任务仍 INSTALL_PENDING。CAT1 再发 ACTIVATE 后，端口却要求当前 A 的版本等于旧 source 1.5.13，记录 stage11。原始证据：`logs/ota_push_1513_1514_20261107/post_install_probe.json`、对应 SRAM；精确首错 raw16 和时间线见完整复盘。

交换完成后的 A 是新目标、B 是回退旧镜像；此前校验分支始终把 A 当旧源、B 当新候选。仅放宽版本比较仍会错误验证 B，且可能再次激活或复位，因此必须区分安装前和已经运行目标两种收据。

## 修改文件和行为

| 文件/函数 | 修改前 | 修改后 |
|---|---|---|
| `ble_app_uart_c/Src/user/ota/yp001_ota_port.c`，install_check / install_check_step | 所有 PREPARED、INSTALL_PENDING 使用安装前 A/B 假设 | 仅 INSTALL_PENDING 且 Boot TRIAL/CONFIRMED 生成 installed 收据；认证当前执行 A 与 Boot.new 完全一致、Boot.old/source 和 Boot.new/target 版本匹配 |
| 同上，第二阶段验证 | 认证 B 的候选包 | installed 收据认证 A 的完整原生包哈希和签名，并对比前一阶段执行身份；普通路径继续验证 B |
| 同上，install_prepare | 接受有效安装收据 | 明确拒绝 installed 收据，不允许其重新准备安装 |
| 同上，install_commit | 进入激活和 reset_armed 路径 | 复核完整持久 owner、进度、owner/B/Boot generation 与 Boot old/new 身份后，installed 收据仅返回成功；不写日志、不再次激活、不设置复位计时、不触碰健康观察状态 |
| `tools/ota/test_gr_install_receipt.c` | 缺少真实交换后的重复激活用例 | 增加真实 Boot prepare/activate/resume/trial 后的重复请求、CONFIRMED、身份拒绝、收据失效和健康连续性用例 |
| `tools/ota/test_gr_port.c` | 原生包验证模型仅支持 B，仅读哈希首字节 | 主机模型支持交换后的 A，检查全部 32 字节期望哈希；不代表硬件密码学验收 |

协调器既有精确 job/hash/target/version/epoch 解析和 `safe(true)` 保留，匹配重复请求经原有短租约返回 GRANT。它只确认本次 GR 激活已发生，不代表健康通过或整机 OTA 完成。CAT1 仍一次性激活；SPENT 规则未放宽。

## 需求对应及安全边界

- F-031：安装前完整校验和提交安全门不变，按用户最新要求保留有效电量 ≥50% 或健康 USB；技能中的历史 70%/充电要求不覆盖本次明确裁决。
- F-032：TRIAL 不能由重复激活升级为成功；仍须实际健康观察、Boot CONFIRMED 和独立结果处理。
- U-OTA-01：owner/epoch、串行、原生 CAT1 次数控制不变。
- U-DATA-01：仅易失收据新增标记，没有改变用户区或持久记录格式。
- PREPARED、未提交 Boot PREPARED、Boot INSTALL 丢 ACK 的原路径仍执行原有认证/激活；REVERTED 不作为成功重复激活接受。
- 收据须按每个命令重新建立；owner、完整进度、B generation 或 Boot generation 变化使其失效；TRIAL 收据不能跨健康确认后的 journal generation 使用。
- 不主动清空健康观察。既有安全规则仍有效：真实业务异常或采样间隔超过 3 秒会重新开始 120 秒观察。主机用例以及时采样验证连续性，未证明真实密码运算/串口租约耗时不会触发重新计时；实板必须观察。

## 验证

1. 修复前先新增真实 Boot 交换后用例，运行 `python tools/ota/test_gr_install_receipt.py` 失败（首个 installed 激活验证失败），保留 `logs/gr_duplicate_activate_fix_20261107/red_before.log`。
2. 修复后同脚本以 C99、Wall/Wextra/Werror 编译实际 port/Boot/receive/wire，测试通过。覆盖 TRIAL 与 CONFIRMED 重复确认、无 owner/Boot 改写、无额外 reset、epoch 不匹配、CRC 有效且进度完整的持久 hash/source/target 不匹配、运行镜像损坏、原生校验拒绝、TRIAL 收据被 CONFIRMED generation 撤销、健康满 120 秒才确认。错误哈希用例明确到达 stage12，避免仅因进度丢失而假通过。
3. 同套保留初始安装、未提交 PREPARED 恢复、INSTALL 完成 ACK 丢失、收据撤销、写失败、49/50%、USB/未知电量/拔 USB 和健康重新计时回归。
4. `python tools/ota/test_gr_activation_stages.py` 通过：实际协调器的只读分阶段、初始/恢复、稳定等待、失败、超时、报警、授权丢失。该套使用端口模型，与真实端口套共同提供主机证据，不能冒充完整硬件集成。
5. 会话内独立对抗审查未发现生产修改缺陷；审查指出负向测试通过 store 改 owner 会丢进度，已改为请求身份不匹配及明确的主机 CRC 有效记录故障注入，验证实际认证分支。

## 已验证 b18 的本地保护

修改前已保留 7 个文件：受影响的三个 C 文件、现有 AXF/HEX/MAP 和版本头；原相对目录保持在 `logs/gr_duplicate_activate_fix_20261107/before/`。复制后逐一 SHA256 比对，清单 `before/manifest.json`。它是本次源码修复的局部安全副本，不是完整发布可复现性声明，也不等于已经实施长期版本管控方案。

## 强制检查项

| 检查项 | 结果/证据 |
|---|---|
| 修改前工作区和目标文件检查 | 已只读 git status；保留全部既有未提交变更；从当前文件复制并校验 7 个文件 |
| 主工程/交付副本差异检查 | 不适用：用户取消自动同步/编译；仅主工程源码修改 |
| 硬件/显示协议核对 | 不涉及引脚、电源参数或显示修改 |
| 代码时间/修改人/原因注释 | 新增/变更逻辑附近 SAM、北京时间、原因注释 |
| 运行、失败、超时、复位及回退 | 上述主机回归；没有放宽回退、确认或重试次数；实板待验 |
| 清理规则/缓存保护 | 未清理、未改清理脚本；Objects/.d、输出路径和原工程保留 |
| 本轮中文修改说明 | 本文件；完整复盘追加当前源码修复状态，原实板证据不改写 |
| 主工程 Keil 6 编译 | 未执行；旧产物不能代表新源码。后续仍原工程 F7 增量 |
| 交付工程 Keil 6 编译 | 不适用：用户取消自动同步/编译 |
| 实板测试及未完成项目 | 尚未烧写本轮修复；待唯一新版本构建和真实重复 ACTIVATE 验收 |

## 后续实板验收

发布前必须分配唯一新版本/build，不能覆盖已经验收的 1.5.14/b18 身份；不得直接将本轮新源码产物冒充旧 b18 包。按原 Keil 工程 F7 流程准备匹配签名和配套指纹，Boot 逻辑未变，不要求重编 Boot。

实板测试开始前先确认 GR 正常运行、CAT1 真实启动。覆盖真实新版本安装后的同任务重复 ACTIVATE（TRIAL 和 CONFIRMED）、错误身份拒绝、无额外重启、健康观察后确认/结果串行推进，核对首错和最终 outbox。未完成这些测试前，只能声明源码修复及主机回归通过。
