# OTA唯一验收与固件准备表

## 当前有效状态：按此执行，不使用下方历史待办
> SAM | 2026-10-24 +08:00 | 第3步候选准备已完成，唯一目录 `Air780EGH/_ota_release/first_trial_20261024`：CAT基线2f0dc71f7b9d…、目标2655f1eaa913…，两版LuaDB523248；GR目标复用不重编。唯一USB入口baseline/USB_IMPORT_FINAL，52文件，主机重建524033/524288，实际Luatools合并及基线部署未完成。第4步仍需明确首次受控试验准入，不能伪填生产验收true。见 `2026-10-24_第3步基线与目标候选准备.md`。
> SAM | 2026-10-24 +08:00 | 第2步限定首次试验准入代码已接通：显式本地配置＋匹配运行身份＋签名同底包纯脚本构建记录，新增8项针对测试通过，默认未配置仍关闭；尚非实板准入部署或安装验收。第3步需真实审查配置与基线/目标统一准备。先前5278a7c0ae9c SOTA已因本轮源码变化降为历史候选，不要求下载。详见 `2026-10-24_第2步首次受控试验准入代码.md`。
> SAM | 2026-10-24 +08:00 | 上下文压缩入口 `OTA_当前压缩接续.md`。第2步新增最后一块原生调用内部异常/即时复位两项主机故障测试通过，保留提交不确定性且不重放；生产Lua未改，不因测试重生成固件。尚未完成精确底包限定的首次实板试验准入，原生/HTTP开关仍关闭，不能称第2步或实板OTA全部完成。
> SAM | 2026-10-24 +08:00 | 首次例外已限定1.0.2→1.5.0；新增容量问题已解决：目标SOTA 5278a7c0ae9c…，LuaDB520601/524288，原生格式及解压读回通过。源文件保留，仅镜像省略未引用旧libfota2，未放大分区。唯一候选和证据见 `2026-10-24_首次OTA策略新增容量问题已关闭.md`；这不是整机可安装ZIP，不要求再次刷诊断版。后续不重复处理容量项。
> SAM | 2026-10-24 +08:00 | 用户明确批准首次同底包脚本OTA采用可读数据对照，原始KV取证保留未完成且不阻塞。已实现显式策略：未初始化KV不init，比较根文件并记录kv_acceptance=UNVERIFIED；KV可读则仍完整比较键值，前后范围/摘要不一致拒绝。require_data_identity继续true；原生激活及HTTP门未放开。当前接续第2步原生激活安全，不再等待USB raw KV。见 `2026-10-24_首次OTA可读数据策略落地.md`。下方历史“等KV入口才推进”不再作为当前待办。
> SAM | 2026-10-24 +08:00 | 新增已关闭项：已直接核对官方课程§5.4/§8.5，正常FOTA保留LFS/KV的厂商说明成立，无需重复搜索。第1步仅剩本板完整KV可靠取证入口；FlashToolCLI离线TryConnect已到串口禁用边界，连接后副作用未证明。详见 `2026-10-24_CAT1数据保留官方条款与USB读回剩余边界.md`。下方“缺厂商数据合同”等历史笼统表述以此细分为准，安装门不变。
> SAM | 2026-10-24 +08:00 | 已核对用户提供的合宙EPM官方OTA自建服务器及核心库正文：支持原生组件分段写入、重启后确认实际版本，沿用现有ZIP解析与官方FOTA路径；正文未补齐V2052未知KV无损读回或最后一块后的撤销保证。第1步状态不变，不重测已通过项目。见 `2026-10-24_用户提供合宙OTA开发资料核对.md`。
> SAM | 2026-10-24 +08:00 | 用户已批准第1→5步顺序执行。当前仅第1步：官网调查已收敛，未知KV取证尚未关闭。官方flashdump细则跳转飞书登录，公开资料未取得匹配V2052的无擦写全KV读回规程；不执行猜测读回命令，不推进安装。完整记录见 `2026-10-24_获批五步计划_第一步官网取证结论.md`。后续仅在得到该缺失规程/接口后继续，不重复查已排除路线。

SAM | 2026-10-24 +08:00 | Boot实板首次接入已完成；不重测分区、容量基线、WDT、现板签名或旧包只读下载。GR编译和下载由用户手动执行。此次系统级检查发现安装路径仍被软件准入关闭，不能靠再次下载旧ZIP解决。

| 阶段 | 当前结论 | 唯一后续动作 |
|---|---|---|
| GR SDK/布局/用户保护范围 | 固定SDK1.0.4与已定布局 | 保持，不重新规划 |
| GR现板基线 | 1.0.2/build3，427328正文+904签名；WDT与原生验签实测通过 | 保留现板，不USB覆盖目标1.5.0 |
| GR Boot | 实板部署、SCA路由、受控复位进入原应用均通过 | 关闭首次接入项 |
| GR本次部署数据保持 | 原应用和所有非计划区域与下载前完整副本相同 | 沿用证据，不当作真正OTA后数据保持 |
| CAT1当前基线 | 最新实板记录1.0.2/build3诊断修订5 | 安装源码变化时再准备唯一新集合 |
| 客户HTTP200/chunked、整包MD5、签名、双组件摘要 | 真实蜂窝只读COMPLETE通过 | 关闭，不再重下载验证 |
| 现有后台ZIP | 685625字节，MD5 48186cc7b9585801a9c06376af0a8115，device_installable=false | 仅保留解析夹具；禁止作为安装输入 |
| GR目标1.5.0 | 用户新编译0错0警告，正文427328+904签名，1.5.0/build4已独立验签冻结；target_verification.json | 已完成，勿USB下载覆盖现板；后续打包使用当前HEX，不再要求重编 |
| CAT1生产网络准入 | ota_device_options.lua的native_rx_limit_verified仍false | 用已取得的精确底包接收证据制定准入，不用诊断成功替代生产接线 |
| V2052最后一块激活边界 | 已前移数据复核/持久提交意图，5项新回归及相关回归通过；未部署 | 沿用源码修复，不再查同一结论；真实准入成立后统一打包 |
| CAT1原生激活 | native_contract_verified始终false，原生安装start明确拒绝 | 闭合该精确底包安全/数据合同后再启用，不能硬改true |
| 打包安装策略 | 新增PackageForDevice与GUI/CLI显式准入入口，绑定版本/组件/底包/证据，普通和离线入口仍false；主机回归通过 | 尚缺真实CAT1原生/只读数据准入记录，不生成虚假可安装包 |
| V2052未知KV只读入口 | 已有ELF/模块表确认sfd未导出；本轮匹配ELF指纹，关闭重复查源路线 | 取得受支持的只读接口后再接入；不初始化KV、不生成重复诊断固件 |
| CAT1数据保持与真实双端OTA | 软件链已有；跨真实安装仍未验收 | 在可安装包与原生准入成立后执行一次完整N→N+1 |

执行顺序：准备正确目标产物→闭合生产准入/原生合同→生成新签名安装包→上传新包→真实任务安装→两端实际版本/数据/结果验收。原ZIP和本板Boot测试批准不自动放开整包/CAT1安装。不再把签名解析通过说成接近完成整机安装。

## 本轮准备边界

准备一套当前1.0.2/build3的匹配基线候选：复用已编译GR，CAT从唯一源码入口生成本轮原生脚本产物并核实际容量。该生成只为此次基线准备，不是同版本OTA验收；不上传、不烧录、不改版本、不创建整机OTA ZIP。

