# 操作与判定参考

SAM | 2026-11-07 +08:00 | 已获准启用的操作参考；先确认当前文件、工具实现、授权和设备状态。

## 一、编译与版本核验

原工程`D:/CODEX/sos-card/ble_app_uart_c/Keil_6/YP001_GR5526.uvprojx`。先看是否已有匹配新产物，再核对实际日志、时间、版本/build、工程宏、输入hash与输出hash。保留原缓存，但不据此宣称最小增量编译范围已经证明。

冻结AXF、MAP、HEX、导出BIN、签名BIN/HEX、签名记录、构建日志和工具/合同指纹。完整源输入未绑定时，标记可重建性pending，不用当前可变工作树补作历史事实。

同一正式版本/build若对应不同字节，应拒绝替换发布，保留两者指纹并解释来源；本案的同版异包是教训，不是日常流程模板。

## 二、读取设备前先确认运行

优先使用当前已知端口，不能硬编码历史COM号。该项目最近GR为COM30，CAT1日志COM21/23、二进制调试COM22；这些只是路由线索。

```powershell
python tools/ota/gr_cli.py --port COM30 --wait-ms 2000 --log <新日志> fw_version "cat1_power status" "business status"
```

先看结果，再决定是否发CAT1命令。link/rail/PG不是模块真实启动证据；需RDY/实际版本/MQTT或本轮信标。下电时先暂停模块测试。

若已获本轮上电授权且模块确未运行：先on、确认ACK、至少200ms；仍无启动回应才一次PWRKEY并确认ACK，随后等待真实启动。拒绝、ACK丢失或事务不明时不盲重试，不强制reset或断电。

旧技能中的无条件`cat1_power reset`、宽泛清日志/清事务建议，不能覆盖当前安装安全门。

## 三、核对用户到底烧了什么

按以下证据链，不再让用户自行推断：

- Luatools工程路径只是输入线索；实际`script.bin`要解析为LuaDB成员。
- `tools/ota/check_luatools_scriptbin.py`比较每个成员，main.lua需用相同luac -s编译后比。临时目录ACL失败时，用新建ASCII工作区输出文件，不误记为校验通过。
- 核对实际成功烧写日志、脚本分区地址和相应时间，再取得模块真实启动/行为。
- GR读取实际工具logs里的pre/post、app、Boot配对和SCA证据。保护区域按本板已验证布局核对，不套用其他SDK默认布局。
- 取消“出厂清姓名/房号/园区”；CAT1保留FS/KV和匹配底包。文件数只是本案57正常/58维护的线索，不能代替指纹。

若两个交付归档字节相同，只改外层名称，不重刷；如果实际下载记录缺失，先补证据，不立即要求用户再刷一次。

## 四、事务取证

```powershell
$env:PYTHONIOENCODING='utf-8'
python tools/ota/gr_ota_probe.py --output-dir <全新证据目录> --json <全新JSON文件>
```

需要精确首错时，附当前镜像匹配的`--install-error-address`及`--firmware-provenance`。不要复制本案RAM地址到另一个build。探针“仅读”也可能增加调试观察负担，健康观察期优先串口/VUART，阶段异常时有针对性捕获，不固定轮询J-Link。

保留原始owner.bin/journal.bin/sram.bin。先核对当前结构ABI和枚举宽度，历史字段偏移仅见案例索引，不直接复用。用有效CRC/commit及generation选最新记录，不取数组最后一项或最大裸数字；FF页不是合法generation。

RAM内容扫描只是候选；marker0只说明该地址未记录，不能证明所有失败路径从未执行。非原子捕获和当前固件来源必须写清。

## 五、供电分支与故障

最新规则50%或USB：有效百分比50–100直接满足供电项；不足/未知必须有真实健康USB。未知电池内部哨兵255不得作为百分比发布。

USB需VIN/PG、无热限制/系统故障/OTG；充电关闭时仅允许代码明确实现的NTC分类例外，BATOVP不属于该例外。ETA69631 REG09 bit3=BATOVP，不能据无电池就认为可以忽略。

充电中display_status可能返回≤1秒缓存；最终电源证据还需无REG_FAULT副作用的live STATUS/DPM/POWER读取。prechecked不得绕过最终电源失败。未知电池＋USB必须也能进入并完成合法健康观察。

先区分历史CHG SNAP/AUTO_FAULT和本次实际FAULT_NOW。当前故障消失不证明原故障是误测；ADC变化不证明万用表电压已变。

## 六、旧事务恢复

PREPARED/full B/SPENT时先确定源/目标、Boot、job/hash/epoch和本轮数据保持范围。新修复在B里不能改变仍运行的旧A安装器。

区分：

- CANCEL_EMPTY：仅已有入口验证的空下载条件。
- GR Boot自动回退：只适用于其实现和当前Boot状态。
- 受控有线恢复：A、Boot基线描述符、SCA、旧事务/候选范围必须配套，保护最新用户数据。
- CAT1维护退休：精确任务身份、真实manager合法性和native安全性；保留配额/结果/历史，不宽泛清FS或复活SPENT。

