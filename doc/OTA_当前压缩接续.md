> 第6次结果（SAM，2026-10-25 +08:00）：已核对实际Luatools51成员，QUERY_SENT→ARMED后第6次进入传输并失败，已停止。新首次拒绝mask=0x10，transport_ready=false、network=MQTT、call=idle，last_rx_age=1840ms；最后链路失效源为UART_RX_LOST，随后仅network_mqtt状态已恢复，有效hello尚未恢复。电量/按键/运动年龄900/0/10ms，均有效。这次已排除IP降级和20秒超时为当前直接拒绝条件。

失败RAM接收214528，持久仍212992，未增加持久扇区。完整Flash与peer部署后快照比较：A、Boot、B、协调页、保护区、NVDS全部未变，原R4/epoch2/CRC/commit有效。CAT为PAUSED/GR_NACK_7/FAILED_HASH_LIMIT，MQTT conn=1/disc=0/CONNECTED。第6次已消费，不得重发授权或执行第7次。

源码中UART_RX_LOST只在GR接收溢出/驱动错误分支置位；本次累计软件环形队列dropped=0且未重置，可进一步收窄到UART错误事件或receive_async重新挂接失败，而不是软件环形队列挤满。当时具体error_code已被既有逻辑清除，当前0不能反证未出错。尚不能区分硬件错误码与重挂失败，更不能直接归因为电平/硬件损坏。下一定位仅围绕该驱动分支，保留原校验及状态门，不能再用一次OTA来猜。

证据：`logs/ota_sixth_20261025/denial_decoded.json`、`after_failure_verified.json`、`authorization.txt`、`progress_1.txt`、`uart_counters.txt`。本轮未安装任一目标，双端OTA和用户数据业务级验收仍未完成。

---

> 第6次授权更新（SAM，2026-10-25 +08:00）：用户已明确批准这一次。独立gr_r6票据及OTA_RECOVER_R4_6入口已完成，6组定向检查通过；仅需下载CAT1 recovery_sixth_20261025/baseline/USB_IMPORT的51文件，USB524243字节余45。GR、Boot及原R4不变。第6次尚未消费，下载后核对再执行已批准机会；第7次未授权。详见2026-10-25_R4第6次受控恢复票据与执行记录.md。本条覆盖下方第6次未授权的历史状态。

> 实板部署验收（SAM，2026-10-25 +08:00）：用户完成本批下载，GR签名应用/Boot读回逐字节一致；B槽、协调页、保护区、NVDS相对第五次现场全部未变，范围外变化为0，原R4/epoch2/212992持久进度保留。Luatools实际51成员全部匹配。已用GR rail on及一次PWRKEY给CAT1上电，COM21/22/23枚举，实机FW_VERSION为1.0.2/build3；MQTT conn=1/disc=0/CONNECTED；FOTA_STATUS为PAUSED、GR_NACK_7、429256/429256、FAILED_HASH_LIMIT。当前维护基线部署核对通过，双端OTA没有完成，第6次未授权且未执行。CAT运行态code_identity=NOT_CHECKED及health=NOT_OBSERVED不冒充安装健康验收。部署刚启动时有一次binary_or_long_line_discarded，后续版本/状态均正常；这不是已证明持续串口故障或长稳验收。

当前接续：修复集合已经部署，不再要求重编/重刷相同集合；如继续OTA，需要用户另行批准同一R4的第6次受控恢复，并另行准备限次票据，不能重发已消费的第5次命令。保留历史次数、候选和数据，不能清任务或重置上限。证据：`logs/ota_peer_sync_20261025/deployment_acceptance.json`、`deployment_verified.json`、`actual_cat_merge_verified.json`、`powered_live_status.txt`。

---

> 最新成套核对（SAM，2026-10-25 +08:00）：GR与Boot均已由用户实编0错误/0警告。签名应用430280字节；Boot34044字节且相对前一批严格仅40字节基线描述符变化；本轮源码仍与通过测试的指纹一致。CAT1集合51文件指纹一致，USB容器524239字节余49。成套下载载体已经生成，尚未部署；第6次未授权。以下待编译表述为历史，以本条和`firmware_releases/gr_peer_sync_20261025/update_plan.json`为准。

## 本批唯一部署清单

按顺序操作，完成后再读回核对，不直接启动OTA：

1. CAT1：Luatools替换为`D:\CODEX\sos-card\Air780EGH\_ota_release\peer_sync_20261025\baseline\USB_IMPORT`的全部51文件，仅“下载脚本”，保留FS/KV、任务和已消费票据，不下载底包。
2. GR应用：`D:\CODEX\sos-card\firmware_releases\gr_peer_sync_20261025\baseline\SIGNED_DOWNLOAD\DOWNLOAD_SIGNED_APP_ONLY.uvprojx`，仅Download，不F7、不Run。
3. 配套Boot：`D:\CODEX\sos-card\firmware_releases\gr_peer_sync_20261025\boot\DOWNLOAD_PAIRED_BOOT_ONLY.uvprojx`，仅Download，不F7、不Run。

后台R4不变，无需重新上传。当前212992字节为部署前应保留的持久进度，需部署后读回确认；本轮离线核对不能代替实板保留证据。

---

> 更新（SAM，2026-10-25 +08:00）：GR新应用已手动编译0错误/0警告；源指纹、新AXF中116字节拒绝记录及peer接口核对通过。签名镜像430280字节，槽余12088，签名验证通过。已生成匹配Boot工程`firmware_releases/gr_peer_sync_20261025/boot/BOOT_BIND_PEER_SYNC_BASELINE.uvprojx`；仅修改基线描述符和输出路径，编译器/FPU/下载设置与前一批已验证Boot一致。当前只需用户F7编译该Boot，暂不Download。配套Boot未实编，不能成套部署；第6次仍未授权。本轮未烧录。

# 最新接续：peer修复源码完成，等唯一GR工程手动编译

SAM | 2026-10-25 +08:00 | 用户批准四步：1已用第五次部署源码复现重复IP_READY错误降级；2已修复且真实断网/SIM撤销测试通过；3首次拒绝扩展116字节并经实际C与解码验证；4CAT1冻结51文件524239字节余49，GR只编译`ble_app_uart_c/Keil_6/YP001_BASELINE_PEER_SYNC_20261025.uvprojx`，暂不Download，编译后绑定新Boot。9组针对性验证通过，源码固定。本轮未操作设备，R4/212992持久进度/已消费5次不变，第6次仍未授权。完整唯一清单见`2026-10-25_peer状态覆盖修复与唯一更新清单.md`。当前不要单独刷CAT1或使用旧签名GR/Boot冒充新源码。

---
以下为历史现场及接续。

# 当前唯一接续：第5次失败已停止

## 第5次实板结果：失败，机会已消耗

SAM | 2026-10-25 +08:00 | 根据已保存现场更新，不重新触发OTA、不烧录。

