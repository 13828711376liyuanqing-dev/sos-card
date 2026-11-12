# 首次主动OTA已受理及WAIT_GR阻塞定位

SAM | 2026-10-24 +08:00 | 修复原生JSON userdata被错误拒绝导致不发GR请求；不改GR、布局或用户数据。

## 实板实际推进

Luatools本次真实合并镜像有效长度521239字节，update指纹4118b4ffb3375657613bb59c88eab35075aea6ea8cfe7a87a6790f5c83563f5d。52个脚本/资源内容与预期一致，只有LuaDB整体校验条目不同（成员排列/头部不同会影响该值），不将整个镜像声称字节相同。full_merge_comparison.json记录原始差异。

已向COM26发送本次MD5及后台URL，实板回复QUEUED_NOT_INSTALLED、ACCEPTED_PENDING_GR；随后FW_VERSION确认phase=WAIT_GR。GR business link=1 net=4 alarm=0 call=0 battery89。未观察到安装开始，不再重复提交同一任务。

## 确认的代码缺陷

Air780EGH/ota_platform.lua::default.send_gr要求type(json)==table，V2052 json实际为native userdata，因此直接false，UART没有OTA_CTL日志。精确V2052反汇编链：luaopen_cjson 0x00c379a4→luat_newlib2 0x00c322fc→rotable2_newlib 0x00c14ece→lua_newuserdata。抽取证据logs/ota_first_trial_live_20261024/json_native_container_disassembly.txt，复用已有底包反汇编，不操作设备。

已改为pcall保护成员访问及编码，不按容器类型否定功能；仍要求UART函数、编码成功、字符串及1000字节上限，保留所有授权门。新增test_platform_native_json.py用真实userdata适配器复现修改前失败/修改后通过，缺失/错误/超长codec仍拒绝；2项通过，原运行时21项通过。尚未部署此源码修复，不能写成实板缺陷已消除。

## 新目标必须同步修复

旧已上传目标也含错误检查，若只修基线，目标安装后仍无法向GR确认。已生成新的同版本受控候选：Air780EGH/_ota_release/first_trial_jsonfix_20261024/package/1.0.2---1.5.0_J1.ypota.zip。695203字节；MD5 353e60cc1d9c1a3adf059769b2f28d15；SHA256 ab213e0465a241f026f67814b5c49100b4be038086f13a6480c4caa4a2ea7e83。

CAT1目标SOTA251499字节、LuaDB523281/524288，余1007；官方编译/解压、签名归档、六成员STORE、CRC、组件hash通过。GR沿用同一冻结签名镜像，未重编或重签。新review绑定当前源码与新增回归证据。不覆盖旧候选，不伪造安装/KV验收。

## 重要接续边界

当前实板仍是未修复的手动基线，并持有旧包WAIT_GR任务。未清任务NV、未初始化/清空KV、未执行原生激活。先取得新包URL；基线部署及旧WAIT_GR任务向新任务的安全切换还需完成，不能直接下载修复基线让旧任务自动续作，也不能绕过GR所有权或随意清状态。这个任务切换是当前需补工作，不重开布局/Boot/旧网络解析。

## 强制检查结果

| 项目 | 结果 |
|---|---|
| 改前调用链/既有工作 | 核对平台sender、manager发送及真实日志；保留其他工作 |
| 主/交付 | 仅CAT1根源码；交付副本不适用（用户取消同步） |
| 注释 | ota_platform/测试/生成器有SAM、2026-10-24、+08:00及原因 |
| 中文说明 | 本文件、压缩接续和唯一验收表已更新 |
| 主Keil/交付Keil | 不适用；GR未改，用户手动操作 |
| 实板验证 | 新手动入口和任务受理已观察；JSON修复未部署，安装和数据保持未验收 |
| 数据/布局/清理 | 无用户数据删除、无KV初始化、无Flash布局或Keil配置修改 |
