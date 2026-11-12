# R6 OUTBOX_FULL：代码根因与MQTT修复交付

SAM | 2026-10-26 +08:00 | 本轮已取得实板首因并复现接口错配。当前软件修复/冻结验证完成，尚未部署新MQTT集合，OTA未完成。

## 最新实板进度（覆盖下方待部署状态）

SAM | 2026-10-26 +08:00 | 后续已经沿原R6一次授权接续：MQTT实板关闭、R6 epoch4、完整432328B候选采用、GR已ACK1536B；随后GR FIFO溢出0x02并在token9返回静默拒绝，CAT PAUSED/TRIAL_SPENT，已停采、未重试。最新证据与剩余问题以`2026-10-26_R6实板推进1536字节与GR溢出证据.md`为准；下方“尚未接续”属历史。

SAM | 2026-10-26 +08:00 | 用户已完成MQTT修复下载；实际Luatools生成52成员匹配，524256有效字节。GR CLI/明确rail-on ACK/CAT真实版本回应均通过，无需PWRKEY。连续两次查询均为IDLE、OTA_OUTBOX=0；旧OTA_REASON=OUTBOX_FULL仍是历史首因，未清历史记录。**本板回执队列阻塞已解除**，不是仅主机测试通过。

原同步采集缓存1793007806已另存。新一轮准备启动DL32时，电脑控制接口返回`computer-use request budget exhausted`；已请用户按F1启动，尚未发送本轮R6恢复命令，也未消费试验。收到真实采集启动证据后，直接沿原批准一次R6接续，不再次询问授权。当前接续文件目录：`logs/r6_handoff_20261026/mqtt_live`，progress.json、pre_resume.txt、mqtt_queue_recovered.txt。

## 本轮实际推进

| 阶段 | 明确结果 | 证据 |
|---|---|---|
| CAT下载身份 | 52成员全部匹配，524286有效字节、工具填充2字节 | admission_live目录；实际Luatools script.bin解包核对 |
| 供电/启动 | GR正常1.0.2；明确rail_request=on code=0x0000；CAT真实版本1.0.2/build3 | power_confirmed.txt、cat_version.txt；未发PWRKEY |
| UART准备 | uart_idle=true，uart_faulted=false，空闲40960字节 | pre_resume.txt |
| 同步采集 | DL32日志17:43:26启动，D0/D1、10MHz、1.6V、Stream；首因到达后F2停采并关闭窗口 | capture_start.txt与逻辑仪本机日志；未解码本次波形 |
| 一次同任务接续 | 收到READY，4265ms内实板返回IDLE和OTA_REASON=OUTBOX_FULL | admission_dispatch.json、admission_live.txt、admission_result.json |
| 安装/次数 | 准入失败停住，未创建新GR owner、未进入prepare/安装；R6一次机会仍未消费 | CAT IDLE/首因，未发送新任务或增加票据 |

实板证据目录：`D:\CODEX\sos-card\logs\r6_handoff_20261026\admission_live`。旧600秒采集已按文件清单/长度复制保存在`logs/r6_handoff_20261026/capture_1793004041_preserved`，459文件、444075147字节。最初供电指令未取得ACK，随后先确认CLI/只读status，再用完整行边界发幂等rail-on，取得明确ACK；未盲发PWRKEY、未断电/复位。

## 确定的代码缺陷与因果链

官方任务消息接口：

```lua
function sys.sendMsg(taskName, param1, param2, param3, param4)
    -- 实际入队：{param1, param2, param3, param4}
end
```

旧调用传了五个payload参数：

```lua
sys.sendMsg(sender, "MQTT_EVENT", "PUBLISH_OK", packet_id, client, session)
```

因此session被忽略，sender收到的msg[5]始终为nil；CONNECT_OK正常传入session=1。即使packet_id和client匹配，`msg[5]==send_item.session`仍为false，导致：

1. 第一条MQTT的sent回调已经到达。
2. sender不执行确认回调，不释放send_item，也不发下一条。
3. OTA runtime的inflight不释放，持久outbox无法确认排空。
4. 之前自动准入失败又追加回执，队列达到6条后accept返回OUTBOX_FULL，R6留在IDLE。

本板17:36启动日志恰好记录：第一条64字节消息，sent packet=2，随后130字节消息进入待发；pub_ok长期为1，业务消息继续正常。17:44:53实板首因OUTBOX_FULL。代码使用第五项校验、官方四参数边界与这些现象一致。

**当前阻塞定位为软件任务消息参数错配。** 原先UART FIFO溢出的具体服务延迟来源仍是独立未闭项，不以本次结果宣称全部硬件或异常恢复可靠性通过。

## 官方来源与证据边界