不使用旧Build-VersionedRelease.ps1自动流程：其仍包含交付副本检查/编译及改版本行为，与当前用户要求冲突。本轮使用现有生成核心与明确的主工程产物。

原生激活及HTTP门当前保持关闭，基线候选不等于可完成实装。精确待补项见上表，不能扩大为“全部重新测试”。

## 引用证据

- `doc/2026-10-22_CAT1原生SOTA生成与文件选择修复.md`
- `logs/ota_vendor_gate_20261023/identity_readonly.txt`
- `logs/ota_vendor_gate_20261024/sources.json`
- `logs/ota_installation_result_20261024/results.json`、`source_artifact_hashes.json`
- `logs/ota_data_transaction_20261024/results.json`、`source_hashes.json`
- `doc/2026-10-24_CAT1安装结果门禁改接与验证.md`
- `doc/2026-10-24_CAT1数据保持证据接入原生OTA事务.md`

产物准备结果将在本表下方追加；未追加前不视为已生成。

## 已准备的唯一基线候选

目录：`firmware_releases/baseline_candidate_20261024`，清单 `baseline_manifest.json`，操作边界见目录README。

| 产物 | 结果 |
|---|---|
| GR HEX/AXF | 复用10-24构建，归档HEX及对应源码hash与构建记录一致；本轮未重编 |
| CAT原生SOTA | CAT1_TK_PROJECT_OTA_001.000.002_c3c97fde66c4_2f4584.sota；242779字节；SHA256 c3c97fde66c4e914a8b5aa7c7f00abe9095e751c1b9d44c1bee751e2a671ca07 |
| CAT LuaDB | 500586/524288，余23702字节；现有生成器容量/格式/解压读回通过 |
| CAT原生OTA预算 | 242779/974848，余732069字节；沿用原布局不改区 |
| USB完整导入目录 | CAT1/USB_IMPORT，49文件，共502368字节；最终Luatools合并尚未执行，不能把合计视为实际合并容量 |
| 版本 | 两端001.000.002/build3，产品1.0.2；不是目标1.5.0，不改嵌入版本 |
| 交付hash | 52个产物逐个核对，所有根Lua源码hash记录在manifest |
| 实板/平台 | 未烧录、未上传、未生成整机ZIP；不构成实板验收 |

本轮仅文件准备，无生产源码修改，不需要重跑协议测试或Keil构建。上述候选替代早先不包含最新接线的同版本准备目录；历史文件不删除，但不得混用。后续优先完成本集合的Luatools最终合并与实板只读取证，不重新计算固定分区或重复已过的主机用例。

## 2026-10-24 本轮 Luatools 合并接续记录

SAM | 2026-10-24 +08:00 | 固定当前阻塞点，防止将旧窗口状态误用为新候选证据。

- 已定位 Luatools v3.4.14，当前项目仍是 `Air780EGH_antenna`，不是本轮49文件集合的已验证项目。
- 窗口显示V2052 Air780EGH、下载成功/已使用413KB，但这只是窗口保留状态；不能证明本轮候选已合并、已烧录或设备当前在线。
- `D:/Installers/_temp/project/core`、`download`仍为2026-10-23 10:33的旧目录时间，没有取得本轮新合并产物。
- 自动点击“项目管理”失败：`coordinate input geometry is unavailable`；重新枚举、定位并激活窗口后，截图失败：`FrameArrived timed out: timed out waiting on channel`。停止重复点击，不改用盲点坐标。
- 本轮没有烧录、重启、擦除、改源码或重新编译；现有候选及已通过证据继续有效。
- 唯一下一动作：将Luatools主窗口恢复可见并打开“项目管理”，完整导入本候选 `CAT1/USB_IMPORT` 的49文件，先生成合并产物；保留FS/KV，不点下载。取得新script.bin后核对实际大小和模块完整性，更新本表后再进入部署。

### 新生成文件的实际读回结论

SAM | 2026-10-24 +08:00 | 用户表示已完成后，直接读取Luatools当前script.bin核实。

- 当前script.bin为422912字节，LuaDB解析出39个业务文件；头部及内置MD5校验通过。解析内容止于422737，余175字节不作为业务文件解释。
- 与本轮49文件候选比较：缺10个模块，另10个既有字节码与候选不同。具体清单与SHA256：`logs/ota_usb_merge_20261024/current_merge_comparison.json`。
- 结论：当前合并仍来自旧集合，不能下载作本轮基线。不是容量超限；需要替换项目输入集合后重新生成。
- 项目管理实际仍显示baseline_20261023_2ee715ad/luatools_explicit；量产报告显示39文件。自动点击关闭仍报窗口几何不可用，键盘Escape也未关闭报告，未触发烧录。

## 当前候选更新：USB文件名限制已修复

SAM | 2026-10-24 +08:00 | 用户实测揭示新集合中的ota_candidate_files.luac有24字节，Luatools上限23字节；此前仅要求替换目录不足以消除此阻塞。

**当前唯一候选改为 firmware_releases/baseline_candidate_20261024_usbfix。上方旧目录及旧SOTA/hash仅保留历史记录，不再使用。**

- 模块改名ota_candidates，运行引用同步；持久数据路径不变。
- USB49文件，全部文件名≤23个UTF-8字节；生成器及USB导出新增对应拒绝门。
- 新LuaDB500576/524288，余23712；新SOTA242807/974848，SHA256 e3dda7e954658e69fd51187e2ec45262c850e1d383abeffca3b13e0968f2b1d4。
- 版本仍001.000.002/build3、整机1.0.2；GR复用既有构建，无需重编/重烧GR来解决本问题。
- 边界回归先失败后通过，候选IO四项及数据事务五组通过；新SOTA生成解压读回、49文件名扫描与53个归档hash通过；GUI编译和启动自检通过。
- 下一项仅为用新USB_IMPORT替换旧项目输入并核对Luatools最终合并。未完成新合并/烧录/真实OTA验收，其他证据门状态沿用，不重复规划容量。

详细修改与逐项检查：doc/2026-10-24_CAT1_USB导入文件名23字节限制修复.md；证据：logs/ota_usb_merge_20261024/namefix_verification.json。

## 已关闭：修正版Luatools最终合并验证

SAM | 2026-10-24 +08:00 | 用户生成49文件报告后直接读回本轮script.bin；此项已通过，后续不再重测本集合。

- 文件数49；无缺失、额外或内容不同模块。main用相同厂商编译器对USB文本入口重新编译后逐字节一致，其余字节码/音频直接与USB_IMPORT比对。
- 所有LuaDB头校验及内置MD5通过；实际script.bin501760/524288，余22528（22KiB）。内容501546字节，尾部填充214字节。原生SOTA的500576字节是另一入口生成的已验证镜像，不拿两者大小差异当缺文件。
- SHA256 ca67fea9f6a454063e2c0bf978b60bea8280afe16e4ba1993d34944d0e8d96ba。取证logs/ota_usb_merge_20261024/final_merge_verification.json；候选manifest已更新usb_final_merge_verified=true。
- 已归档CAT1/USB_VERIFIED/script.bin，取证目录不作为脚本导入目录。
- 下一项：保留FS/KV，仅下载当前新脚本集合，然后核对实际启动代码身份、数据可读性及恢复链路。本项通过不表示已经下载或真实OTA安装通过。

## 已完成下载与两端版本读取；当前仅定位数据审计失败

SAM | 2026-10-24 +08:00 | 用户本轮下载成功截图与COM26只读回包。

