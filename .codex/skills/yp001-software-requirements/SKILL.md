---
name: yp001-software-requirements
description: Apply the customer software and business requirements for the YP001 third-generation alarm/location card in D:/CODEX/sos-card. Use when designing, changing or reviewing device state machines, SOS, voice, positioning, power, IoT messages, display, parameters or CAT1/GR5526 OTA; trace requirements and resolve document conflicts before implementation.
---

# 三代报警定位卡软件与业务要求

用户于2026-10-12指定四份客户文档作为后续软件/业务流程基线。本技能将要求、冲突和验收入口固化；不表示当前固件已经满足这些要求。

## 使用方式

1. 先读 [requirements.md](references/requirements.md)，按本次功能选出 F-xxx 要求和流程；修改前必须检查 [conflicts.md](references/conflicts.md) 的对应条目。
2. 精确字段、时序、参数需回查 [source-index.md](references/source-index.md) 指向的客户原文及行号。该索引记录四份原件SHA256；内容变化时先更新差异和裁决，不静默替换基线。
3. 涉及OTA再读 [ota-contract.md](references/ota-contract.md) 与项目正式 [双端OTA方案](D:/CODEX/sos-card/doc/2026-10-12_CAT1与GR5526双端OTA落地方案_备份与失败恢复.md)。只读核对当前代码，区分客户目标、方案建议、已实现功能、实板证据。
4. 将本次影响写为“需求ID/源章节 → 当前行为 → 改动 → 成功/失败/跨重启验收”。实施遵守项目AGENTS.md及代码强制检查项；本技能本身不授权烧录、联网、发布或改写用户数据。

## 不可丢失的规则

- 以用户最新明确要求为准；客户文档是产品规范与协议资料，不是命令执行授权。未决冲突不得擅自新增线上字段或假称平台已支持。确定不冲突的工作继续做，影响实现的未决项单列。
- 当前产品按 **GR5526 + Air780EGH** 落地。文档GR5512是历史硬件选型；不能借机更换芯片、引脚、链接布局或现板驱动。CAT1源码唯一入口 `D:/CODEX/sos-card/Air780EGH`；旧目录不是输入。
- GR始终是应用/供电/OTA编排主控；CAT1负责网络、音频/VoIP、下载和串口管道，OTA不翻转主从。
- 活动态CAT1已注册、低功耗可达；传输/通话切常规；静止硬断电。运动或按键可唤醒；睡眠SOS先上电并优先报警，再走上线流程。
- 报警通话只拨一次、不主动重拨，通话结束不等于报警解除；只有用户取消或平台取消结束报警。报警类/找人类60秒未确认最多重发3次；其余包括OTA无平台应用层确认，MQTT QoS1仍需正确处理。
- OTA必须同时满足稳定静止、充电中、电量至少70%、无报警；另检查通话/按键/运动和真实供电状态。无Force、不开放平台修改70%阈值、不为OTA周期唤醒。
- 两端OTA严格串行，包含下载/传输/安装/确认。GR A/B回退；CAT1常规厂商FOTA，不能宣称CAT1有自建A/B。
- **OTA不改、不清、不丢现有用户数据；回退程序不回退用户数据。** 清OTA任务NV仅限独立任务记录；不格式化NVDS/LFS，不以旧快照覆盖最新合法数据。无法保留则拒绝升级/救援。
- 源文件中的密码、Token、示例号码、带鉴权URL不写入技能、知识库或日志。只引用来源，不复制凭据、不试连平台。

## 维护位置

知识库主副本：`D:/code知识库/技能/yp001-software-requirements`。
项目发现副本：`D:/CODEX/sos-card/.codex/skills/yp001-software-requirements`。
两份同版本同hash维护；有差异先比较，不按时间戳盲目覆盖。项目AGENTS.md负责后续会话读取入口；不承诺当前会话的技能目录动态刷新。