维护遇到io2先按job.id判归属，合法无关历史可保留，但不能因此绕过当前io2/native活跃状态。普通新OTA入口禁用不等于精确维护/退休协议全禁用。不要把案例中epoch6、hash或probe S/N写成通用恢复许可。

## 七、正常OTA与后台监视

按当前真实版本生成接收端、不同更高目标、匹配范围和冻结MD5。改目标任何字节后重新生成校验/冻结，不覆盖旧发布目录。

```powershell
python tools/ota/check_url.py <受控url.txt> --package <本地目标协议包> --out <新报告目录>
```

PASSED需包括内容与本地相同、MD5、签名、组件摘要及服务器对应Range/流式路径。URL含凭据时不复制进技能或报告。主机读取同套Lua不能替代蜂窝模块实测。

读真实FOTA_STATUS/FS/MQTT/供电，按当前budget.json核算镜像、LuaDB、SOTA及可用空间；历史数值集中在案例索引，不自动套用。不能估大、用历史空闲代替当前、以清业务数据腾空间。

等待推送不得出现CAT1已下电的盲区；临时保电和设备OTA_HOLD须有ACK交接，无断电空档。设备收到新任务后确认LOG_CLEARED、ACCEPTED和OTA_HOLD，不重复推送、不叠加reset/PWRKEY。

V=整包预校验，D=组件网络下载，G=GR持久化进度。PSRAM暂存期G可为0。确认同任务至少两个有时间顺序的有效accepted/offset样本递增，才能判为仍在前进；单个DATA只证明曾传输，旧offset、单个信标及无错误日志均不能单独证明存活。停滞时对齐最后成功阶段与ACK/租约/接收诊断，不盲判HTTP故障或重复推送。

健康等待或结果挑战可能持续数分钟；优先看状态是否推进、真实版本及错误证据。新GR已运行时的stage11重复ACTIVATE已在源码与主机回归层修复，见[专项记录](D:/CODEX/sos-card/doc/2026-11-07_GR安装后重复ACTIVATE误报修复.md)。本轮未F7/签名/烧录，实板1.5.14/b18仍是原程序；不能把源码修复反写为b18已修，也不能 blanket-ignore同名错误。修复只接受精确owner/Boot/当前执行A身份，返回已激活确认，不代表健康通过、Boot确认或整机OTA完成。

## 八、最终验收与回退

设备成功至少包含：两端真实目标版本、合法持久owner COMPLETE/实际success、Boot CONFIRMED、CAT1正常终态/队列状态。历史TRIAL字段不能脱离当前phase单独判断；outbox0也不等于后台页面成功。后台可核对任务记录、消费日志或实际结果消息；原OTA协议没有平台应用层ACK，不增加新ACK要求，页面不可取得时保留“设备成功、后台记录待核对”的并列结论。

自动空闲下电与安装中异常掉电分开。任务结束后可在既有授权内重新上线核对持久终态，不能在native安装未知时这样做。

仅在证据完整且last_run身份匹配时记录一键工具done；它更新baseline，不执行同期副本同步/清理。恢复包完整性、真实救援演练和生产业务矩阵各自标记，不因OTA成功自动填passed。

回退需遵守已批准方案、实际落地状态与当前权限：不清用户未提交工作、不回写旧用户数据、不降级绕过版本校验、不把CAT1说成自建A/B。高风险保护组不能用普通总开关跳过；精确diff/hash许可尚未实施时明说当前工具能力边界。

## 九、批准后版本保护工具的核对入口

以下是本轮落地入口，使用前核对实际文件、`--help`、对应回归与[执行记录](D:/CODEX/sos-card/doc/2026-11-07_版本保护与OTA技能启用执行记录.md)。工具文件存在不代表当前发布已晋升，更不代表救援演练通过。

- `tools/version_control/baseline.py`：`freeze --spec --output`收集普通目录基线，`verify --directory --expected-manifest-sha256 <冻结目录外的原始锚点>`复核清单与hash；缺少历史输入的b18只能如实标记可重建性缺口，禁止将当前源码充作历史精确源码。
- `tools/ota_oneclick/oneclick.py --review-manifest <workspace-relative JSON>`及`tools/ota_oneclick/release_gate.py`：核对精确差异、评审清单与发布身份。不能继续依赖旧`--reviewed-ota-change`布尔值放行受保护差异；不要手写未知schema，先读工具帮助和本轮使用说明。
- 工具仍在开发或尚无对应通过证据时，明确标记该阶段未完成，不宣称已全仓强制执行。逐项base/delta/candidate与用户数据保持约束独立有效。

调用冻结、核验或生成本地候选不构成硬件操作许可。若命令后续会构建、签名、上传或烧录，先检查分支与副作用；GR实际构建始终由用户在原Keil主工程F7执行。