- usbfix集合脚本下载成功；FS/KV清除均未勾选。两端001.000.002/build3；CAT IDLE，正常main启动；GR-CAT串口命令回包正常。此项沿用，不重新生成已部署集合。
- 数据审计实板失败：complete=false/error=READ_FAILED。不是数据损坏结论，更不是保持验收通过。当前code_identity=NOT_CHECKED、GR ota_provisioned=0保留真实记录。
- 已补固定读取stage而不输出原始异常/用户内容，12组审计与5组事务主机结果通过。
- 待部署诊断：firmware_releases/baseline_candidate_20261024_audit/CAT1/USB_IMPORT，49文件且文件名≤23字节；LuaDB500993、SOTA242971。新诊断尚未合并/下载，不覆盖usbfix实板结论；下一项仅取READ_FAILED的具体stage。
- 说明：doc/2026-10-24_CAT1下载后只读数据审计阶段定位.md。实板回包：logs/ota_usb_merge_20261024/post_download_readonly.txt。

## 数据审计定位接续：已读到PORT_CHECK；诊断修订2已放回原导入目录

SAM | 2026-10-24 +08:00 | 不重跑usbfix集合的合并/下载/启动验收，只缩小当前异常。

- 已从项目INI、下载成功状态和实板带stage回包确认诊断修订1已运行。OTA_DATA_AUDIT返回READ_FAILED/PORT_CHECK；随后FW_VERSION仍可正常回报IDLE，排除整个OTA状态查询都不可用的判断。证据audit_stage_device.txt。
- PORT_CHECK还包含scan最初的业务空闲检查；不能据此断言文件系统/KV坏或已读取。修订2在执行最初guard前标为IDLE_CHECK，并对白名单内部错误码允许剥离原生运行时前缀；未知异常仅报告CALL_FAILED/INDEX_FAILED/STACK_FAILED/NATIVE_EXCEPTION，绝不输出原始异常或用户内容。此改动用于定位，并未宣称已找到底层最终原因。
- 新增回归先失败后通过；13组审计输出和5组事务输出通过。修订2原生SOTA生成解压一致：243192字节，LuaDB501619字节，SHA256 d5a864ab49b760002a411588df41f0256634a19495af322515d40d8cbef93de4。
- 为免用户反复换目录，当前Luatools已经引用的baseline_candidate_20261024_audit/CAT1/USB_IMPORT原位只更新ota_data_inventory.luac、update.luac，其他47文件逐字节一致。旧49文件完整保存在revision1_USB_IMPORT，旧清单revision1_manifest.json。当前diagnostic_manifest.json明确revision=2、flashed=false。
- 尚未执行修订2下载。Windows自动控制仍存在窗口几何不可用/截图超时；尝试系统菜单恢复后仍未恢复，未盲点下载或转为不明串口写命令。已核对官方FlashToolCLI历史仅写flexfile2的调用记录，但未因缺少受控进下载模式合同就擅自调用。
- 必须的下一动作已缩至现有项目点一次“下载脚本”（FS/KV不清），不用换目录或重编GR；回包后仅追踪IDLE_CHECK/具体读阶段，不重开全面测试。

## 最新接续：修订2已运行；模块缓存依赖修复为修订3待部署

SAM | 2026-10-24 +08:00 | 只推进IDLE_CHECK入口异常。

- 修订2实板：READ_FAILED / IDLE_CHECK / INDEX_FAILED；日志audit_revision2_device.txt。此回包证明修订2诊断已运行，不再重复下载修订2。
- 定位：ota_platform空闲/主题及ota_runtime健康代码裸访问package.loaded。官方当前加载器采用内部注册表，活动实现不提供该标准字段；主机package=nil精确复现原空值索引。公开源码不替代V2052实板闭环。
- 修复：main加载已有MQTT/业务对象后显式绑定；默认适配、健康观察共用绑定对象。缺失服务保持拒绝，标准Lua缓存只在存在时兼容。无KV/Flash/GR布局改动。
- 六个定向测试脚本及三个Lua语法通过，原生生成/解压读回通过。修订3LuaDB502149，SOTA243385、SHA256 14776bc2e50032f1fbce39bc238f2f3c79ca9c76a5c3924d1ba6df7744fbd2a2。
- 当前项目路径不变：baseline_candidate_20261024_audit/CAT1/USB_IMPORT，49文件；只更新main.lua、ota_platform.luac、ota_runtime.luac。修订2备份revision2_USB_IMPORT及revision2_manifest.json。当前manifest revision=3，尚未下载/实板确认。
- 下一步仅下载现有新脚本并读取OTA_DATA_AUDIT；不重算空间、不重测版本/启动、不下载旧修订。详见doc/2026-10-24_CAT1_LuatOS模块缓存访问修复.md。

## 最新：修订3实板索引错误已关闭；修订4修复真实停止SIP仍被判忙

SAM | 2026-10-24 +08:00 | 沿IDLE_CHECK继续，不重测已通过集合。

- 修订3已下载，实板回包BUSY/IDLE_CHECK，无INDEX_FAILED，package.loaded异常修复已得到实板证据。记录audit_revision3_device.txt。
- 当前只读SIP_STATUS=STATE_IDLE，NTP已同步；业务事件network=mqtt、call=unknown。原因是按需未启动SIP没有READY事件，业务从初始unknown无法变成已知无会话。
- 修订4绑定SIP实际状态，停止/启动/清理生命周期同步至业务门禁；拨号/来电/连接/初始化/报警仍拒绝，迟到STOPPED不能覆盖新会话或活跃业务通话。
- 定向业务7项、SIP真实包装层host测试及相关审计/事务/健康/runtime回归通过；三个Lua语法及native生成解压通过。LuaDB503167，SOTA243705，SHA256 497666e8c6c903e0495c9b23da3ca841a4f603ee0800149a87a580e6785b46dc。
- 当前同一USB_IMPORT路径已是revision4，仅改business_runtime.luac/main.lua/sip.luac，其余46文件不变；旧revision3完整备份；当前manifest flashed=false。
- 下一项仅下载现有新脚本并读取OTA_DATA_AUDIT，确认扫描是否开始。修订4未下载/实板验收；数据保持及真实OTA未通过。详见doc/2026-10-24_CAT1_SIP停止状态导致OTA忙门禁修复.md。

## 最新：修订4实板揭示SIM异步快照覆盖；修订5同目录待部署

SAM | 2026-10-24 +08:00 | 本轮仅修复忙门禁的网络恢复时序。

- 修订4回包仍BUSY/IDLE_CHECK。当前合并中的相关模块匹配，main包含bind_sip_status。启动日志证明先call=idle、随后call=unknown，再registering/mqtt；不是未下载新文件。证据audit_revision4_device.txt、revision4_timing_evidence.json。
- 已补真实事件顺序回归：绑定停止SIP→异步SIM RDY→MQTT ready，先复现失败再修复。MQTT确认当前SIM/IP正常后重新查询同一真实停止状态；活跃会话不被覆盖，SIM/IP失效仍拒绝。
- 当前同一路径USB_IMPORT已是revision5，仅改business_runtime.luac，其余48文件不变；旧修订4已完整备份。7组定向测试脚本及Lua/native生成解压通过。
- LuaDB503197、SOTA243727、SHA256 4d115e726d9adc9e9cb14d9fac8a9e02ef49aa2af0561f85e8e797a7909c3849；当前manifest revision5/flashed=false。
- 下一项仅保留FS/KV下载现有脚本，读OTA_DATA_AUDIT。修订5未实板确认，数据扫描/用户数据保持/真实OTA仍未通过；不重开已通过的SDK/布局/启动验证。