- 用户已下载第5次票据集合，实际51文件匹配；命令已返回ARMED并实际传输。第5次已消费，未授权第6次。
- 最终PAUSED / GR_NACK_7 / FAILED_HASH_LIMIT。双端安装未完成，第5步未验收。
- 首次拒绝mask=0x10，仅peer；电量观测770ms、按键0ms、运动260ms，sample_flags=0xf。任务身份/epoch/进度检查没有拒绝；watchdog=0xffffffff表示此前已拒绝、未调用，不能判为看门狗故障。
- GR持久进度147456→212992，新增65536字节；RAM接收216576不等于持久完成。
- 对现有fifth_after_flash.bin离线解析：两页CRC/commit有效，epoch2、原R4身份一致，B槽212992字节前缀与签名R4一致。
- 对比observation_after_deploy_mapped.bin：A、Boot、保护区、NVDS逐字节未变。这不代表CAT1完整KV验收。
- 附近MQTT统计conn=1/disc=0/state=CONNECTED；故障后的GR已回到transport_ready=1/network=MQTT。不能将peer拒绝等同于已证明网络掉线。

### 唯一剩余定位

peer由GR的transport_ready与network==MQTT共同决定。现有快照未分别记录故障时两个字段，不能在两个来源之间定案。源码显示：20秒业务接收超时会清transport/network/call；CAT1 IP_READY会无条件发布ip，MQTT失效会发布offline。它们是候选路径，不是已证实本次根因。单纯transport_lost还会使call未知，与本次只有peer位不同，必须有后续部分同步才能解释。

下一项仅针对peer状态变化做离线时序复现与现有日志关联；不重跑下载/ZIP/JSON/布局/观测采样，不绕过peer门，不再发恢复命令，不修改当前票据或次数。未取得对应证据前不交付猜测修复。

证据：logs/ota_system_review_20261025/fifth_denial_decoded.json、fifth_after_verified.json、fifth_authorization.txt、fifth_continuous_monitor.txt。离线核验脚本verify_fifth_preserved.py使用独立输出，未覆盖第四次证据。

---
以下均为历史接续，不能据此重发第5次命令。

# OTA当前压缩接续

> 第5次授权接续（SAM，2026-10-25 +08:00）：用户已明确批准原R4仅增加第5次、保留历史和数据、失败即停。独立`gr_r5`票据和专用命令已实现，原第4次记录保留；5项新增＋7项原恢复＋2项runtime测试及manager回归通过。唯一新CAT1集合 `Air780EGH/_ota_release/recovery_fifth_20261025/baseline/USB_IMPORT` 51文件，预计USB524197字节余91，等待用户下载脚本。GR/Boot已部署验证无需再动。第5次尚未消费；下载后核对实际合并，再直接执行已批准机会，不再次询问同一授权。详见 `2026-10-25_R4第5次受控恢复票据与执行记录.md`。下方“第五次未授权”为历史，已被本条覆盖。

> 当前实板状态（SAM，2026-10-25 +08:00）：新观测修复应用及配套Boot已由用户下载，J-Link有效读回逐字节匹配；B/任务页/保护区/NVDS未变，既有147456持久进度保留。GR运行且持续真实采样，CAT1已上电枚举并回应PAUSED/GR_NACK_7/FAILED_HASH_LIMIT、候选429256/429256。没有新恢复；第五次仍未授权。部署证据 `logs/ota_system_review_20261025/observation_after_deploy_verified.json`，最终状态 `observation_final_status.txt`。下面待下载/待编译为历史。

> 成套交付更新（SAM，2026-10-25 +08:00）：观测修复应用及Boot均编译并核验通过，源码未变，Boot严格仅40字节基线指纹变化。唯一下载清单 `firmware_releases/gr_observation_fix_20261025/paired_downloads.json`，用户手动按应用→Boot仅Download、不F7、不Run。待下载后读回新部署差异；第五次恢复未授权，现有R4及147456持久进度保留。此条覆盖下方Boot待编译状态。

> 源码修复接续（SAM，2026-10-25 +08:00）：[第4步GR观测入口修复与拒绝快照](2026-10-25_第4步GR观测入口修复与拒绝快照.md)。已拆出与屏幕无关的运动/电量采样，覆盖共用UART入口及rx_allowed，新增首次拒绝RAM证据；主机入口/实际采样/实际port故障注入/业务回归通过。新工程 `ble_app_uart_c/Keil_6/YP001_BASELINE_OBSERVATION_FIX_20261025.uvprojx` 应用已实编0错误/0警告并验签，签名429256字节，尚待用户编译同批boot/BOOT_BIND_OBSERVATION_BASELINE.uvprojx并核对配对。本轮未烧录，未授权第五次。下段为当前实板最后现场，仍有效。

> 当前唯一接续（SAM，2026-10-25 +08:00）：[第四次恢复结果与GR许可覆盖缺口](2026-10-25_R4第四次恢复结果与GR许可覆盖缺口.md)。JSON克隆修复已实板越过RECOVERY_METADATA，返回ARMED；获批唯一额外恢复已使用，GR B持久从98304进至147456（RAM accepted147968），随后再次GR_NACK_7/FAILED_HASH_LIMIT。失败后Flash独立验证owner/epoch2/hash/CRC及B前缀匹配，A/Boot/保护区/NVDS未变。已停止，禁止第五次；双端安装与步骤5未验收。源码确认debug_uart_cli_poll还有未先刷新观测的接收入口，电量仍依赖UI；本次具体内部拒绝条件未捕获，不能当作昨天运动过期。下一项只处理GR许可完整覆盖及无断点拒绝快照；不重开下载/ZIP/JSON/COM/布局/旧Boot检查，不清任务。下方旧最新与交付目录仅作历史。

SAM | 2026-10-24 +08:00 | 用户要求压缩上下文并执行第2步。本文件只列当前有效状态，历史文档与之冲突时按用户最新授权处理。

> 最新接续：第2步限定试验准入代码已落地并通过8项新测试，见2026-10-24_第2步首次受控试验准入代码.md；默认未提供审查配置仍关闭。下一项为第3步基线/目标中的真实配置及精确底包部署记录绑定。下文5278a7c0ae9c SOTA是历史候选，不包含新代码，不能再要求下载。原始KV仍非阻塞。

## 目标与已批准顺序

GR5526 SDK1.0.4＋Air780EGH V2052/113，1.0.2/build3→1.5.0/build4，串行OTA，不修改/清空用户现有数据。

1. 数据取证：已按用户批准的新范围完成软件调整。可读文件/已初始化KV前后比较；原始KV不可读则UNVERIFIED，未完成但非阻塞。不再研究flashdump、USB raw KV或NOR保护。
2. 原生激活审查：当前步骤；最后一块写入可能激活，必须在此前持久化提交意图并复核安全/数据。原生finish(false)不能视为撤销。
3. 统一基线与目标固件。
4. 唯一安装ZIP。
5. 实板串行OTA及版本、可读数据、业务健康和上报验收。

