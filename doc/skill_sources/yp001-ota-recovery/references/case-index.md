# 2026-11-06至07案例与证据索引

本文件是历史案例，不是当前设备或新安装机会的授权。

- 完整复盘：[报告](D:/CODEX/sos-card/doc/2026-11-07_OTA合并事故完整复盘与实板验收报告.md)。
- 已批准机制（历史文件名保留）：[方案](D:/CODEX/sos-card/doc/2026-11-07_已验证版本保护_合并准入与回退机制方案_待评估.md)。
- 上次教训：[11月2日复盘](D:/CODEX/sos-card/doc/2026-11-02_CAT1合并问题复盘.md)。

## 历史现场

初始b16运行1.5.12，目标1.5.13；owner302/epoch6/PREPARED、total=durable380136、Boot658/CONFIRMED、票SPENT。入口safe不满足时旧代码预校验0次，缺收据却被归类activation_validation_failed。具体瞬态门控项未被证据确定。

修复后先有线恢复1.5.13/b17，维护r1拒绝历史io2；r2按当前job归属检查并保留无关历史。真实OK_RETIRED及再次启动OK_ALREADY_RETIRED、IDLE/outbox0。

TEST_DATA固定80%已移除。用户随后将规则明确为50%或健康USB；最终commit绕过、USB缓存、unknown battery健康确认三个审查问题均修复并测试。当前与历史故障区分后，以USB正常样本准入，没有忽略08/BATOVP。

## 本轮成功终态

2026-11-07后台1.5.13/b17→1.5.14/b18，08:22:56 ACCEPTED，08:37:52回IDLE。最终owner103/epoch2/CAT1/COMPLETE/actual1.5.14/success，Boot329/CONFIRMED；两端实际build18，CAT1再次上线IDLE/outbox0。平台页面未核对。

中间G0时捕获相同事务DATA offset229376，证明曾传到对应位置，PSRAM尚未给durable信用；后续完整381160证实流程最终前进。单个中间点本身不证明持续存活，下轮应采集两个有时间顺序的有效进度点。新GRTRIAL期间重复ACTIVATE产生stage11、old1005013/new1005014、gate_mask0；Boot最终确认后流程自动继续CAT1，未人工解锁SPENT。该重复激活误报随后已完成源码修复和主机回归，见[专项记录](D:/CODEX/sos-card/doc/2026-11-07_GR安装后重复ACTIVATE误报修复.md)；未执行本轮F7、签名、烧录或新实板验收。上述b18实板成功证据仍属于原程序，不能被新源码状态覆盖。

本案历史owner为368字节短枚举ABI，target143、version151、source215、total352、durable356、CRC360、commit364。历史预算为GR签名≤393216、LuaDB≤507904、SOTA≤262144、可用≥GR签名＋32768。这些值不能替代新固件的ABI/当前budget核对。

## 直接证据路径

| 内容 | 路径，相对D:/CODEX/sos-card |
|---|---|
| 原故障/旧精确符号 | logs/ota_fix_execution_20261106/forensics/ |
| GR有线用户区保持 | logs/ota_recovery_acceptance_20261107/gr_flash_verification.json、power50_flash_check.json |
| 实际正常接收端匹配 | logs/ota_recovery_acceptance_20261107/normal_receiver_burn_check.json |
| 供电重读 | 同目录power_remeasure_1.txt、power_remeasure_2.txt |
| 平台地址检查 | logs/ota_push_1513_1514_20261107/url_check/report.json |
| 全程阶段 | 同目录run_vuart.txt |
| 安装后stage11 | 同目录post_install_probe.json及原始RAM |
| 最终成功 | 同目录final_probe.json、final_online_status.txt |
| 实际目标源码 | firmware_releases/ota_1.5.13_to_1.5.14_20261107_0742/work/target_source |
| 现有版本记录 | tools/ota_oneclick/state.json |

签名/MD5/版本均为历史身份；不要用本案URL、票、epoch、RAM地址、一次性标记或旧目标包执行下一轮测试。