## 最新：修订5实板已越过空闲门禁；当前唯一数据审计阻塞为KV未初始化

SAM | 2026-10-24 +08:00 | 本轮不再生成Lua候选或让用户重复下载。

- 修订5已下载；当前合并中的变更模块已匹配。OTA_DATA_AUDIT回包KV_STATUS/KV_UNAVAILABLE，原生日志明确call fskv.init() first!!!。记录audit_revision5_device.txt、revision5_kv_blocker.json。
- 模块索引错误及SIM恢复后永久BUSY关闭，不再重测；根文件第一遍处理已走到KV检查，但整个双遍审计未完成，不能称用户数据保持通过。
- 公开源码以及底包map对应SFD路径：标准KV初始化在mount失败时会自动format；本轮未调用init/clear等，不能把未初始化KV视为空。
- 已整理具体只读挂载／受控原始区读取接口要求、源码hash及故障验收：doc/2026-10-24_CAT1_KV只读审计接口缺口与验收条件.md。当前缺底包层无格式化读取能力，不通过再改一次Lua或重复烧写解决。
- 当前manifest revision5已更新flashed=true，真实OTA/用户数据保持仍未验收。下一项落实只读KV原生能力，保持数据与激活门禁，不清KV、不假data_ok。


## 最新：原生KV读取缺口已完成查源，等待匹配工程或厂商能力

SAM | 2026-10-24 +08:00 | 本轮只查源，无固件修改、下载或重复设备测试。

- 当前ELF内部有sfd_onchip_read但无luaopen_sfd，Lua缺少安全原始KV读取入口。
- 官方同名GitHub源本轮404，Gitee403；第三方2025年EC716/EC718镜像不能证明匹配当前Air780EGH V2052，不作为构建输入。
- 已生成可直接转交厂商的精确请求：doc/2026-10-24_提交合宙_V2052只读KV接口请求.md，包含SOC/ELF指纹、有界只读接口及零写入验收条件。
- 不生成修订6，不调用fskv.init，不以未初始化等同空库。修订5及已通过项不变；数据保持和真实OTA仍未验收。


## 官方产品支持范围更正：不能以公开 CSDK 自行补齐

SAM | 2026-10-24 +08:00 | 用户授权重新网上下载后，取得官方型号资料，纠正此前匹配CSDK下载方向。

官方 https://docs.openluat.com/air780egh/ 明确：Air780EGH只支持LuatOS二次开发，不支持C-SDK，也不支持AT指令。此处AT指模块原生AT开发方式，不是本项目Lua自定义串口命令。

因此不能以EC718公开CSDK替代Air780EGH工程，也不能承诺下载通用CSDK后自行编译出匹配V2052底包。此前“等待匹配公开CSDK”的接续方向由本节更正。当前可行接续为合宙确认V2052安全只读接口，或提供支持该接口的受支持底包/定制支持；是否可提供私有原生工程须由厂商确认。

官方页面原文、摘录与SHA256已下载保存：logs/ota_usb_merge_20261024/official_air780egh_product.html、official_air780egh_product.txt、official_air780egh_csdk_support.json。未下载或使用不匹配SDK，未改固件/数据，未重复烧录；KV与真实OTA仍未验收。


## 接续交付：合宙支持材料包已准备

SAM | 2026-10-24 +08:00 | 现有flash/sfd导出及sfud/fs/otp/ndk公开入口核对未找到可直接替代的内部KV只读接口。详细结果在提交合宙请求文档末尾。

已生成 doc/support/Air780EGH_V2052_KV只读接口支持材料_20261024.zip，ZIP读回及逐文件SHA256通过；仅需求、公开源和脱敏证据，无固件/用户数据/密钥。不是OTA包。下一项为合宙确认受支持的无格式化读取方式或底包。没有新烧写或重复设备测试。


## 最新安排：厂商支持与本地路线同步；无备用板仅完成准备

SAM | 2026-10-24 +08:00 | 用户确认没有备用板，先完成本地准备。

- 厂商包沿用既有产物，未代发。新增本地路线与数据归属说明：doc/2026-10-24_OTA本地验证准备与用户数据归属.md。
- 44个CAT根目录Lua源码仅3处fskv引用，未发现直接KV初始化/写删调用；不能认定历史KV为空或跳过保护。文件业务和独立OTA日志已列明。
- 当前GR住户/时间开关源码明确为RAM视图；旧参数解析g_config未见落盘。记录业务持久化缺口，不把普通重启丢失误判为OTA破坏。未改业务代码或分区。
- logs/ota_lab_preparation_20261024/source_data_map.json冻结源码指纹，device_cases.json列8项实板用例，全部NOT_RUN；读回及来源SHA256复核通过。
- 无实板动作、无新候选、无版本变更，不生成修订6。实验入口尚未实现，生产门禁保持关闭。待专用板后按LAB0→LAB1顺序取证，现有板不调用fskv.init。真实OTA仍未验收。


## 最新本地落地项：冻结准备自动检查

SAM | 2026-10-24 +08:00 | 新增 tools/ota/check_lab_preparation.py，只读检查既有冻结材料，不接设备、不更新基线。

- 9项新定向测试通过，真实冻结目录检查有效；输出 logs/ota_lab_preparation_20261024/preparation_check.json。
- local_preparation_ok=true；device_ota_accepted=false。缺实板用例、KV只读能力、原生激活合同和备用测试板。
- 新工具拒绝用例伪造PASS/未知KV冒充空库及路径越界；源码变化报告差异，不自动重算旧通过项目。详见 doc/2026-10-24_OTA本地准备自动检查.md。
- 无固件修改、无新下载、无设备动作，不同步交付副本；不据此开放安装。


## 最新实质进展：主工程单份发布修复；目标1.5.0已经构建

SAM | 2026-10-24 +08:00 | 本轮不新增验收工具、不重复旧测试，修复实际发布脚本冲突并生成目标产物。

- Set-FirmwareVersion/Build-VersionedRelease已取消所有交付副本比较、同步、编译；Windows PowerShell5.1隔离版本测试通过。
- 已实际构建firmware_releases/1.5.0：主GR 0错误0警告，payload426304字节；CAT原生SOTA243733字节，LuaDB503197字节，USB导出49文件。两端001.005.000/build4。
- 当前根源码是目标1.5.0；实板仍采用先前1.0.2/build3记录，本轮未重读、未烧录。旧基线目录保持；交付版本头hash未变。
- 归档candidate_manifest.json及源码/文件hash已读回核对，生产门禁未开放。未生成可正式下发ZIP，不要求用户下载。
- 旧1.0.2冻结清单不覆盖；目标准备清单另存logs/ota_lab_preparation_20261024/target_1.5.0，检查材料有效，实板验收false。
- 业务数据归属补充：/yp001_business_0/1保存报警/电话白名单，必须保护；paraSetMsg在当前CAT业务链返回PARAMETERS_NOT_READY，不能假定进入GR旧g_config存储。
- 详细记录doc/2026-10-24_主工程单份发布修复与1.5.0目标候选.md。KV读取、原生激活/HTTP实板证据和真实OTA仍未验收；没有备用板，不操作现有KV。


## 最新官方路径决议：标准FOTA无需CSDK或KV初始化