GR编译/下载用户手动；不自动同步交付副本；不Git/SVN；不改硬件/布局/已验证Keil配置。用户禁止重跑已通过项目。

## 直接沿用，不重测

- GR基线、签名、Boot首次部署和路由已实测。
- GR目标firmware_releases/target_1_5_0_current_20261024/GR5526_1.5.0_signed.bin已冻结，428232字节；SHA256 4b16a9c188ee6cba8ae549b4b063de74b154462533c265a9e71f6e89b858ce8c。
- 真实蜂窝HTTP200/chunked、整ZIP MD5、签名、GR/CAT摘要：logs/ota_sequential_20261024/device_readonly/round5_acceptance.json。
- 旧ZIP只供解析，device_installable=false，不得上传作安装。
- 正常官方FOTA保留LFS/KV，已直接核对官方课程009 §5.4/§8.5。

## 当前源码与产物

CAT唯一源码Air780EGH；main.lua为001.005.000/1.5.0/build4，实机最后记录为1.0.2/build3诊断修订5，不能混同。

首次数据策略只对1.0.2→1.5.0允许root_files_kv_unverified；其他版本组合仍拒绝。require_data_identity=true，KV已可读则仍比较键值。boot业务初始化前读取，合法后续业务写入不再用旧快照覆盖。

唯一新CAT目标：logs/ota_readable_scope_20261024/native_target/CAT1_TK_PROJECT_OTA_001.005.000_5278a7c0ae9c_f76d02.sota。

- LuaDB520601/524288，余3687；SOTA250544；SHA256 5278a7c0ae9c84d7290b19a9c08850352512848eb7f5f7aa63fdd505c636ac47。
- 格式/解压读回通过；不包含用户数据区载荷；不是可安装整机ZIP。
- 新策略曾导致容量超限；已通过省略未引用旧libfota2载荷解决，源文件保留。容量项关闭，不重算布局。
- 新打包GUI候选OTA_Packager/YP001OtaPackager_scoped_first_ota.exe；原BAT仍使用原GUI，不要声称默认入口已替换。

## 本次第2步的实际推进

没有重改已通过提交边界。新增两个此前未覆盖故障用例：

1. 最后一块native.run内部抛异常：保留COMMITTING/native_activation_possible，不调用finish(false)冒充撤销；重启不重放。
2. 最后一块native.run尚未返回即构造复位恢复：读到此前持久COMMITTING，保持RECOVERY_HOLD，不继续写入。

两项通过；同一测试文件共7项通过。日志logs/ota_readable_scope_20261024/step2_final_run_faults.txt。仅主机故障模拟，不是V2052实板异常复位验证。生产Lua源码未变，所以上述目标SOTA在本次测试后未失效，无需因新增测试再次生成。

## 尚未关闭的确切边界

Air780EGH/ota_device_options.lua仍有native_contract_verified恒false及native_rx_limit_verified=false。现有SOTA因此不能直接执行真实安装。这两项没有因KV范围调整自动变true。

第2步不能被笼统写成“全部安全已验收”：已完成主机提交顺序/异常恢复审查，尚未落地与精确底包、源/目标版本及已知证据绑定的首次受控实板试验准入。下一次直接处理该准入的实现与验证，不再搜索不存在的通用pending接口、不再重测上午下载解析，也不能再把真实安装成功反过来设为首次测试的前提造成循环。

限定首次试验与生产长期准入必须区分；只能按已有授权范围连接，不能把泛化开关直接改true。原生API回调/写入完成不等于重启安装成功；最终仍需真实目标版本、签名代码身份、120秒业务健康与可读数据比较。

## 入口与解释边界

- 当前唯一验收表：doc/OTA_唯一验收与固件准备表.md。
- 激活证据：doc/2026-10-24_V2052最后一块激活边界修复.md；logs/ota_v2052_tool_review_20261024/activation_functions.txt。ELF SHA256 c439f1c407ff2213b5e27a41a56b2a468fd05739a025348143ad16edaab4dd97。
- 固定底包SHA256 29a3f2dc4eb07badc1093bf8b48f04fa54b40a6d537d1c0814dcfadf53693eec。
- 用户的合宙AI粘贴是参考资料，不是执行NOR保护/未知地址读取/放宽安全门的授权。
- 本轮仅补测试和记录，无生产固件改动/编译/烧录，无实板OTA，无新增实板通过项。

## 最新接续：第4步首次试验包已生成（2026-10-24）

本节覆盖上文旧候选与“尚未生成安装ZIP”的状态。第1步原始KV非阻塞且未验收；第2/3步准备沿用已留证结果；第4步已完成本地主机打包验证，第5步真实OTA未开始。

唯一上传文件：`Air780EGH/_ota_release/first_trial_20261024/package/1.0.2---1.5.0.ypota.zip`，695202字节，MD5 `3d6719bf8646044f8e428162283e3f06`。验证记录：同目录上一级`package_verification.json`。

本次修复BundleSigning.VerifyArchive只允许不可安装LOCAL_TEST包、与新增FIRST_CONTROLLED_TRIAL生成器冲突的问题。仅固定1.0.2→1.5.0、原底包、审查绑定、可读数据范围允许首次试验；未放行普通离线包或生产声明。13项试验绑定拒绝、20项归档范围拒绝、12项既有安装准入拒绝通过。最终固定公钥RSA验签、六成员STORE、CRC、两组件hash和冻结GR逐字节一致通过。

COM26本轮读到CAT1 1.0.2/build3，FS可用495616字节，代码身份NOT_CHECKED；用户报告新基线下载完成，但完整部署集合没有独立匹配证据。无需为此再刷诊断脚本。原OTA_SPACE的install_enabled=false是旧硬编码，不用它判断试验profile。

下一项仅需用户上传上述唯一新ZIP并提供新直链，再按已授权串行OTA执行；不用上午旧包。真实安装、目标代码身份、可读数据保持、120秒健康和结果上报仍需实板证据；不可读KV持续UNVERIFIED。不要返回flashdump、布局、Boot部署或重编GR。

## 新后台地址核对（2026-10-24）

用户已上传第4步唯一试验包。电脑从新后台地址取得HTTP200/chunked，695202字节，MD5 3d6719bf8646044f8e428162283e3f06、SHA256 97c494f88f7798371ce69605a574767a36672cf12069f83ef372ef2ea5c4c1d6，与本地ZIP逐字节一致。记录logs/ota_first_trial_live_20261024/backend_verified.json；鉴权URL不复制到日志。

COM26本轮读取：GR 1.0.2/build3且ota_provisioned=1；CAT1 1.0.2/build3、code_identity=NOT_CHECKED、FOTA_STATUS=IDLE。记录preflight_serial.txt。尚未发现新任务/真实安装，不能记为OTA通过。

正式入口为CAT1可信MQTT下行otaMsg，要求非retained；现有串口FOTA_CHECK明确拒绝绕过平台任务及GR授权。已请用户用新地址下发1.0.2→1.5.0任务，并开始COM26监听。不要因文件上传成功声称已触发升级，也不要为注入任务新增诊断刷机。