- 固定版本源码：[sys.lua第880行](https://github.com/openLuat/LuatOS/blob/a6a12408bdb644c48142a9b2183433ced64272f3/script/corelib/sys.lua#L880)。本地official_sys.lua SHA256：`d837193de8dd8886108f11a48bef3736d7bd11a9eb60d367b5be20d39ffc5d0f`。
- API实现正文已直接装入Lua测试，并非另写一个无限参数mock。来源记录official_task_api_provenance.json。
- 未从本板V2052 ROM提取sys函数机器码；官方源码证明接口合同，实板证明首因和投递停点，主机复现证明现有代码在该接口下必然丢session。最终修复是否恢复本板队列必须看实际OUTBOX计数和投递结果。
- 曾核对publish返回布尔值的假设；官方mqtt C实现返回单个整数message_id，该假设不成立，未据其改动publish逻辑，临时错误假设用例已移除。

## 实际修改

| 文件/函数 | 修改前 | 修改后 |
|---|---|---|
| Air780EGH/mqtts_main.lua / sent | client、session分别占第4/第5 payload参数 | 第4个payload为`{client, session}`，不再截断 |
| Air780EGH/mqtts_sender.lua / PUBLISH_OK | 比较丢失的msg[5] | 验证context为table，仍逐项匹配packet_id、client、session，匹配后才执行确认及推进队列 |
| mqtts_main / suback与失败通知 | SUBSCRIBE的matched也位于第5payload，QoS1拒绝标志可能丢失 | 入队前算出是否满足必要QoS1，消息只传4个payload；失败/超时仍拒绝并重连 |
| update.lua / FOTA_STATUS | 无法直接读取持久回执数量 | 输出只读OTA_OUTBOX=N，未发送消息、未改任务/次数 |
| sender日志 | 每次PUBLISH_REQ有多条重复指针/准备日志 | 去掉3条重复调试行；事件、等待/无连接、连接状态日志保留，以满足固定脚本容量 |

两端串行、安全门、业务Topic、包身份、GR/Boot和后台R6保持。保留所有待投递回执，只在对应Broker确认后按原事务移除。

## 为什么此前测试没有发现

旧测试的sys.sendMsg使用`function(...)`收集任意多参数，凭空保留了设备接口不保留的第五项，故三重匹配看似通过。现测试改为四参数边界；新增用例直接执行固定官方实现，并连接真实main中sent调用语句、真实sender和真实runtime持久outbox。

## 已完成验证

- 旧代码+官方sys：`OFFICIAL_SENDMSG_SESSION_TRUNCATED`明确失败。
- 修后：两个消息顺序发送；错误packet/client/session、重复/旧会话确认均不删除新消息。
- 真实runtime：6条持久回执经过实际sender和官方任务消息边界逐项确认排空；同一R6之后进入WAIT_GR，无新增/消耗试验，旧同hash历史count=3保持。
- 实际main回调：订阅拒绝、QoS降级、nil、超时、旧计时器、旧client均按预期处理。
- 活动CAT源码34个sys.sendMsg调用点审查，均不超过4个payload参数，清单task_boundary_audit.json。
- 冻结交付源码重新运行上述用例通过；update只读数量/错误字符串过滤通过；原生LuaDB解析和解压读回通过。
- 全部为主机/产物验证；本板新集合尚未下载。

## 唯一交付与下一实板验收点

`D:\CODEX\sos-card\Air780EGH\_ota_release\r6_mqtt_delivery_final_20261026\baseline\USB_IMPORT`

52文件，524256有效字节，余32字节。对已部署准入修复集合仅3个成员变化：mqtts_main.luac、mqtts_sender.luac、update.luac。manifest/verification/native_verified在同层；生成器prepare_r6_mqtt_envelope.py不覆盖已有输出。

1. 用户Luatools导入此目录全部52文件，仅下载脚本，保留FS/KV、任务、候选；GR/Boot、后台包无需操作。
2. 先确认GR正常、CAT1供电及真实版本；查询FOTA_STATUS的OTA_OUTBOX，观察旧回执按实际确认减少直至0。旧OTA_REASON=OUTBOX_FULL为已持久历史，队列排空后仍可能保留，不能当成新失败。
3. 若回执不排空，停在投递链路读取证据；不通过清outbox或改上限放行，不启动OTA。
4. 排空后，在同步UART采集就绪时显式接续同一已批准R6待办，期望IDLE→WAIT_GR→GR_GRANTED。既有R6授权仍适用，不增加次数、不重复旧RETIRE。
5. 后续GR安装、CAT1安装/重启、真实版本、可读用户数据、健康和结果投递逐项验收；未完成不得写OTA成功。

本次唯一待落地阻塞是**新MQTT修复尚未在板端验收**。没有把下载成功、离线6条排空或WAIT_GR模型写成实板OTA成功。

## 强制检查记录

| 检查项 | 结果 |
|---|---|
| 修改前范围和现场 | 读取当前实板首因、USB日志及源码调用边界；不回测布局/下载/旧退役 |
| SAM注释 | 每处运行代码、测试和生成器均记录SAM/日期/+08及原因 |
| 既有用户改动 | 仅补MQTT消息封装、订阅判断、回执计数；原冻结输出保留 |
| 主工程/交付副本 | 无GR修改；交付副本自动同步/编译不适用 |
| 编译与容量 | CAT原生编译、读回、524256/524288、52成员通过；无需F7或Boot绑定 |
| 用例 | 失败→通过、实际四参数边界+6条持久回执、订阅与旧会话、安全拒绝通过 |
| 实板 | 本轮得到OUTBOX_FULL首因；MQTT修复待下载验收；OTA仍未完成 |