SAM | 2026-10-24 +08:00 | 按用户要求补查官方现成流程，新增官网libfota2/3、同型号Demo和固定提交源码依据。

- 采用现V2052_113、仅脚本升级及官方fota核心库分块run；复用已有ZIP签名分发和GR串行owner，不换底包、不重写升级器。
- libfota2支持客户自建HTTP平台，但直接接入会边接收边进入原生FOTA；libfota3仅合宙平台，不直接采用。
- 官方公开fota.file实现内部调用done/end，不能当纯预下载。整个原生阶段均须在GR安全授权内，现项目保留run控制。
- 官网明确正常升级保留FS/KV，重启后版本可确认安装；CSDK/专用pending API/调用fskv.init均非标准OTA必要条件。此前将只读KV接口视作所有OTA唯一路径的表述更正：当前缺的是本项目完整数据取证，不是官方OTA能力。
- 未放开任何门禁；无备用板，当前实板数据与激活异常验收仍未完成。1.5.0候选沿用，不重生成。
- 完整对照doc/2026-10-24_合宙官网现成OTA流程与本项目采用路径.md；原文与hash在logs/ota_official_workflow_20261024。


## 最新已落地：CAT1原生缓存积压误判修复

SAM | 2026-10-24 +08:00 | 按官方fota.run语义修复明确软件缺陷，不重开基础测试。

- 原控制器把合法cache>64KiB当WRITE_FAILED取消；新失败用例已复现。现改为至少100ms非阻塞WAIT_CACHE，offset只推进一次，等待仍检查GR授权和原120秒总时限。非法返回仍拒绝。
- native_fota/data_transaction/default_native_path/runtime四组定向回归及厂商Lua语法通过；不能因此认定过去实板失败由此导致。
- 最新候选为firmware_releases/1.5.0_native_backpressure_20261024，替代上一1.5.0候选；版本/build仍001.005.000/build4，旧目标未发布/烧录，不再加版本。GR原归档hash完全相同，不重编。
- 新CAT SOTA243764字节、LuaDB503325字节，SHA256 a50dc5a53606ed05397bc48610bd489fbf4a7a7a0ec029ad6b483a0c2495ff25；原生生成/解压读回、49个USB文件名及hash核对通过。该修订最终USB合并未验。
- 未烧录、未出正式ZIP，生产门禁未开放；不要求用户现在下载。目标准备目录target_1.5.0_backpressure，原冻结记录不覆盖。
- 详细记录doc/2026-10-24_CAT1原生FOTA缓存等待修复.md；证据logs/ota_native_backpressure_20261024。


## 当前候选r2：HTTP发送积压等待已落地

SAM | 2026-10-24 +08:00 | 对照官方socket返回语义，修复瞬时full=true立即失败的问题。

- 接收限长第四参数与官方源码一致，保留不动；发送缓冲满改为20ms让出后重试，忽略满缓存时done，清除旧TX_OK；接受后不重发。原30秒总时限、暂停/关闭/清理保留。
- 新3项用例旧实现均HTTP_SEND失败，修复后HTTP16项通过。真实本机TCP联测341次请求/释放、最大读取512、两组件摘要一致；runtime及厂商Lua语法通过。仅主机证据，不是当前1.5.0或CAT模块安装验收。
- 当前唯一候选指针为firmware_version.json/built_release：firmware_releases/1.5.0_candidate_20261024_r2，累积两处缓存等待修复。两端001.005.000/build4不变，旧目标未烧录/发布。GR归档hash相同，不重编；49个USB文件仅ota_http_range.luac较上一候选变化。
- 新CAT SOTA243805、LuaDB503432字节，SHA256 14a29d2dcd04216ebd63ceedc468313445ff64c34af5a00e8a747d97f5756d3a。原生生成及解压/文件读回通过，该修订最终USB合并未验。
- 未操作实板、未生成正式整机ZIP；安装/数据/原生接收门不变，不要求用户现在下载。详见doc/2026-10-24_CAT1_HTTP发送缓存等待修复.md。


## 当前唯一离线签名ZIP：1.0.2 → 1.5.0

SAM | 2026-10-24 +08:00 | 补齐可实际下载解析的双组件签名归档；保持实板安装未验收。

| 状态 | 本轮证据 |
|---|---|
| 已通过：离线签名包 | firmware_releases/1.5.0_candidate_20261024_r2/OFFLINE_PACKAGE/YP001_1.0.2---1.5.0_LOCAL_TEST_OFFLINE_c6ea9a4c4bb5.ypota.zip；685625字节 |
| 已通过：本包本机下载/解析 | 352次TCP请求与关闭，最大读取512字节，两组件摘要一致；可信固定公钥验签通过 |
| 已通过：严格检查保留 | 核心64项、离线模式拒绝同版本及超限；源码与49个USB文件哈希未变 |
| 明确未知：实机空间 | cat_free_operator_input=null；LAYOUT_PROFILE_ONLY；requires_device_space_check=true |
| 未验收：实板 | 当前终端版本/空间、KV安全取证、原生安全激活与重启结果、平台/蜂窝及真实N→N+1保持数据；未操作设备 |

MD5：48186cc7b9585801a9c06376af0a8115。SHA256：0ef33a6725707dc695df54f7eb4973e5bebdf53a488854a476d961fb91d0d345。

本包LOCAL_TEST_ONLY且device_installable=false；仅用于离线/后台下载联调，不是安装授权。新增OTA_Packager/YP001OtaReleaseCli.exe的pack-offline命令，GUI未改。没有重复生成已签名包或重编GR；交付副本未操作。详见doc/2026-10-24_双端OTA离线签名候选打包与本机下载验证.md，机器证据logs/ota_offline_package_20261024/results.json。


## 本轮已落地：GUI离线候选入口

SAM | 2026-10-24 +08:00 | OTA_Packager/YP001OtaPackager.exe已更新；使用原启动BAT重开即可。新增显式离线复选项，默认严格空间检查不变。GUI定向测试及最终启动/布局检查通过；未改固件/核心、未重复生成ZIP、未操作实板。详见doc/2026-10-24_OTA打包工具离线模式界面落地.md。


## 本轮通过：原ZIP本机HTTP上传→下载→Lua解析

SAM | 2026-10-24 +08:00 | 同一685625字节ZIP实际POST上传201、完整下载200、Range206、越界416；下载逐字节一致，再交现有实际Lua/TCP解析，352次请求/关闭、最大512字节，验签与两组件摘要通过。客户平台=false、蜂窝=false、device_ota_accepted=false；没有设备动作。证据logs/ota_upload_download_20261024/20261024_095159_013226/results.json，说明doc/2026-10-24_双端OTA原包上传下载与Lua解析实测.md。原包未改，未重打包。


## 最新安装链结论：不是只缺CAT1开关

SAM | 2026-10-24 +08:00 | 只读源码审查确认：现ZIP严格/离线均不可安装；GR候选Boot许可0/0/1，若直接作为启动Boot部署会拒绝跳转并复位。HTTP及CAT原生门仍固定关闭，隔离实验入口未实现。不得以应用provisioned或主工程下载证明Boot就绪。按只读网络实机入口→GR首次部署取证→CAT受控实验→受控签名包→串行实装推进，不重复容量/主机下载测试。详见doc/2026-10-24_双端OTA安装链实质阻塞与最短落地顺序.md。无固件/设备动作，真实OTA仍未验收。


## 只读诊断接线与信任合同补充