## 最新：用户已批准手动主动拉取入口

用户后台尚未具备主动下发，已批准仅修改CAT1基线的手动入口。已生成唯一新下载目录Air780EGH/_ota_release/manual_trial_20261024/USB_IMPORT，52文件；主机重建521239字节，余3049；5组测试通过，含实际manager夹具仅REQUEST、无直接激活。原始根源码/GR/已上传ZIP保持不变。

仅派生基线update以OTA_TRIAL_START替换旧OTA_NET_CHECK，只允许1.0.2/build3及MD5 3d6719bf8646044f8e428162283e3f06，异步调用runtime.accept，保留签名/GR授权/安全门。OTA_DATA_AUDIT保留。详见2026-10-24_CAT1手动首次OTA入口实现.md。

现在需要用户一次仅脚本下载上述新目录且保留FS/KV；完成后通过COM26发送cat_at OTA_TRIAL_START=<固定MD5>,<用户提供的新后台URL>，不用再等后台下发、不重测旧只读解析、不重编/下载GR、不重传ZIP。新入口尚未部署；没有新的实板安装通过项。Luatools实际合并未独立核对。原始KV非阻塞且未验收。

## 手动入口部署差异已定位

用户报告下载后，COM26发送OTA_TRIAL_START无回包，FW_VERSION仍正常。停止重复触发，未观察到任务开始。

已检查Luatools真实生成物D:/Installers/_temp/ec_download/script.bin：有效LuaDB524033字节，update SHA256 9af51c8aeeaaf540c6de218a574dd9b44b5108548ec256af987974a32666e463，不含OTA_TRIAL_START，仍含OTA_NET_CHECK。当前项目Air780EGH_antenna.ini仍指向旧first_trial_20261024/baseline/USB_IMPORT_FINAL。

正确manual_trial_20261024/USB_IMPORT的主机重建为521239字节，update SHA256 4118b4ffb3375657613bb59c88eab35075aea6ea8cfe7a87a6790f5c83563f5d，含新入口。证据logs/ota_first_trial_live_20261024/actual_usb_comparison.json。这是导入旧集合导致的部署差异，不是重新排查安装方案；不要重改入口、GR或后台包。需在Luatools项目删除旧文件列表并导入唯一新目录全部52文件，保留FS/KV，仅脚本下载。下载后先对实际合并镜像update指纹，再执行一次命令。

## 避免重复误选的项目配置已落地

用户再次报告下载后，实际ec_download/script.bin更新时间17:43:52，但有效LuaDB仍524033字节且update不含手动入口。读取项目ini确认仍为旧目录；发现同时运行两个Luatools_v3进程（不据此断言哪个覆盖设置）。

已创建独立项目D:/Installers/project/OTA_MANUAL_102_TO_150.ini，固定指向manual_trial_20261024/USB_IMPORT全部52文件；原项目未改、未覆盖、未操作设备。工作区副本同名保留在manual_trial_20261024。下一次明确选择新项目名OTA_MANUAL_102_TO_150，不再让用户在原项目中反复改路径；若项目列表未刷新，重新打开Luatools项目管理。实际新集合有效字节应为521239，不能只看512KiB填充后的文件总长。

## 最新实板接续：手动入口通过，WAIT_GR发送缺陷已定位

新项目实际合并已匹配52个内容条目（CRC条目不同），521239字节。主动命令实际返回ACCEPTED_PENDING_GR，设备停WAIT_GR。无需再让用户重新导入旧集合。

V2052精确底包反汇编证明json由lua_newuserdata构造；ota_platform.send_gr误要求table导致请求未发。根源码已修复，2项原生JSON回归与21项运行时回归通过；源码修复未部署。

新修复目标包first_trial_jsonfix_20261024/package/1.0.2---1.5.0_J1.ypota.zip已生成验签，MD5 353e60cc1d9c1a3adf059769b2f28d15；GR不变。已请用户上传新包提供新URL。旧包目标也含该错误，不能只修基线继续旧包。

当前设备旧WAIT_GR任务仍保留。尚需安全切换任务及准备最终修复基线；不要清用户数据/伪造GR授权，不直接部署修复后自动重放旧任务。详见2026-10-24_首次主动OTA_WAIT_GR与JSON原生模块修复.md。安装及数据保持未验收。

## 最新接续：J1地址已验证，最终J1基线就绪

新后台包695203字节，MD5 353e60cc1d9c1a3adf059769b2f28d15，逐字节匹配。无需重传。

唯一新下载项目OTA_J1_FIXED已添加D:/Installers/project；对应manual_j1_20261024/USB_IMPORT，51文件，USB主机重建520811字节，余3477。包含JSON修复和基线专用manual_bridge；启动自动暂停确切旧WAIT_GR，显式新命令先QUERY，只有3秒内GR空闲且无owner才原子结束旧任务，再经原accept受理J1。保留用户数据、失败/重试/上报记录；不释放实际GR owner。6项新接续和5项原入口测试通过。J1 ZIP及GR不变。

当前待用户下载此新项目，仅脚本保留FS/KV；未部署前不要发送新任务。下载后核实际merge，发送OTA_TRIAL_START=353e60cc1d9c1a3adf059769b2f28d15,<用户最新URL>。状态应先GR_IDLE_QUERY_PENDING，再OTA_LOCAL=OLD_WAIT_RETIRED_GR_IDLE及ACCEPTED_PENDING_GR。这仍不代表安装成功。实板任务切换/升级/可读数据/健康及上报均待验；raw KV非阻塞且未验收。详见2026-10-24_J1后台与旧WAIT_GR安全接续基线.md。

## Luatools依赖误识别修复（最新下载接续）

用户报告下载后，实际ec_download/script.bin仍为17:48的521239字节旧集合；trace运行时间未重启。工具日志18:12两次明确报错：缺少 ota_manual_bridge').new(require('ota_device_options.lua。由此确认本轮未下载生效，不是用户路径选错；我此前只建议取消弹窗未解决生成器兼容问题。

原因：生成main的同一行有两个嵌套literal require，Luatools贪婪依赖扫描合并成一个假文件名。已在tools/ota/prepare_manual_j1.py拆为独立两行加载，再调用new；同路径source/main.lua和USB_IMPORT/main.lua已同步修正。项目仍OTA_J1_FIXED，目录仍manual_j1_20261024/USB_IMPORT，51文件，不再改项目名。

生成器回归test_j1_dependency_scan.py复现该贪婪捕获并验证新写法，测试通过；6项bridge测试仍通过。官方编译native_mainfix2：SOTA SHA256 6095141df9f02a1119b1cc36d65ed6b14a3a3d6acad378a5e2eca893b88a663c。USB重建仍520811，余3477；最新比对基准改用manual_j1_20261024/expected_usb_script_mainfix2.bin，旧expected_usb_script.bin保留追溯，不再用于本次比对。前一native_mainfix目录是在PowerShell路径数组错误时重建的旧main，不是最终输出，不用。