SAM | 2026-10-24 +08:00 | 确认现组件口强制GR所有权/先GR安装完成，不能给实机诊断填假完成；网络验证入口需与生产门区分。合同整文件hash与当前App pin相符，但批准字段改变会使旧pin失配，须首次部署前冻结后统一Boot/App/签名。当前未改任何合同/固件，未实现新诊断命令。客户新URL尚未提供，不能证明其206/ETag合同。详见doc/2026-10-24_实机只读下载入口与信任合同接线分析.md。


## Filebin新包实际下载与解析通过

SAM | 2026-10-24 +08:00 | 用户已将当前包上传Filebin；真实电脑下载685625字节、整包hash与候选一致，Range/If-Range通过。确切下载包经Lua/TCP352次请求验签与两组件摘要通过，固定组件已提取读回。入口需要Cookie→302→HTTPS，不兼容当前CAT原生HTTP下载器；没有蜂窝或设备安装动作。证据logs/ota_filebin_20261024/20261024_102307_144940/results.json；详见doc/2026-10-24_Filebin实际升级包下载与组件解析结果.md。


## 最新通过：实际公网Range响应直接进入Lua解析

SAM | 2026-10-24 +08:00 | Filebin本包229次公网Range读取、1371251字节、124.312秒；Lua签名、整包MD5、GR/CAT组件摘要通过，暂停未发新请求。电脑HTTPS适配器非原生CAT驱动；owner/完成/空间仍主机夹具值，不能作设备授权。首轮链接解析断言失败保留，后续完整运行通过；未操作设备、未改固件。见doc/2026-10-24_Filebin公网分段直读与Lua解析验证.md及logs/ota_filebin_20261024/live_20261024_102706_891997/results.json。


## 已落地源码：独立只读诊断与UART入口

SAM | 2026-10-24 +08:00 | ota_bundle.open_diagnostic/diagnostic_step、ota_http_range.new_diagnostic、update.OTA_NET_CHECK已实现，诊断无GR假完成或持久证明，无安装口；生产门保持。新增5+3测试、受影响ZIP20/HTTP16及runtime21组、厂商语法通过。原生诊断构建LuaDB509221/524288、SOTA245754，生成解压通过；当前版本1.5.0仅容量构建，不作现1.0.2板诊断基线。未实现Filebin HTTPS/Cookie/跳转，未部署，不要求用户烧录。原ZIP未改。详见doc/2026-10-24_CAT1独立只读诊断核心与UART入口落地.md与logs/ota_readonly_diag_20261024/results.json。


## 客户新地址已下载；真正新增阻塞为200/chunked

SAM | 2026-10-24 +08:00 | 客户上传的短名包实际下载685625字节，与原MD5/SHA256一致，签名/整包MD5通过。0起点及64非零起点Range均返回200文件开头，chunked，无ETag/Content-Range；当前严格Range代码不兼容，未在设备尝试。详见doc/2026-10-24_客户后台新地址下载与Range不兼容定位.md。

Filebin诊断TLS/Cookie源码接线与14项新增定向测试完成；相关回归通过，LuaDB515003/524288、原生包248644，未部署，不开放生产门，不代表客户200流式模式已完成。证据logs/ota_readonly_diag_20261024/results_tls.json。


## 200/chunked顺序路径源码通过主机验证，容量未通过

SAM | 2026-10-24 +08:00 | 新增原生流式HTTP和元数据缓存/串行组件提取，5项顺序测试、4项流式HTTP测试及受影响回归通过；后台不改，断网重读从零。native5实际构建被512KiB拦截，LuaDB核算524898，超610字节，禁止作为可烧写交付。原签名ZIP不变，安装门不变，无设备操作；真实服务器顺序解析/实板安装未验收。见doc/2026-10-24_CAT1顺序流式ZIP实现与容量阻塞.md。


## 已解决：200/chunked源码容量与客户公网顺序解析

SAM | 2026-10-24 +08:00 | 对本轮重复逻辑做等价精简，原生工具生成SOTA252097字节、LuaDB524277/524288（仅余11字节），结构/解压读回通过，源码hash与包记录一致。客户服务器原始TCP直接进入真实Lua HTTP解码/顺序ZIP解析：4连接全部关闭，整包MD5/签名及双组件摘要通过，元数据缓存14612字节，source_unchanged=true；无整ZIP落盘。8项顺序、HTTP21、诊断14、ZIP20、runtime21组及容量回归通过。未操作设备、未改原签名ZIP或安装门；当前1.5.0容量包不是1.0.2诊断基线。接续设备原生接收合同和实际安装/用户数据保持，不重查已通过容量及电脑公网解析。详见doc/2026-10-24_CAT1顺序流式容量修复与公网解析验证.md。


## 最新只读网络诊断基线已准备（待人工导入）

SAM | 2026-10-24 +08:00 | 唯一集合firmware_releases/baseline_diag_stream_20261024/HTTP_DIAGNOSTIC/CAT1/USB_IMPORT，51文件，1.0.2/build3；原生LuaDB520270、SOTA249813；含文本依赖入口预计USB LuaDB521277/524288。为留入口空间，仅隔离快照排除Filebin HTTPS诊断/证书，客户HTTP流式及业务保留，根源码和目标1.5.0未变。51文件hash/≤23字节名、生成解压、HTTP-only隔离验证通过。Luatools最终合并/部署未执行；需人工导入新集合，保留FS/KV仅脚本下载后验证OTA_NET_CHECK。未生成新双端ZIP，不开放安装门。详见doc/2026-10-24_1.0.2只读流式诊断基线交付.md。


## 实机只读下载已执行；当前定位ZIP_LOCAL_HEADER

SAM | 2026-10-24 +08:00 | 实机1.0.2/build3/IDLE；Luatools镜像522240、51文件，非main字节码与候选一致。真实OTA_NET_CHECK已启动，MQTT保持CONNECTED，原生限长读取实际执行；METADATA阶段ZIP_LOCAL_HEADER失败，尚未通过整包或安装验收。仅在隔离快照补成员/偏移/四字节错误码；同一USB_IMPORT只更新ota_seq_zip.luac，其余50文件不变，revision2尚未下载。USB估算521368余2920；注入与原生生成解压通过。下一项仅取精确失败字节，不重查分区或已过电脑公网。见doc/2026-10-24_CAT1实机只读下载ZIP头定位.md。


## 已定位并修复：ZIP_H2_O1913_B00000000来自zbuff used未重置（待下载）

SAM | 2026-10-24 +08:00 | 修订2实板头部探针取得第2成员头偏移1913全零。官方clear只memset不清used，socket.rx按used追加；旧实现query(0,n)读到零，旧夹具错误地把clear当重置因此漏测。生产http模块改buffer:del()，夹具同步native追加语义；回归先失败后通过，HTTP22项、原生生成解压通过。根LuaDB524275；基线修订3USB估算521366，余2922；同原USB_IMPORT仅更新ota_http_range.luac，其余50不变。变更后公网原始TCP解析通过；修订3尚未下载，未验收设备修复或安装。下一项仅下载该修复后跑同一只读请求。见doc/2026-10-24_CAT1原生接收zbuff有效长度修复.md。


## 修订3实板：全零头未复现，尾部HTTP_SOCKET；修订4待下载

SAM | 2026-10-24 +08:00 | 一次实测及一次受限重试约10秒HTTP_SOCKET，限长读取日志字节下界约664KB，失败前有缓存；未取得完整MD5，不能称实板下载通过。guard会在终止事件前抢先拒绝缓冲数据，已增加发送完成后的接收排空，连接/发送错误、读空/截断、分块终止、超时/暂停/所有摘要继续拒绝。回归先失败后通过，HTTP24项及分块/握手专项通过；根LuaDB524269，基线USB估算521360余2928。同原USB_IMPORT仅更新ota_http_range.luac，其余50不变，revision4未部署。下一项只测该修复是否覆盖实机尾部问题；不保证真实截断可恢复，不开放安装。见doc/2026-10-24_CAT1尾部终止事件缓冲排空修复.md。


## 修订4实板原生读取仍失败；Keep-Alive修订5待下载

SAM | 2026-10-24 +08:00 | round4为HTTP_NATIVE_OVERFLOW，此谓词也覆盖native false，未确认实际越界。官方network_rx离线直接拒绝读，Lua排空不足；服务器Keep-Alive按512字节+4ms慢读全685625字节且MD5通过、结束后连接仍打开。HTTP适配器改Keep-Alive，客户端仍每请求完成/失败主动close/release，不复用、不松数据校验；HTTP27项和原生生成解压通过。主LuaDB524274，基线USB521365余2923；同原51文件集合仅http字节码更新，revision5未部署。下一项同一只读实测，尚未验收下载/安装。见doc/2026-10-24_CAT1服务器关闭前KeepAlive读取修复.md。


## 实板下载项关闭；GR首次部署进入有据准备

SAM | 2026-10-24 +08:00 | round5 COMPLETE/gr_verified=true/cat_verified=true/SEQUENTIAL_200；after状态1.0.2/build3/IDLE。J-Link按已验证Cortex-M4配置恢复只读访问：SCA直接App，Boot整40KiB全FF，B/scratch/Boot日志/协调日志全FF，preserved67268非FF/NVDS63非FF保持保护。完整1MB副本及sha已归档，非原子一致快照；不恢复旧业务数据。本轮不改合同/授权，不烧写Boot，不重编现有基线。待生成匹配426304字节紧凑基线与信任合同的首次部署镜像，CAT原生激活与跨升级数据保持另待验收。证据device_readonly/round5_acceptance.json、gr_boot_core_readonly.txt、gr_current_flash_inventory.json、gr_fixed_layout_inventory.json；详见最新接续文档。

### 2026-10-24 13:55 增量锁定
FO7保存及无自动运行、WDT修复基线下载与完整回读、用户保护区不变、实机WDT初始化0均通过。详见当日WDT阻塞修复文档。唯一接续点：已初始化WDT在验签探针中refresh返回1，尚未进入SHA/PKC；Boot未部署，双端OTA未验收。不要重开CAT1下载、分区或WDT初始化排查。

### WDT刷新返回1的准确接续
已在真实HAL错误分支定位到硬件运行位为0；句柄counter/clock有效、锁未占用。尚不能把调试观测定性为正常业务故障。新增`fw_version verify`正常上下文只读入口，主机回归通过，待用户手动编译隔离1.0.2工程，再重新签名和手动部署；旧载体不含此改动。详见`2026-10-24_WDT刷新错误分支与正常运行验签入口.md`。没有执行GR编译/下载。

### 最新锁定：正常运行WDT与原生验签通过
现板1.0.2/build3，`fw_version verify`真实返回`wdt_running=1 refresh=0x0000 result=0 signature_ok=1 bytes=427328 version=1000002`；证据`logs/ota_wdt_fix_20261024/normal_runtime_acceptance.json`及对应原始串口日志。受控复位后同样通过。WDT与此应用签名验证关闭，不再复测。Boot已离线重绑定427328字节新基线，批准门保持关闭，未编译未部署；下一项仅Boot首次接入。真实双端OTA及此次下载用户数据对比仍未验收。

### Boot部署接续增量
Boot-only完整回读门已实现（6项新测试，原应用回读5项通过），不会授予启动许可。最新实板签名应用428232字节匹配；preserved73728字节/NVDS8192字节与前次有效回读完全一致。证据`firmware_releases/boot_bound_verify_cli_20261024_NOT_FLASHABLE/latest_gr_user_region_comparison.json`。尚未编译/部署Boot，批准合同及跨端安装仍待闭合；不可让用户下载批准位0的Boot。详见`2026-10-24_Boot首次部署回读门与现板数据保持.md`。

### 最新有效接续：已生成可进入首次启动验证的Boot编译输入
不改已签名合同原文或现板APP，以本板完整副本、实际签名通过、空白可写区及保护区证据单独形成首次接入测试准入。生成`firmware_releases/GR_BOOT_COMMISSIONING_20261024/GR_BOOT_COMMISSIONING.uvprojx`，provision绑定427328字节当前基线，1/1/1仅作为本板测试部署输入；生产/双端OTA未验收。4项定向拒绝测试通过，工程源路径及J-Link/FO7/FC8000已检查。下一步用户仅编译该Boot，勿下载；编译后检查实际产物再准备下载。本轮未编译未下载，不再重烧现应用。详见`2026-10-24_Boot首次接入测试准入与编译入口.md`。

### Boot用户编译产物已核验，进入手动下载阶段
Boot本次0错0警告；加载36048/40960、压缩下载34044字节；实际二进制1/1/1和当前427328字节基线descriptor匹配。已生成`firmware_releases/GR_BOOT_COMMISSIONING_20261024/BOOT_DOWNLOAD_ONLY.uvprojx`，TargetName与J-Link options匹配、FO7/FC8000，避免Keil因目标名不匹配回退ULINK。最新完整before为同目录`immediate_before_boot.bin`。下一步用户手动Download，不F7不主动Reset/Run；之后完整回读检查再启动。没有重编/重烧App，本轮未代用户编译或下载。

### 最新锁定：Boot首次实板接入通过，停止重复该项
用户下载Boot后完整有效回读通过：SCA→0x002EC000、Boot34044字节相符、APP与用户区/非计划区原样保持。Boot APP_INFO明确BOOT_LONG_TIME=0，SCA仅bit9按实际编译值变化，其余位保留。实际受控复位后正常运行1.0.2/build3，WDT刷新0、signature_ok=1。证据`firmware_releases/GR_BOOT_COMMISSIONING_20261024/first_boot_acceptance.json`及原始日志。分区未改，Boot首次接入关闭；后续不重开空间/WDT/签名/下载配置，接续仅真实1.0.2→1.5.0升级链路。


## 被当前状态替代的早期摘要（仅追溯）

## 当前最新结论（此前待下载记录仅保留历史）

SAM | 2026-10-24 +08:00 | **签名1.0.2/build3应用已实板部署，完整回读一致，保护区未变，provisioned=1**。这些项目关闭。只读验签目前被WDT未初始化拦住，实机返回0xE9；已查明原报警2500ms在实测26740Hz下转换66850 ticks，超SDK的16位上限。BSP改1000ms报警、保留5000ms复位，定向回归及主工程编译通过；接下来只验证修复版，不回头测下载/布局。详见[落地与具体阻塞修复](2026-10-24_实板签名基线落地与OTA看门狗阻塞修复.md)。Boot仍未部署。