已请用户原项目再次点击下载脚本，保留FS/KV，不添加默认库；修复后不应弹假缺库警告。尚无本次实板部署/OTA新增通过项。后台J1/GR未变；不重新上传。

## 最新状态：J1接续通过，GR采样调度缺陷已定位并修源

实际merge51内容全匹配，实板OLD_WAIT_RETIRED_GR_IDLE及ACCEPTED_PENDING_GR已出现；JSON发送修复实板有效，REQUEST/QUERY实际发出。此项关闭，不再重发或重刷CAT。

GR未授予新任务。一次只读SRAM样本（Cortex-M4，旧map短枚举正确解析）owner IDLE/epoch0，电池年龄10300ms、运动2180ms、moving1。BSP采样原每10秒/2秒且被屏幕节流，违反3秒/1.5秒安全新鲜度，持续重置静止判定。只改主bsp.c采样调度：电池后续1秒/XYZ0.5秒，采样在屏幕节流前，显示仍2秒；不降低任何安全门。真实函数桩运行改前失败12.4/2.48秒间隔，改后1.48/0.98秒通过；原业务测试通过。

已准备两份用户手动编译工程：Keil_6/YP001_BASELINE_SAMPLE_FIX_20261024.uvprojx（1.0.2）和YP001_TARGET_SAMPLE_FIX_20261024.uvprojx（1.5.0）。只F7编译，不下载未签名HEX，不先部署修复GR让当前J1 WAIT_GR自动续作旧目标。Codex未编译GR。输出firmware_releases/gr_sample_fix_20261024/{baseline,target}/Objects。

编译后需签名、最终两端一致目标包、CAT暂停/安全换任务后再部署；J1后台包不能作最终双端目标（其GR也有采样缺陷），不要再让用户重复上传J1。所有源/目标/采样修复实板、数据保持和健康验收仍待。详见2026-10-24_GR授权采样调度根因与修复.md。JLink禁止再尝试GR5526设备名，直接用已验证Cortex-M4。

## 最新：用户两份GR构建已核对签名，S2待部署

两份0错0警告，正文427328/签名428232。baseline1.0.2签名hash5718a8e1be84fc50cb93e398ca7645dac15e48bb45c964d62dce47b0bc32b0cf；target1.5.0签名hash8cd92a9e70b53509082e295bdba7c057e20b94863d4cbbe4efa09f62780a9d9a。用户编译，Codex仅签名/载体包装，不重编应用。

S2包已在OTA_Packager/output/1.0.2---1.5.0_S2.ypota.zip，MD5 d31713e0fb1af1bcb4eb026a201b2a39。包含新GR采样目标和未改的J1 CAT目标；签名/归档读回通过。FS本轮487424，容量检查仍通过。需要用户上传S2提供新URL，不再用J1目标。

当前实板仍J1 WAIT_GR。为防修复GR一运行就安装旧J1，先只下载CAT项目OTA_S2_HOLD（已加入Luatools），对应manual_s2_20261024/USB_IMPORT全部51文件，主机合并520807字节。其bridge启动暂停J1，固定仅S2命令触发实时GR IDLE查询和接续；7项bridge+5项原入口测试通过。不要先下载GR，更不要用未签名HEX。

CAT暂停部署经实际merge和日志确认后，再通知用户下载firmware_releases/gr_sample_fix_20261024/baseline/SIGNED_DOWNLOAD_AFTER_CAT_HOLD/STAGE1_DOWNLOAD.uvprojx载体，前后保留数据回读。载体已生成0警告且精确签名字节；目前尚未部署。然后新URL下发S2，做真实升级验收。

源代码/布局/Boot已通过项不重查，编译不用再做。详见2026-10-24_双GR构建签名与S2配套准备.md。安装、可读数据保持及健康仍未验收；raw KV非阻塞且未验收。

## S2后台地址已验证，待CAT暂停集合下载

用户已提供S2新后台地址。HTTP200取得695203字节，MD5 d31713e0fb1af1bcb4eb026a201b2a39、SHA256 11db24354dc15c88bb9fec670f938dca1d37356f3a269588eabaf41d31d66e34，与唯一S2包逐字节一致；鉴权URL不落日志。证据s2_backend_verified.json。

Luatools当前实际合并仍520811字节的J1集合，与S2相比仅ota_manual_bridge.luac、update.luac不同，见s2_current_merge.json。S2 HOLD尚无部署证据，禁止先下载GR或发送S2命令。下一步只需用户选择已准备OTA_S2_HOLD并仅下载51脚本、保留FS/KV；正确主机合并为520807字节。确认实际集合与运行态暂停后，再进行签名GR基线部署。包无需再上传、两份GR无需重编。

## 最新：S2集合正确生成，但本次USB下载实际失败

实际ec_download/script.bin 520807字节，51条payload全匹配S2；这只能证明合并生成，不能证明已烧入。随后trace仍发送J1 job316a40...的REQUEST/QUERY，S2命令实板返回ARGUMENT。

工具日志明确：18:57:47曾发现COM28；18:58:03启动FlashToolCLI --port COM28 --skipconnect 1 burnbatch --imglist flexfile2；18:58:36打开端口时报FileNotFoundError并记录两处“下载失败”，随后重启旧固件。因此S2 HOLD未部署。不是bridge暂停逻辑实板失败，也不是用户选错脚本，禁止因此重写bridge或生成新包。已撤回前面暂停代码有问题的猜测。

当前端口COM21/22/23/26，无COM28。只做官方CLI --help主机启动检查/预热约2.15秒（在工具目录写自身日志，需要沙箱外日志权限；最终允许），未指定端口、未烧写或擦除。最初沙箱启动因官方log文件写权限失败，不作为CLI或硬件故障证据。没有自动审批拒绝。

下一步仍使用同一OTA_S2_HOLD、同目录51文件及S2后台包，不改代码，不重传包、不重编GR。请用户通过现有BOOT开关保持下载模式至实际写入进度开始后释放，重试仅脚本下载、保留FS/KV。必须核工具日志明确下载成功以及新运行态入口，不能仅凭合并文件判断部署。签名GR基线仍禁止先下载。更新证据s2_deployed_merge.json（仅合并）、s2_start.txt（ARGUMENT）。

## 连续下载失败定位：不是固件生成或容量问题

用户反馈连续失败。新日志19:06:40.940发现COM28，19:06:40.971标记端口ok；19:07:29.148才启动官方CLI，空档48.177秒；19:07:32.102实际SerOpen COM28报FileNotFoundError/0x1010，日志明确下载失败。不存在AccessDenied证据，不能说端口被占用。CLI进程本次仅约2.9秒即进入打开端口，不应把48秒归因于CLI启动慢。

端口为何退出、48秒为何等待仍待确定，已询问用户该阶段是否有“断开BOOT/确认开始”弹窗。不要在答案前写成人工延误或工具内部固定等待。既有下载助手仅引导手动流程，不自动执行Luatools烧写，不是该48秒的已证实来源。