SAM | 2026-10-24 +08:00 | GR首次部署本地准备已落地：真实签名1.0.2基线427208字节，隔离Boot0错0警告，加载区36048/40960字节，二进制provision和签名篡改拒绝检查通过。输出`firmware_releases/gr_first_deploy_20261024_NOT_FLASHABLE`，批准仍关闭，不可烧录。新证据确认现用FLM的Verify存在隐式SCA重写分支；下一步只闭合首次部署启动顺序及批准合同，不重跑CAT1下载。详见[签名基线与隔离Boot准备](2026-10-24_GR首次部署签名基线与隔离Boot准备.md)。

SAM | 2026-10-24 +08:00 | **CAT1修订5已部署，客户HTTP200/chunked实板只读下载/整包前置校验/签名/双组件摘要COMPLETE通过**；结束后CAT1仍1.0.2/build3/IDLE，未安装。不重测此项目，不重上传同一后台包。下一项为GR Boot首次部署：实读SCA仍直接启动0x00202000，整个Boot40KiB和B/升级日志区为空；GR实际应用长度477536，与紧凑基线426304不同。1MB现机只读副本已保存，但非原子快照；preserved和NVDS有数据，全程保护。详见[最新实板验收与接续](2026-10-24_CAT1实板下载通过与GR首次部署接续.md)。


SAM | 2026-10-24 +08:00 | 汇总并复用已有证据；此表是当前状态入口，历史报告保留追溯，不反复重新规划/测试。

## 已通过与需补验

| 项目 | 当前结论及证据 | 后续动作 |
|---|---|---|
| SDK/源码基线 | 已固定SDK1.0.4与Air780EGH根目录；交付副本取消自动同步 | 沿用，不重新选基线 |
| CAT1脚本布局 | 已通过主机包结构/地址检查：0x56E000–0x5EE000，524288字节；10-22原生SOTA生成报告 | 仅测本轮最终script.bin实际大小 |
| CAT1原生FOTA容量 | 0x64E000–0x754000；扣98304备份后预算974848字节；同一报告已有检查与拒绝坏包证据 | 不重算布局，仅核新SOTA大小 |
| 用户数据区包写保护 | 10-22报告已验证越界至FS的包即使重算校验也拒绝；正常脚本升级保留LFS/KV另有10-24官方正文 | 沿用静态合同；不能称实板用户数据已验收 |
| GR布局/容量 | 采用后续固定槽442368字节；当前payload426304，加904签名后427208，余15160 | 旧报告479232失效；不调整布局、不重编未变化源码 |
| GR当前构建 | 10-24安装结果改接主工程0错0警告，HEX实际生成；日志ota_installation_result_20261024/main_build.txt | 核对源码/产物hash后复制现有构建 |
| CAT1安装结果判断 | 官方允许重启后版本判断；现有实现加签名代码读回、任务/epoch、120秒健康；9组相关回归通过 | 不再等待专用pending接口；固件部署后测真实结果 |
| 数据保持软件链 | 10-24已有基线随INTENT持久化、提交/重启前检查、业务前比对及持久回执；6组相关回归通过 | 沿用，不重新写扫描器或日志 |
| 原生提交/撤销/重启授权软件 | test_native_fota/default_native_path已有主机故障测试通过，未发生本轮破坏性改变 | 不重测相同主机用例；中途复位原生行为仍缺匹配V2052实板证据 |
| KV可读性 | 既有OTA_CAPS证明kv_get存在；现有代码拒绝未初始化KV，公开通用初始化存在风险分支 | 不是重新验证容量；需真实只读结果或精确底包初始化实现证据，不能将“API存在”当“读出内容” |
| FS空间读数 | 既有实板total524288/free495616记录可追溯；不是当前实时余量 | 真正下载前一次刷新，不反复测静态分区 |
| 脚本/代码身份与协议回归 | 既有签名/解压读回及两端结果协议测试有效，旧pending帧拒绝 | 最终生成器检查新脚本集合；不重跑整套无关测试 |
| 新代码实板部署 | 最新结果协议和数据事务接线尚未烧录 | 本轮准备唯一基线候选，不能用旧SOTA冒充 |
| 真实N→1.5.0/失败恢复 | 无完整验收证据 | 不生成可安装声明或假成功；最终目标包仍需完整发布条件 |



### GR目标1.5.0已冻结
用户14:48编译的新目标0错0警告、源码hash一致、1.5.0/build4正文427328字节、签名后428232字节并独立验签通过。输出target_1_5_0_current_20261024/target_verification.json。GR目标准备关闭，现板保持1.0.2。CAT1原生合同与未知KV只读证据仍缺，不能硬改门或要求反复烧GR；未生成新安装ZIP。详见2026-10-24_GR目标1.5.0冻结与CAT1安装阻塞.md。


### 安装生成路径与提前拒绝已修改（源码/主机交付）
新GUI为OTA_Packager/YP001OtaPackager_20261024_Admission.exe。PackageForDevice提供受控安装包入口，12项拒绝测试及核心63项通过；CAT resolver将不可安装包提前拒绝，相关运行时21+5+3组通过。Lua未部署、真实CAT1原生/数据证据仍缺，本轮无设备动作；不是双端安装已完成。详见2026-10-24_安装包生成入口与CAT1提前拒绝落地.md。

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

## 最新实板接续：手动入口通过，WAIT_GR发送缺陷已定位

新项目实际合并已匹配52个内容条目（CRC条目不同），521239字节。主动命令实际返回ACCEPTED_PENDING_GR，设备停WAIT_GR。无需再让用户重新导入旧集合。

V2052精确底包反汇编证明json由lua_newuserdata构造；ota_platform.send_gr误要求table导致请求未发。根源码已修复，2项原生JSON回归与21项运行时回归通过；源码修复未部署。

新修复目标包first_trial_jsonfix_20261024/package/1.0.2---1.5.0_J1.ypota.zip已生成验签，MD5 353e60cc1d9c1a3adf059769b2f28d15；GR不变。已请用户上传新包提供新URL。旧包目标也含该错误，不能只修基线继续旧包。

当前设备旧WAIT_GR任务仍保留。尚需安全切换任务及准备最终修复基线；不要清用户数据/伪造GR授权，不直接部署修复后自动重放旧任务。详见2026-10-24_首次主动OTA_WAIT_GR与JSON原生模块修复.md。安装及数据保持未验收。

## 最新接续：J1地址已验证，最终J1基线就绪

新后台包695203字节，MD5 353e60cc1d9c1a3adf059769b2f28d15，逐字节匹配。无需重传。

唯一新下载项目OTA_J1_FIXED已添加D:/Installers/project；对应manual_j1_20261024/USB_IMPORT，51文件，USB主机重建520811字节，余3477。包含JSON修复和基线专用manual_bridge；启动自动暂停确切旧WAIT_GR，显式新命令先QUERY，只有3秒内GR空闲且无owner才原子结束旧任务，再经原accept受理J1。保留用户数据、失败/重试/上报记录；不释放实际GR owner。6项新接续和5项原入口测试通过。J1 ZIP及GR不变。

当前待用户下载此新项目，仅脚本保留FS/KV；未部署前不要发送新任务。下载后核实际merge，发送OTA_TRIAL_START=353e60cc1d9c1a3adf059769b2f28d15,<用户最新URL>。状态应先GR_IDLE_QUERY_PENDING，再OTA_LOCAL=OLD_WAIT_RETIRED_GR_IDLE及ACCEPTED_PENDING_GR。这仍不代表安装成功。实板任务切换/升级/可读数据/健康及上报均待验；raw KV非阻塞且未验收。详见2026-10-24_J1后台与旧WAIT_GR安全接续基线.md。

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