脚本生成预处理/依赖/容量已通过，烧录指令明确burnbatch --imglist flexfile2，配置对应script.bin / 0x56E000；不是因本次脚本超容量而拒绝。未修改配置、固件或硬件，也未自动重烧。现有GUI/S2集合不变。下一步集中修正“端口检测→实际打开”的交接，不再让用户盲目重复点下载或先刷GR。

## S2脚本实板下载成功（2026-10-24 19:17）

官方日志19:17:45 Burn OK / Burnbatch OK，imglist仅flexfile2；实际生成镜像51个payload与S2预期全部一致（派生CRC成员不同不作源码差异）。重启后510行记录无OTA_CTL旧任务请求，业务联网并上报1.0.2/build3。S2 HOLD部署证据已闭合，可以推进用户手动下载既有签名GR基线载体：firmware_releases/gr_sample_fix_20261024/baseline/SIGNED_DOWNLOAD_AFTER_CAT_HOLD/STAGE1_DOWNLOAD.uvprojx。不重编、不重传S2后台包。此证据不代表OTA安装或用户数据保持验收。证据logs/ota_first_trial_live_20261024/s2_usb_success.json。下载失败暂不再复现；此前48秒延迟根因仍未确认，不能称永久修复。

## 最新：GR签名基线已运行，S2接续成功，候选文件名超63字节导致PAUSED

实板fw_version verify验签通过，1.0.2/build3/427328正文；采样修复生效。S2仅发送一次，GR实时IDLE后旧J1已退役，新任务已授权，job99a8c39d...进入PREPARING后PAUSED。19:39:15候选83字节文件名wb创建失败，精确V2052 LittleFS上限63；已复现并修改源代码为完整SHA256无损Base32、55字节文件名，全调用链与数据排除项同步。修复未烧入，不改/重传旧S2，不清当前owner/epoch或失败计数。下一步仅做受控失败恢复及匹配的CAT基线/目标发布，不能套用GR-IDLE旧任务退役入口。详见2026-10-24_S2候选文件名越限定位与修复.md，实板安装/数据保持/健康仍未验收。

## 最新：安装前空任务取消代码与修复集合已准备

只新增CANCEL_EMPTY，精确owner/epoch、GR DOWNLOADING、零持久进度、B槽全空、无Boot安装/试运行意图才持久取消收据。CAT先CANCELLING后匹配收据归档，失败计数不清。新维护桥启动hold旧S2，拒绝旧S2重投。C故障注入、CAT两项取消与桥一项、28项任务回归通过，未烧入。
CAT独立Luatools项目OTA_STORAGE_REPAIR已添加，目录storage_repair_20261024/baseline/USB_IMPORT，51文件；预期USB LuaDB519111，余5177。目标SOTA28f983ea...已生成517056脚本字节。GR用户新基线0错0警，已签名6397c0eb...，新载体gr_storage_fix_20261024/baseline/SIGNED_DOWNLOAD_AFTER_CAT_HOLD/STAGE1_DOWNLOAD.uvprojx待CAT保持确认后下载。新GR目标输出仍空，已向用户精确提示只编译TARGET_STORAGE_FIX，不用旧SAMPLE目标。先CAT维护基线，再GR签名基线，再真实空任务取消，再新修复ZIP；不清FS/KV/owner，不重投S2。详见2026-10-24_S2空任务安全取消与修复集合交付.md。

## 20:20后接续：CAT维修基线实板已确认，GR两构建已齐，唯一R3已生成

用户目标工程完成后已取得新target/Objects/YP001_GR5526.hex，构建结尾0错误0警告；签名目标428232字节，SHA256 0d37ee735d52b91ca7e0cc492d0d970264129513ced78b691e5961cb2c9be456。不重编基线，不再使用SAMPLE_FIX旧目标。

CAT维护基线20:20:43官方日志Burn OK/Burnbatch OK，实际merge51 payload与expected_usb_script.bin全部匹配；新运行态FOTA_STATUS返回PAUSED并明确OTA_REASON=write_readback_failed。维护保持已生效；这不代表已取消任务。

本地打包器对review元数据缺少核心指纹/原生未验收字段、随后目标main未绑定完整review均明确拒绝，未绕过检查。新release_review包裹原组件source review，保留component_source_review_sha256；只把目标main的profile绑定到完整release review并重建目标SOTA，已烧入的维护基线未变化。最终目标SOTA为target/native_bound/CAT1_TK_PROJECT_OTA_001.005.000_fc307b7ff765_f22dbf.sota，248564字节、LuaDB517056，SHA256 fc307b7ff765b9fe1b69010587e1e48bb63e2b4e72aa52d568230366311495f2。先前target/native中的28f983...仅是源审查阶段产物，不用于上传。

唯一新包：OTA_Packager/output/1.0.2---1.5.0_R3.ypota.zip，691924字节，MD5 415328781189dff4c29ca4344e1759e5，SHA256 5a6d95b3eec547445dca604a67793a040982283fbbea3be98991e523b458d455。独立Python验证归档RSA签名、GR签名、两端组件字节/hash/MD5、六成员STORE/CRC、1.0.2→1.5.0映射全部通过，证据R3_VERIFIED.json。仍是FIRST_CONTROLLED_TRIAL，实板安装验收false。

已通知用户现在只Download新GR签名基线载体（gr_storage_fix_20261024/baseline/SIGNED_DOWNLOAD_AFTER_CAT_HOLD/STAGE1_DOWNLOAD.uvprojx），不用F7；可并行上传唯一R3，不触发升级。下一步仅核新GR运行/保护和空任务取消收据。

必须保留的下发入口边界：维修基线为了停旧S2，当前没有OTA_TRIAL_START；不能承诺取得R3地址后复用已删除的手动命令就会升级。标准MQTT otaMsg接收仍存在，后续需要接通可用的受控下发入口。对既有broker只做了无凭据TLS握手，系统证书验证失败，未发送用户名/密码/任务，未订阅/发布、不影响终端已有会话；不把它当已完成的下发路线。原始KV仍非阻塞且未验收。

## 本轮 J-Link 恢复运行与 CAT1 上电
J-Link 实测初始 PC=0x20000000，为下载算法 RAM 停留；通过 r/g 恢复 GR，未烧写 Flash。cat1_power on 与一次 key 均返回 code=0；CAT1 COM21/22/23 出现，REG=1、IP_READY、MQTT CONNECTED，FW_VERSION=1.0.2/build3，PAUSED。GR verify 仍报告旧正文427328（预期新维修正文428232），不得发送 CANCEL_EMPTY。后续一次 A 槽只读导出阻塞且输出0字节，已停止本轮JLink进程；该文件无效，不当备份、不重复读。R3后台文件691924字节，MD5 415328781189dff4c29ca4344e1759e5，SHA256与本地完全一致。实板OTA仍未验收。


## R3实板接续更正与当前门槛
正文427328与签名文件428232差904，不是新GR未生效。已通过新构建入口指令及实板取消应答断点确认新GR执行；无需再烧。CAT1已通过JLink恢复GR+电源/key启动，MQTT在线。一次取消进入CANCELLING；实际GR DENY=cancel_not_empty_or_safe。当前charger FAULT_NOW=02、CHG_EN=0、业务bat_known=0，真实充电门不满足，禁止伪造或放宽。R3后台包哈希完全匹配但未下发；手动入口缺口仍存在，安全MQTT下发尚未接通。下一步先恢复真实正常充电，再取得取消收据，再R3串行安装；不重测已通过项。详见2026-10-24_R3实板测试当前阻塞.md。


## 最新授权：USB供电台架例外已改源码，待用户编译
用户明确不要充电、用USB测试，现已增加默认关闭的YP001_OTA_USB_BENCH_TEST；专用BASELINE_USB_BENCH/TARGET_USB_BENCH工程启用。真实USB PG/输入/热调节/非NTC故障/充电关闭检查保留，ADC真实电量≥70、静止/无报警/串行/签名/数据保护不变。生产不定义宏则原逻辑。两组电源策略测试+协调器故障注入通过，尚未Keil编译/签名/烧入。用户只F7编译两新工程，不直接Download未签HEX。新输出firmware_releases/gr_usb_bench_20261024/{baseline,target}/Objects。旧R3不具新USB策略，新GR目标完成后须新包，不能继续称R3可完整安装。CAT入口缺口仍未解决，需安全MQTT或固定任务入口。详见2026-10-24_USB供电OTA台架例外.md。


## 最新：USB三缺口软件联测已通过，待统一两份GR编译
已新增prepare_usb_bench_delivery.py：最终签名包固定MD5绑定本地OTA_TRIAL_START，保留CANCEL_EMPTY/维护桥；核真实签名/组件/USB台架目标标识，旧R3被拒绝误作新测试包。test_usb_bench_chain三项连接真实manager与durable store，覆盖旧S2取消重启→新入口→GR结果/清理→CAT接续→安装及数据证据→唯一最终结果。C协调器USB配置额外GR/CAT授权与失电/69%/活动否决通过。check_usb_bench_readiness统一软件检查通过，源码未变；不算实板安装。CAT入口官方实际编译/解压读回51文件，LuaDB519833，USB文本main再编译预计合并520567/524288，余3721。sourcecheck目录仅内部模板容量检查，绑定旧R3MD5，禁止给用户下载。现在软件准备齐可统一请用户F7 BASELINE_USB_BENCH与TARGET_USB_BENCH，均不Download；收到新HEX才签名/打唯一新包并绑定最终CAT入口，一次交付。新GR未编译，最终ZIP仍不存在，S2实板仍CANCELLING，rawKV未验收非阻塞。详见2026-10-24_USB台架三缺口联测与统一交付.md。


## 最新最终交付：用户已编译，R4/CAT入口/GR签名载体齐备
两份USB GR实际21:01已编译0错0警，正文428352、签名429256。撤回Codex编译后额外纯识别输出，避免用户重编；现在按实际AXF/HEX/正文hash+反汇编USB函数链冻结BUILD_VERIFIED，不依赖新增文本标识。新基线签名6f006473...、目标96bc08c5...独立PSS通过。唯一上传OTA_Packager/output/1.0.2---1.5.0_R4.ypota.zip，692948，MD5 5c38e1d5e9615c98deeb76c77646124a，SHA256 7ff4090024561988635fee275416430fed1b5d9816dcbd27abf32b701553beec。CAT最终入口已固定R4，目录Air780EGH/_ota_release/usb_bench_final_20261024/baseline/USB_IMPORT，51文件，主机预计520567/524288余3721，官方原生编译/解压与USB非main读回通过。GR新签名载体firmware_releases/gr_usb_bench_20261024/baseline/SIGNED_DOWNLOAD_AFTER_CAT_HOLD/STAGE1_DOWNLOAD.uvprojx，只Download不F7，实际使用上一载体保存配置。下一步用户先CAT51脚本保留FSKV，再GR签名载体；并行上传R4给新直链。未操作设备，新集合未烧入，实板仍旧S2 CANCELLING。新基线运行后核usb_bench_test=1、正文428352验签与精确取消收据→IDLE，然后一次本地启动R4；不重跑R3、不清任务。详见2026-10-24_R4唯一实板交付清单.md。


## 最新实板：R4已上传、基线和CAT均匹配；卡在漏配Boot绑定/SCA，勿重烧APP
R4后台文件692948且hash完全匹配。JLink r/g恢复下载算法停留后，GR报告usb_bench_test=1、正文428352、验签成功；CAT on/key后MQTT在线，业务bat_known=1/89。实际Luatools51成员与最终R4集合全部匹配；OTA_TRIAL_START=无效探测返回ARGUMENT证明入口存在，未建任务。旧S2 CANCELLING物理否决已命中boot_open失败。SCA load/run=0x202000（FLM线刷改回A），实际Boot36KiB读回与先前已验收34044字节完全匹配、尾FF，Boot journal8192全FF。既有BootEMPTY启动仍绑定427328/65cefb...旧基线，不能只恢复SCA否则新基线无法启动。已承认这是交付漏配，不再查充电、网络或重编APP。新增prepare_usb_boot_binding.py生成唯一BOOT_BIND_USB_BASELINE.uvprojx，路径firmware_releases/GR_BOOT_USB_BASELINE_20261024；只改provision baseline长度/hash为428352/f8e0a254...，批准位/信任/布局/算法/SDK保持。静态配置比较通过；等用户只F7这一个Boot（暂不Download），然后工具--verify要求新旧Boot除描述40字节范围外完全相同，再做保护区前后回读并部署Boot路由。两APP不重编、CAT不重下载、R4不换不重上传。未启动OTA、未Flash写入、实板未验收。详见2026-10-24_R4实板启动链遗漏定位与Boot配套更新.md。


## 最新：Boot已编译核对，待用户只Download
用户Boot编译0错0警，AXF存在而工程未自动HEX，已仅fromelf导出实际HEX，prepare_usb_boot_binding.py --verify通过，34044字节且仅baseline描述40字节范围变化，其余原Boot字节完全一致，hash97e1ccfe42fed43fef0934af239402424d9208ec246e546a1d9e9dd081504ba3。已取本次新鲜下载前A429256与签名基线逐字节一致，preserved73728/NVDS8192长度与hash核对，记录r4_before_boot_rebind.json。待用户只Download firmware_releases/GR_BOOT_USB_BASELINE_20261024/BOOT_BIND_USB_BASELINE.uvprojx（不F7、暂不复位），然后读回新Boot/SCA/保护区，恢复运行接续S2取消→R4。CAT入口已实测ARGUMENT存在，51payload与R4匹配；R4后台hash已确认，地址仍用本轮用户ff808081a09d8f2401a16e1fe444005a链接。不能再让用户重传包、重下CAT或重编APP。


## 最新：Boot下载算法加载错误，已生成匹配成功J-Link模板的只下载载体
截图Cannot Load Flash Programming Algorithm，FLM实际存在。BOOT_BIND_USB_BASELINE仍为旧FC1000/UL2CM3配置，与成功R4应用载体不同。已新增firmware_releases/GR_BOOT_USB_BASELINE_20261024/BOOT_DOWNLOAD_ONLY.uvprojx及同名uvoptx：复用成功STAGE1_DOWNLOAD的FlashDriverDll/完整J-Link选项，TargetName匹配，源码组清空，输出指向已验证Boot AXF。AXF/HEX/BIN哈希均未变，download_carrier_verified.json静态通过；未烧录，实际算法加载待验。用户关闭旧工程后打开新载体，只Download不F7、不主动复位。之后先回读Boot/SCA/A/保护段，再恢复运行取消S2和启动R4。不重编APP/Boot、不重下CAT、不重传R4。详情见R4实板启动链遗漏定位与Boot配套更新文档末节。

## 最新：按用户要求J-Link恢复GR并成功启动CAT1
本轮未编译/未烧录。J-Link初始PC=0x20000000（下载算法停态）；停态XIP回读全部FF，属于无效读回，不能作为Flash擦除/数据变化证据，r4_after_boot_rebind_verified.json未通过，禁止当验收件。复位立即停核读取亦未得到有效SCA；随后r/g恢复GR业务，COM26可应答。cat1_power on返回rail_request=on/code0，未见CAT端口后仅发送一次cat1_power key，返回code0。随后实际出现COM21/22/23，CAT日志REG=1、IP_READY、MQTT CONNECTED，CAT1已开机联网。证据r4_restore_mapping.txt、r4_cat_power_on.txt、r4_cat_power_key.txt。Boot/保护段有效运行态读回仍待补齐，不把本次上电写成OTA安装验收。

## 最新22:18：R4已真实下发/授权，确认顺序流与每轮validate冲突
运行态Boot/SCA及A/保护段/NVDS全部读回通过，证据r4_running_boot_verified.json。原停RAM时全FF读回无效，不能当擦除；已纠正。R4只发一次，QUEUED→ACCEPTED_PENDING_GR→GR_GRANTED，后PAUSED/DOWNLOAD_PENDING；FS占用多次40960，精确checkpoint尚未导出。主机真实R4+实际platform/seq/bundle复现：首组件4096字节保留流，下一轮manager.validate重新开HTTP，被busy拒绝，返回BUSINESS_PAUSED；reason残留DOWNLOAD_PENDING。证据r4_stream_validation_collision.json。全面评估及唯一执行顺序见2026-10-24_R4全面评估与顺序流校验冲突.md。应修同任务可信元数据复用、stream owner生命周期和即时进度；不能重复下发/清任务/乱改HTTP_BUSY。当前尚未修改固件或烧录修复，实板OTA未通过。仅修维护基线可继续同一R4首次试验，R4目标仍含旧下载逻辑，不能宣称正式后续OTA能力通过；正式目标修复需另签包且不得覆盖活动R4任务。

## 最新22:29：顺序流冲突修复已落源码/联测/唯一CAT集合
已改ota_platform（已验签元数据RAM缓存，业务/版本/组件顺序仍实时）、ota_runtime（pause/失败关闭自己的bundle通道、回报durable字节与即时tick原因）、update FOTA_STATUS（OTA_PROGRESS/OTA_STEP）。新增test_mapper_stream7项，完整GR哈希/同连接跨块/断线续读/缓存失效/顺序门通过；共7组相关测试exit0，实际官方构建和原生解压读回通过。唯一给用户下载目录Air780EGH/_ota_release/stream_fix_20261024/baseline/USB_IMPORT，51文件；native520829，USB预计521563/524288余2725。已用异步问题通知用户只下载脚本保留FSKV、不动GR/Boot、不重投R4。源码和集合已冻结streamfix_delivery_verified.json；当前设备尚未下载此修复，不能宣称OTA通过。官方旧09:35CLI导致的无用libfota2容量拒绝已避开，使用17:22已验证ReleaseCli生成；旧产物未交付。首次R4目标仍旧下载代码，试验通过不等于正式后续升级能力。后续先核实际Luatools51成员与新进度，再连续接续安装。详情doc/2026-10-24_CAT1顺序流冲突修复与唯一维护交付.md。

## 最新：下载前沿已落地429256/429256，新前沿GR许可拒绝
stream_fix已实际51成员匹配、整库CRC/MD5通过，实板下载进度持续增长并在一次network_error后自动续到完整429256。随后GR_NACK_7；只读快照receiverready1/session2/total429256/hash与owner及已提交journal一致，accepted/durable0，两页CRCcommit通过。不能由事后快照认定历史具体gate；未改GR。CAT把permit拒绝误归永久坏包是确定的软件缺陷，已补同帧3次有界重发及旧GR_NACK7分类修正（必须live reconcile+签名validate+count<3，保留count/deadline），其他永久坏包仍锁。6组相关检查通过。新唯一目录Air780EGH/_ota_release/permit_retry_20261024/baseline/USB_IMPORT，51文件，native521181，USB521915/524288余2373，源码/官方编译/解压读回/USB预期核对通过。已异步请求用户只下载脚本保留FSKV/活动R4/完整候选；GR/Boot/R4不变，无新OTA_TRIAL_START。本版尚未部署，后续先核actualmerge和OTA_STEP/进度再接续安装。证据permit_retry_delivery_verified.json、streamfix_gr_nack_snapshot.json、permitfix_*.txt。实板OTA未验收。

## 2026-10-24收尾总结：以此状态覆盖前面的旧“最新”
见doc/2026-10-24_OTA工作总结_已解决问题与转圈错误复盘.md。现有R4完整GR候选429256保留，GR B接收器持久进度98304后停于GR_NACK7/FAILED_HASH_LIMIT。许可重试版已实际51成员匹配；已在rx_allowed失败断点捕获运动年龄1620>1500ms。GR源码已修motion提前刷新/观测时钟，host业务回归及实际BSP helper通过；用户新基线编译0错0警，428352正文hash5fda2c0e...；signed429256 hash7ca15704...；字节不变的SIGNED_DOWNLOAD载体已生成，尚未部署/最终下载工程尚未齐。新Boot工程firmware_releases/GR_BOOT_MOTION_BASELINE_20261024/BOOT_BIND_MOTION_BASELINE.uvprojx已生成但compiled=false。用户已批准仅额外1次（总4，保留原3）；当前只写了红灯约束测试test_gr_recovery_once.py，manager尚无authorize_gr_recovery，未更改3次上限、未使用恢复机会。下步补Boot真实构建与单次票据、成套部署，不重下R4/不重编相同基线/不清任务或次数。实板双端OTA仍未验收。

